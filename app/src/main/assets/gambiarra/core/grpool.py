import json
import os
import threading
import time
import uuid
import urllib.error
import urllib.request

UPSTREAM_FIXO = os.environ.get("GR_UPSTREAM")


def _upstream():
    """URL do provider escolhido no CONFIG.

    Ler a cada chamada (e nao no import) e o que permite trocar de
    provider sem recompilar nada: o valor vem do config.json. O
    GR_UPSTREAM do ambiente continua tendo prioridade, para testes.
    """
    if UPSTREAM_FIXO:
        return UPSTREAM_FIXO
    try:
        import providers
        url = providers.base_url_atual()
        if url:
            return url
    except Exception:
        pass
    return "https://api.nightrouter.ai/v1"


# compatibilidade: quem importava grpool.UPSTREAM continua funcionando
UPSTREAM = UPSTREAM_FIXO or "https://api.nightrouter.ai/v1"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
COOLDOWN = float(os.environ.get("GR_COOLDOWN", "62"))
NOTICE = os.environ.get("GR_NOTICE", "Fazendo uma gambiarra aqui \U0001F436")
ORDER_FILE = os.environ.get("GR_ORDER", "model_order.json")

_registry = {}
_mark = {}
ON_SWITCH = None

class UpstreamError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message

class Slot:
    __slots__ = ("stored", "token", "state", "errors", "cooldown_until")

    def __init__(self, stored):
        self.stored = stored
        self.token = stored
        self.state = "untested"
        self.errors = 0
        self.cooldown_until = 0.0

    def usable(self, now):
        """Pode ser tentada agora?

        Antes isto olhava so o estado "bad", ignorando o cooldown: uma key
        que tomou 429 continuava "utilizavel" na hora e era reusada em
        TODOS os modelos da cadeia antes de o pool passar para a proxima.
        """
        if self.state == "bad":
            return False
        return self.cooldown_until <= now

class Pool:
    def __init__(self):
        self.lock = threading.Lock()
        self.slots = []
        self.cursor = 0
        self.racing = set()

    def load(self, keys, tokens_by_index=None):
        with self.lock:
            self.slots = []
            for i, k in enumerate(keys):
                slot = Slot(k)
                if tokens_by_index and i in tokens_by_index:
                    slot.token = tokens_by_index[i]
                    slot.state = "live"
                self.slots.append(slot)

    def mark_live(self, index, token):
        with self.lock:
            if 0 <= index < len(self.slots):
                self.slots[index].token = token
                self.slots[index].state = "live"

    def mark_bad(self, index):
        with self.lock:
            if 0 <= index < len(self.slots):
                self.slots[index].state = "bad"

    def order(self, exclude=(), rotate=True):
        now = time.time()
        with self.lock:
            n = len(self.slots)
            if n == 0:
                return []
            start = self.cursor
            if rotate:
                self.cursor = (self.cursor + 1) % n
            idx = [(start + i) % n for i in range(n)]
            good = [i for i in idx if self.slots[i].usable(now) and i not in exclude]
            cooling = [i for i in idx if i not in exclude
                       and self.slots[i].state != "bad" and i not in good]
            bad = [i for i in idx if i not in exclude and self.slots[i].state == "bad"]
            return good + cooling + bad

    def revive(self):
        with self.lock:
            for slot in self.slots:
                if slot.state == "bad":
                    slot.state = "untested"

    def count(self):
        with self.lock:
            return len(self.slots)

    def live_count(self):
        with self.lock:
            return sum(1 for s in self.slots if s.state == "live")

    def resumo(self):
        """(total, utilizaveis, mortas, em cooldown).

        'Utilizaveis' inclui as ainda nao testadas: elas podem responder
        perfeitamente, so nao foram usadas desde que o app abriu. Contar
        apenas as 'live' fazia a tela dizer 0 vivas com 6 keys boas.
        """
        agora = time.time()
        with self.lock:
            total = len(self.slots)
            mortas = sum(1 for s in self.slots if s.state == "dead")
            frias = sum(1 for s in self.slots
                         if s.state == "live" and s.cooldown_until > agora)
            uteis = total - mortas
            return total, uteis, mortas, frias

    def describe(self, limit=8):
        with self.lock:
            rows = []
            for i, s in enumerate(self.slots[:limit]):
                left = max(0.0, s.cooldown_until - time.time())
                rows.append((i, s.state, round(left, 1), s.token[:10]))
            return rows, len(self.slots)

    def note_failure(self, index, cooldown=COOLDOWN):
        with self.lock:
            if 0 <= index < len(self.slots):
                s = self.slots[index]
                s.errors += 1
                s.cooldown_until = time.time() + cooldown

class ModelRouter:

    def __init__(self):
        self.routes = {}
        self.load()

    def load(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ORDER_FILE)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.routes = {k: list(v) for k, v in data.items() if isinstance(v, list)}
        except (OSError, ValueError):
            self.routes = {}

    def has(self, model):
        if model in self.routes:
            return True
        return _sem_prefixo(model) in self.routes

    def chain(self, model):
        """Cadeia do modelo, aceitando com ou sem o prefixo do provedor.

        O servidor pede "gambiarraapi/gpt-6-astra" mas o model_order.json
        guarda "gpt-6-astra": sem resolver os dois, a cadeia virava so o
        proprio modelo e nao havia vizinho para onde cair no TPM.
        """
        base = self.routes.get(model)
        if base is None:
            base = self.routes.get(_sem_prefixo(model))
        if not base:
            # sem rota conhecida: usa a familia toda como vizinhanca
            base = _familia(model)
        if not base:
            return [model]
        if len(base) < 2:
            base = list(base) + [m for m in _familia(model) if m not in base]
        if len(base) < 2:
            return [model]
        head = base[0]
        rest = sorted(base[1:], key=_rank)
        return [head] + rest

    def alive(self, model):
        """Models the background scan has seen answering in the last few
        minutes. Used to seed a fresh chain when the current one is dead."""
        now = time.time()
        rota = self.routes.get(model) or self.routes.get(_sem_prefixo(model)) or []
        out = []
        for name in rota:
            entry = registry(name)
            for variant in model_variants(name):
                if entry.get("alive_at", 0) > now - 300:
                    out.append(variant)
                    break
        return out


def _sem_prefixo(model):
    """'gambiarraapi/gpt-6-astra' -> 'gpt-6-astra'."""
    if "/" in model:
        return model.split("/", 1)[1]
    return model


def _familia(model):
    """Todos os modelos conhecidos da mesma familia do pedido.

    Sem model_order.json valido ainda da para cair num vizinho: gpt-6-astra
    vai para gpt-6-luna, gpt-5.6-sol, etc. Isso garante que o TPM nunca
    prenda a chamada num unico modelo.
    """
    base = _sem_prefixo(model)
    fam = base.split("-")[0]
    nomes = []
    for rota in ROUTER.routes.values():
        for nome in rota:
            if nome not in nomes:
                nomes.append(nome)
    if not nomes:
        return [model]
    mesmo = [n for n in nomes if n.split("-")[0] == fam and n != base]
    outros = [n for n in nomes if n.split("-")[0] != fam and n != base]
    return [base] + mesmo + outros

def _rank(model):
    """Lower is faster. Models whose measured speed is known go first, and the
    ones that timed out or answered empty sink to the bottom for a while."""
    entry = registry(model)
    score = entry.get("avg", 5.0)
    if _timed_out(model):
        score += 60.0
    score += entry.get("timeouts", 0) * 2.0
    score += entry.get("empties", 0) * 1.0
    return score

def _note_speed(model, seconds):
    entry = registry(model)
    avg = entry.get("avg")
    entry["avg"] = seconds if avg is None else (avg * 0.7 + seconds * 0.3)
    entry["alive_at"] = time.time()
    entry["nochan"] = 0

def scan_alive(models, keys, workers=8):
    """Ping every candidate with a tiny request so the router knows which ones
    have a channel before a real request arrives. A dead model costs one
    round trip here instead of a whole deadline later."""
    todo = [m for m in models if not _no_channel_now(m)]
    if not todo or not keys:
        return 0
    found = [0]
    lock = threading.Lock()
    q = queue.Queue()
    for name in todo:
        q.put(name)

    def run():
        while True:
            try:
                name = q.get_nowait()
            except queue.Empty:
                return
            with lock:
                token = keys[found[0] % len(keys)]
            body = {"model": name, "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}]}
            status, text = _post(token, body, timeout=12)
            if status == 200:
                try:
                    parsed = json.loads(text)
                except ValueError:
                    parsed = None
                if not _empty(parsed):
                    _note_speed(name, 1.0)
                    with lock:
                        found[0] += 1
                    continue
            if no_channel(status, text):
                _note_no_channel(name)
            elif is_quota(status, text):
                _note_speed(name, 1.0)

    threads = [threading.Thread(target=run, daemon=True)
               for _ in range(min(workers, len(todo)))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return found[0]

def is_quota(status, body):
    low = (body or "").lower()
    if status not in (429, 402, 403, 500, 502, 503):
        return False
    marks = ("quota", "limit", "exceeded", "insufficient", "balance",
             "credit", "rate", "tokens", "capacity", "overloaded", "usage")
    return any(m in low for m in marks)

def build_chain(models, selected):
    if not selected:
        return []
    fam = selected.split("-")[0]
    same = [m for m in models if m != selected and m.split("-")[0] == fam]
    rest = [m for m in models if m != selected and m.split("-")[0] != fam]
    return [selected] + same + rest

# --------------------------------------------------------------- anti-TPM
# Um modelo como gpt-6-astra roda numa instancia compartilhada: quando o
# TPM da conta upstream estoura, TODA key leva 429 ao mesmo tempo. Nesse
# caso a resposta certa nao e desistir: e pular para o modelo mais proximo
# (mesma familia -> mesma capacidade) e, quando o ciclo termina, voltar ao
# modelo pedido. Repetimos ate conseguir -- a chamada nunca falha por TPM.
TPM_HINTS = ("tokens", "tpm", "rate limit", "rate_limit", "too many",
             "requests", "capacity", "overloaded", "busy", "quota",
             "exceeded", "throttl")

def looks_tpm(status, text):
    """429/503 com cara de limite de taxa ou TPM."""
    if status not in (429, 500, 502, 503):
        return False
    low = (text or "").lower()
    if "no available channel" in low or "model_not_found" in low:
        return False
    return any(h in low for h in TPM_HINTS) or status == 429

def _note_tpm(model, seconds):
    entry = registry(model)
    entry["tpm"] = entry.get("tpm", 0) + 1
    entry["tpm_until"] = time.time() + max(1.0, float(seconds))

def tpm_quente(model):
    """Modelo bloqueado por TPM agora (volta sozinho quando o minuto vira)."""
    entry = registry(model)
    return time.time() < entry.get("tpm_until", 0)

def chain_ciclica(model, tentativa):
    """A cadeia do modelo, deslocada para a tentativa N.

    tentativa 0 -> comeca no modelo pedido (o "inicial")
    tentativa 1 -> comeca no vizinho mais proximo
    ...
    Ao completar uma volta inteira, recomeca do modelo pedido: e assim
    que o trafego volta para o astra quando o TPM dele libera.
    """
    base = ROUTER.chain(model)
    if not base:
        base = [model]
    # variantes (-free / limpo) sem duplicar
    expandido = []
    for nome in base:
        for v in model_variants(nome):
            if v not in expandido:
                expandido.append(v)
    if not expandido:
        return [model]
    n = len(expandido)
    pos = tentativa % n
    return expandido[pos:] + expandido[:pos]

def _espera_tpm(tentativa):
    """Espera curta entre voltas: 0.4s, 0.8s, 1.6s... ate 8s."""
    return min(8.0, 0.4 * (2 ** min(tentativa, 5)))

POOL = Pool()
ROUTER = ModelRouter()

def registry(model):
    key = model
    with _registry.setdefault("_l", threading.Lock()):
        entry = _registry.get(key)
        if entry is None:
            entry = {"last": [], "at": time.time()}
            _registry[key] = entry
        return entry

def _post(token, payload, timeout):
    base = _upstream()
    # gateway que nao fala /chat/completions (ex: Bike4Mind) passa pelo
    # adaptador. Para os providers normais ele devolve (status, corpo)
    # do jeito de sempre, sem nenhuma mudanca de comportamento.
    try:
        import adaptador
        modo = adaptador.adapter_ativo()
        if modo != adaptador.MODO_OPENAI:
            return adaptador.postar(base, token, payload, timeout, modo)
    except Exception:
        pass
    body = json.dumps(payload).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        return 0, "connection: %s" % e.reason
    except Exception as e:
        return 0, "error: %s" % e

def stream_for(model, keys, payload, on_open):
    """Stream the fastest upstream straight to the client.

    Free keys swing between 0.4s and 30s for the same question, so the first
    wave opens RACE keys at once and keeps whichever starts answering first.
    The losers are closed. Later waves go serial to avoid burning quota.

    Mesma regra do TPM do complete_for: se o modelo pedido estourar o
    limite, anda para o vizinho da cadeia e, quando a volta termina,
    recomeca do modelo pedido. Nao devolve erro por limite de taxa.
    """
    last = None
    if not load_keys(keys):
        raise UpstreamError(503, "no_keys", "nenhuma key carregada")
    per_try = max(15.0, float(os.environ.get("GR_TRY", "20")))
    race = max(1, int(os.environ.get("GR_RACE", "3")))
    hard_limit = float(os.environ.get("GR_HARD_LIMIT", "900"))
    inicio = time.time()

    dead = set()
    tentativa = 0
    while True:
        if time.time() - inicio > hard_limit:
            raise last or UpstreamError(504, "timeout", "limite duro atingido")
        # a cada volta anda um passo na cadeia; volta ao inicial ao completar
        chain = chain_ciclica(model, tentativa)
        order = POOL.order(rotate=bool(tentativa % 2))
        first_wave = True
        houve_tpm = False
        tentou_algo = False

        while True:
            batch = []
            for index in order:
                token = _token_of(index)
                if not token or token in dead:
                    continue
                if (token, chain[0]) in POOL.racing:
                    continue
                batch.append(index)
                if first_wave and len(batch) >= race:
                    break
            if not batch:
                break
            tentou_algo = True
            targets = [t for t in chain if not _timed_out(t)] or chain
            jobs = []
            for pos, index in enumerate(batch):
                token = _token_of(index)
                target = targets[pos % len(targets)]
                body = dict(payload)
                body["model"] = target
                body["stream"] = True
                job = {"index": index, "token": token, "target": target,
                       "started": time.time(), "status": None, "head": b"",
                       "conn": None}
                jobs.append(job)
                threading.Thread(target=_race_open, args=(job, body, per_try),
                                 daemon=True).start()
            POOL.racing.update((j["token"], j["target"]) for j in jobs)
            winner, losers = _first_ready(jobs)
            POOL.racing.difference_update((j["token"], j["target"]) for j in jobs)
            for job in losers:
                _close_job(job)
            if winner is None:
                for job in jobs:
                    texto = _text(job["head"])
                    if job["status"] in (401, 403):
                        POOL.mark_bad(job["index"])
                        _note_dead(job["token"])
                        dead.add(job["token"])
                        last = _parse_error(job["status"], texto, job["target"])
                    elif job["status"] == 0:
                        _note_timeout(job["target"])
                        last = UpstreamError(504, "timeout", texto[:200])
                    elif job["status"]:
                        last = _parse_error(job["status"], texto, job["target"])
                        if looks_tpm(job["status"], texto):
                            _note_tpm(job["target"], 30)
                            houve_tpm = True
                        elif no_channel(job["status"], texto):
                            _note_no_channel(job["target"])
                            # sem canal tambem e motivo para trocar de
                            # modelo, nao para repetir o mesmo
                            houve_tpm = True
                        POOL.note_failure(job["index"])
                if all(j["status"] in (401, 403) for j in jobs):
                    continue
                # Todos falharam por quota/TPM/canal: insistir no MESMO
                # modelo e inutil. Volta na cadeia para tentar o vizinho
                # em vez de repetir o que ja estourou.
                if houve_tpm or all(j["status"] and j["status"] != 200
                                    for j in jobs):
                    break

            _note_speed(winner["target"], time.time() - winner["started"])
            sink = on_open(winner["target"], winner["token"])
            if sink is None:
                _close_job(winner)
                raise UpstreamError(499, "cancelled", "cliente saiu")
            POOL.mark_live(winner["index"], winner["token"])
            _note_live(winner["token"])
            if winner["target"] != model and ON_SWITCH is not None:
                try:
                    ON_SWITCH(winner["target"])
                except Exception:
                    pass
            return _pump(winner["head"], winner["conn"], sink)

        # ---- fim de uma volta completa ----
        if not tentou_algo:
            time.sleep(_espera_tpm(tentativa))
        elif houve_tpm:
            time.sleep(_espera_tpm(tentativa))
        else:
            time.sleep(0.5)
        tentativa += 1

def _erro_no_head(head):
    """O upstream pode abrir 200 e mandar o erro dentro do stream.

    A primeira linha as vezes e `data: {"error":{...}}` com
    "exceeded token rate limit" - se tratarmos isso como sucesso, o
    cliente recebe o erro do servidor dos caras em vez de a gente
    trocar de modelo. Devolve o texto do erro, ou "" se for resposta boa.
    """
    try:
        texto = head.decode("utf-8", "replace") if isinstance(head, bytes) \
            else (head or "")
    except Exception:
        return ""
    low = texto.lower()
    if "exceeded token rate limit" in low:
        return texto
    if '"error"' in low and "data:" in low:
        # bloco SSE que carrega erro em vez de conteudo
        for linha in texto.splitlines():
            l = linha.strip()
            if l.startswith("data:"):
                corpo = l[5:].strip()
                if corpo and corpo != "[DONE]":
                    try:
                        obj = json.loads(corpo)
                    except ValueError:
                        continue
                    if isinstance(obj, dict) and obj.get("error"):
                        return corpo
    return ""


def _race_open(job, body, timeout):
    status, head, conn = _open_stream(job["token"], body, timeout=timeout)
    job.update({"status": status if status else -1, "head": head,
                "conn": conn, "done": True})

def _first_ready(jobs, limit=None):
    """Wait for the first job that actually opened. Returns (winner, losers)."""
    limit = limit or max(25.0, float(os.environ.get("GR_TRY", "20")))
    end = time.time() + limit
    while time.time() < end:
        for job in jobs:
            if job.get("done") and job["status"] == 200:
                return job, [j for j in jobs if j is not job]
        pending = [j for j in jobs if not j.get("done")]
        if not pending:
            return None, []
        time.sleep(0.02)
    return None, jobs

def _close_job(job):
    conn = job.get("conn")
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass

def _text(data):
    if isinstance(data, bytes):
        return data.decode("utf-8", "replace")
    return data or ""

def _open_stream(token, payload, timeout):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(_upstream() + "/chat/completions", data=body,
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "text/event-stream")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", UA)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode("utf-8", "replace"), None
        except Exception:
            return e.code, "", None
    except urllib.error.URLError as e:
        return 0, "connection: %s" % e.reason, None
    except Exception as e:
        return 0, "error: %s" % e, None
    # take the first complete SSE block, not one byte: the head of the stream
    # is the only proof the model actually started answering
    try:
        first = resp.readline()
        while first and not first.strip():
            first = resp.readline()
    except Exception as e:
        try:
            resp.close()
        except Exception:
            pass
        return 0, "error: %s" % e, None
    if not first:
        try:
            resp.close()
        except Exception:
            pass
        return 502, "stream vazio", None
    # 200 com erro dentro: repassa como falha para o roteador trocar de
    # modelo em vez de entregar o erro ao cliente
    erro = _erro_no_head(first)
    if erro:
        try:
            resp.close()
        except Exception:
            pass
        status = 429 if "rate limit" in erro.lower() else 503
        return status, erro, None
    return 200, first, resp

def _pump(first, resp, sink):
    """Forward the upstream SSE blocks untouched, as each one completes.

    An SSE event ends on a blank line and may span several lines (data:,
    event:, id:). Forwarding the whole block keeps finish_reason and [DONE]
    exactly as the upstream wrote them - rebuilding line by line lost them.
    """
    got = 0
    buf = first.replace(b"\r\n", b"\n")
    primeiro = True
    while True:
        while b"\n\n" in buf:
            block, buf = buf.split(b"\n\n", 1)
            if block.strip():
                # o primeiro bloco pode ser o erro de TPM disfarcado de
                # evento SSE: nao escreve isso no cliente
                if primeiro:
                    primeiro = False
                    erro = _erro_no_head(block)
                    if erro:
                        try:
                            resp.close()
                        except Exception:
                            pass
                        raise UpstreamError(
                            429 if "rate limit" in erro.lower() else 503,
                            "upstream", erro[:300])
                try:
                    sink.write(block + b"\n\n")
                    got += len(block)
                except Exception:
                    try:
                        resp.close()
                    except Exception:
                        pass
                    raise UpstreamError(499, "cancelled", "cliente saiu")
        try:
            more = resp.readline()
        except Exception:
            break
        if not more:
            break
        buf += more.replace(b"\r\n", b"\n")
    if buf.strip():
        try:
            sink.write(buf + b"\n\n")
            got += len(buf)
        except Exception:
            pass
    try:
        resp.close()
    except Exception:
        pass
    if not got:
        raise UpstreamError(502, "empty_response", "stream sem conteudo")
    return got

def answer_text(data):
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = msg.get("content") or ""
    if not text:
        text = msg.get("reasoning_content") or msg.get("reasoning") or ""
    if not text:
        content = msg.get("content")
        if isinstance(content, list):
            text = "".join(p.get("text", "") for p in content
                           if isinstance(p, dict))
    return (text or "").strip()

def _empty(data):
    if not isinstance(data, dict):
        return True
    choices = data.get("choices")
    if not choices or not isinstance(choices, list):
        return True
    choice = choices[0]
    if not isinstance(choice, dict):
        return True
    msg = choice.get("message") or choice.get("delta") or {}
    if not isinstance(msg, dict):
        msg = {}
    if msg.get("tool_calls") or choice.get("tool_calls"):
        return False
    if msg.get("function_call") or choice.get("function_call"):
        return False
    if (choice.get("finish_reason") or "") in ("length", "tool_calls",
                                               "function_call"):
        return False
    return not answer_text(data)

def _parse_error(status, body, model):
    try:
        data = json.loads(body)
    except ValueError:
        return UpstreamError(status or 502, "bad_gateway", body[:300])
    raw = data.get("error") if isinstance(data, dict) else None
    if not isinstance(raw, dict) and isinstance(data, dict):
        if "message" in data and ("type" in data or "code" in data):
            raw = data
    if isinstance(raw, dict):
        code = raw.get("type") or raw.get("code") or "upstream"
        return UpstreamError(status or 502, str(code),
                             str(raw.get("message") or body[:300]))
    return UpstreamError(status or 502, "upstream", body[:300])

def _eh_custom():
    """O provider ativo usa keys proprias na aba custom?

    Inclui os fixos com keys proprias (Bike4Mind) e os custom:<id>.
    Para NightRouter devolve False e nada muda no comportamento.
    """
    try:
        import providers
        return (providers.nome_atual().startswith("custom:")
                or bool(providers.atual().get("na_custom")))
    except Exception:
        return False


def _sem_saldo(status, text):
    """Upstream respondeu que a conta nao tem saldo?

    SO vale para Custom Provider em modo saldo. No NightRouter nada muda:
    o comportamento de la continua exatamente como era.
    """
    if not _eh_custom():
        return False
    try:
        import custom_modo
        if custom_modo.modo_atual() != custom_modo.MODO_SALDO:
            return False
        return custom_modo.e_sem_saldo(status, text)
    except Exception:
        return False


def _aposentar_conta(token, text, status):
    """Remove a conta sem saldo da base. True se removeu agora."""
    if not _eh_custom():
        return False
    try:
        import custom_modo
        import providers
        nome = providers.nome_atual().replace("custom:", "")
        if custom_modo.morta(nome, token):
            return False
        custom_modo.marcar_morta(nome, token,
                                 reason_text(status, text))
        return True
    except Exception:
        return False


def reason_text(status, text):
    """Motivo curto para guardar no registro da conta morta."""
    import re as _re
    limpo = _re.sub(r"\s+", " ", (text or "")).strip()
    return ("HTTP %s: %s" % (status, limpo))[:170]


def _token_of(index):
    with POOL.lock:
        if 0 <= index < len(POOL.slots):
            return POOL.slots[index].token
    return None

def load_keys(keys):
    keys = [k for k in (keys or []) if isinstance(k, str) and k.strip()]
    with POOL.lock:
        known = {slot.stored: slot for slot in POOL.slots if slot.stored}
        fresh = [known.get(k) or Slot(k) for k in keys]
        POOL.slots = fresh
        if POOL.cursor >= len(fresh):
            POOL.cursor = 0
        return len(fresh)

def complete_for(model, keys, payload):
    """Responde a chamada, custe o que custar.

    Regra do TPM: se o modelo pedido (ex. gpt-6-astra, instancia Azure
    compartilhada) estourar o limite, NAO devolvemos erro. Pulamos para o
    vizinho mais proximo da cadeia, e quando a volta termina recomecamos do
    modelo pedido. Fica girando ate uma resposta sair.

    Só desistimos de verdade quando o problema nao e temporario: nenhuma
    key existente (401/403 em todas) ou o cliente desistiu.
    """
    if not load_keys(keys):
        raise UpstreamError(503, "no_keys",
                            "nenhuma key carregada - rode o farm primeiro")

    # sem teto de tempo: TPM volta sozinho, entao esperamos ele voltar
    # (limite apenas para nao travar para sempre em caso de bug)
    hard_limit = float(os.environ.get("GR_HARD_LIMIT", "900"))
    inicio = time.time()
    per_try = max(6.0, float(os.environ.get("GR_TRY", "20")))

    last = None
    tentativa = 0
    keys_recarregadas = 0

    while True:
        if time.time() - inicio > hard_limit:
            raise last or UpstreamError(504, "timeout",
                                        "limite duro atingido")
        # a cada volta, a cadeia anda um passo: vizinho -> vizinho -> inicial
        chain = chain_ciclica(model, tentativa)
        order = POOL.order(rotate=bool(tentativa % 2))
        dead = set()
        houve_tpm = False
        tentou_algo = False

        for index in order:
            token = _token_of(index)
            if not token or token in dead:
                continue
            # a chave ja levou 429/limite nesta rodada: nao gasta a cadeia
            # inteira (168 modelos) repetindo com ela
            barrada = False
            for target in chain:
                if barrada:
                    break
                if _timed_out(target):
                    continue
                if _no_channel_now(target):
                    continue
                tentou_algo = True
                body = dict(payload)
                body["model"] = target
                started = time.time()
                status, text = _post(token, body, timeout=per_try)

                if status == 200:
                    try:
                        parsed = json.loads(text)
                    except ValueError:
                        parsed = None
                    if _empty(parsed):
                        _note_empty(target)
                        last = UpstreamError(502, "empty_response",
                                             "modelo sem conteudo: " + target)
                        continue
                    _note_speed(target, time.time() - started)
                    POOL.mark_live(index, token)
                    _note_live(token)
                    if target != model and ON_SWITCH is not None:
                        try:
                            ON_SWITCH(target)
                        except Exception:
                            pass
                    return target, text

                if status == 0:
                    _note_timeout(target)
                    last = UpstreamError(504, "timeout", text[:200])
                    break

                err = _parse_error(status, text, target)

                if status in (401, 403):
                    POOL.mark_bad(index)
                    _note_dead(token)
                    dead.add(token)
                    last = err
                    break

                # SEM SALDO: a conta acabou. Remove da base e segue para a
                # proxima. Tem que vir ANTES do looks_tpm, senao um 402 ou
                # um "quota exceeded" seria tratado so como rate limit e a
                # conta morta ficaria sendo tentada para sempre.
                if _sem_saldo(status, text):
                    POOL.mark_bad(index)
                    _note_dead(token)
                    mortas_agora = _aposentar_conta(token, text, status)
                    dead.add(token)
                    barrada = True
                    last = UpstreamError(402, "sem_saldo",
                                         "conta sem saldo, removida")
                    if mortas_agora and ON_SWITCH is not None:
                        try:
                            ON_SWITCH(model)
                        except Exception:
                            pass
                    continue

                if looks_tpm(status, text):
                    # TPM / limite: marca o modelo como quente por um tempo
                    # curto e parte para o proximo modelo da cadeia
                    _note_tpm(target, 30)
                    POOL.note_failure(index, cooldown=min(20, COOLDOWN))
                    houve_tpm = True
                    dead.add(token)
                    barrada = True
                    last = err
                    continue

                if no_channel(status, text):
                    _note_no_channel(target)
                    last = err
                    continue

                if status in (429, 500, 502, 503) or is_quota(status, text):
                    POOL.note_failure(index)
                    # essa key ja mostrou que nao passa agora: nao adianta
                    # gastar a cadeia inteira repetindo com ela
                    dead.add(token)
                    barrada = True
                last = err

        # ---- fim de uma volta ----
        if not tentou_algo:
            # nenhuma key utilizavel: tenta recarregar do disco algumas vezes
            if keys_recarregadas < 4:
                keys_recarregadas += 1
                try:
                    import keyring
                    fresh = keyring.rotation(retry_dead=True)
                except Exception:
                    fresh = None
                if fresh and load_keys(fresh):
                    POOL.revive()
                    POOL.load(fresh)
                    continue
            time.sleep(_espera_tpm(tentativa))
            tentativa += 1
            continue

        if houve_tpm:
            # o modelo pode voltar em segundos: espera um pouco e recomeca
            # do modelo pedido (tentativa 0) a cada volta completa
            time.sleep(_espera_tpm(tentativa))
        else:
            # falhas comuns (timeout/vazio): anda a cadeia e espera pouco
            time.sleep(0.5)
        tentativa += 1

def no_channel(status, text):
    """Upstream answers this when the model has no provider attached. It is
    about the model, not the key, so retrying with another key is pointless."""
    if status != 503:
        return False
    low = (text or "").lower()
    return ("no available channel" in low or "model_not_found" in low
            or "distributor" in low)

def model_variants(name):
    """The panel lists -free ids while the API lists clean ones, and each one
    works at different times. Try both spellings of the same model."""
    out = [name]
    if name.endswith("-free"):
        out.append(name[:-5])
    else:
        out.append(name + "-free")
    return out

def _note_no_channel(model):
    entry = registry(model)
    entry["nochan"] = entry.get("nochan", 0) + 1
    entry["last_nochan"] = time.time()

def _no_channel_now(model):
    entry = registry(model)
    return (entry.get("nochan", 0) >= 1
            and time.time() - entry.get("last_nochan", 0) < 90)

def _timed_out(model):
    entry = registry(model)
    if entry.get("timeouts", 0) >= 2 and time.time() - entry.get("last_timeout", 0) < 180:
        return True
    return entry.get("empties", 0) >= 2 and time.time() - entry.get("last_empty", 0) < 180

def _note_empty(model):
    entry = registry(model)
    entry["empties"] = entry.get("empties", 0) + 1
    entry["last_empty"] = time.time()

def _note_timeout(model):
    entry = registry(model)
    entry["timeouts"] = entry.get("timeouts", 0) + 1
    entry["last_timeout"] = time.time()

def _note_dead(token):
    try:
        import keyring
        keyring.mark_dead(token)
    except Exception:
        pass

def _note_live(token):
    try:
        import keyring
        keyring.mark_live(token)
    except Exception:
        pass

def notice(model):
    return {"error": {"message": NOTICE,
                      "type": "gambiarra_switching",
                      "code": "gambiarra_switching",
                      "model": model}}
