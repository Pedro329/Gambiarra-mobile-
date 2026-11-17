import os
import random
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import farmer
import proxies
import tui

BASE_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(BASE_DIR, "dados")
KEYS_FILE = os.path.join(DATA_DIR, "keys.json")
STATE_FILE = os.path.join(DATA_DIR, "farm_state.json")
DEFAULT_THREADS = 12
MAX_THREADS = 32
MAX_WORKERS = 8

class ProxyPool:

    def __init__(self, want=6, conf=None):
        self.want = want
        self.conf = conf if isinstance(conf, dict) else {}
        self.lock = threading.Lock()
        self.items = []
        self.seen = set()
        self.refreshing = False
        self._topping = False
        self.cycle = 0
        self.dry = 0
        self.last_took = 0.0
        # "nenhum" = conexao direta; nao faz sentido buscar proxy nenhum
        if self.modo() != "nenhum":
            self.spawn()

    def modo(self):
        """Modo de proxy escolhido no CONFIG."""
        return (self.conf.get("proxy_modo") or "auto").lower()

    def direto(self):
        return self.modo() == "nenhum"

    def fixo(self):
        """URL fixa quando o modo e rotativa (proxy premium)."""
        if self.modo() != "rotativa":
            return ""
        return (self.conf.get("proxy_url") or "").strip()

    def spawn(self):
        with self.lock:
            if self.refreshing:
                return
            self.refreshing = True
        threading.Thread(target=self._fill, daemon=True).start()

    def _fill(self):
        started = time.time()
        try:
            modo = self.modo()
            # --- rotativa: uma URL fixa, ja configurada, nao coleta nada
            if modo == "rotativa":
                url = self.fixo()
                with self.lock:
                    if url and not self.items:
                        self.items.append((url, 0))
                    self.cycle += 1
                return
            # --- nenhum: conexao direta, nada a fazer
            if modo == "nenhum":
                with self.lock:
                    self.cycle += 1
                return
            # --- gerador [BETA]: fonte fresca do ProxyScrape + checker
            if modo == "gerador":
                try:
                    import gerador_proxy
                    alvo = max(self.want * 2, 20)
                    vivos, _bruto = gerador_proxy.gerar(
                        target=alvo,
                        time_budget=float(self.conf.get("proxy_gerador_budget", 25)))
                    with self.lock:
                        conhecidos = {p for p, _ in self.items}
                        for proxy, ms in vivos:
                            if proxy in self.seen or proxy in conhecidos:
                                continue
                            if len(self.items) >= self.want * 4:
                                break
                            self.items.append((proxy, 0))
                            conhecidos.add(proxy)
                        self.cycle += 1
                        self.dry = 0 if self.items else self.dry + 1
                    return
                except Exception:
                    # cai no comportamento padrao se o gerador falhar
                    pass
            want = max(self.want * 4, 24)
            # seed with whatever we already had, so the farm never sits on
            # "buscando proxies" with an empty hand
            cached = proxies.load()
            with self.lock:
                known = {p for p, _ in self.items}
                for proxy, _ in cached:
                    if proxy in self.seen or proxy in known:
                        continue
                    if len(self.items) >= want:
                        break
                    self.items.append((proxy, 0))
                    known.add(proxy)
            good = proxies.refresh(target=want)
            if len(good) < self.want:
                # keep hunting in the background rather than blocking here
                threading.Thread(target=self._top_up, daemon=True).start()
            if len(good) < want:
                for proxy, ms in proxies.load():
                    if proxy not in {p for p, _ in good}:
                        good.append((proxy, ms))
            with self.lock:
                known = {p for p, _ in self.items}
                for proxy, _ in good:
                    if proxy in self.seen or proxy in known:
                        continue
                    if len(self.items) >= want:
                        break
                    self.items.append((proxy, 0))
                    known.add(proxy)
                self.cycle += 1
                self.dry = 0 if self.items else self.dry + 1
        finally:
            with self.lock:
                self.refreshing = False
                self.last_took = time.time() - started

    def _top_up(self):
        if self._topping:
            return
        self._topping = True
        try:
            proxies.top_up(target=max(40, self.want * 4))
        except Exception:
            pass
        finally:
            self._topping = False

    def need(self):
        with self.lock:
            return len(self.items) < max(2, self.want)

    def empty(self):
        with self.lock:
            return not self.items

    def forgive(self, limit=60):
        """A proxy that worked before must be allowed to come back. Without
        this the seen set grows forever and the pool starves."""
        with self.lock:
            if len(self.seen) > limit:
                keep = {p for p, _ in self.items}
                self.seen = {p for p in self.seen if p in keep}

    def take(self):
        # --- conexao direta: o farm usa o IP da propria maquina
        if self.modo() == "nenhum":
            return None
        # --- rotativa: sempre a URL configurada, sem rotacionar
        if self.modo() == "rotativa":
            return self.fixo() or None
        with self.lock:
            while self.items:
                proxy, _ = self.items.pop(0)
                if proxy not in self.seen:
                    self.seen.add(proxy)
                    return proxy
            return None

    def ok(self, proxy):
        if not proxy:
            return
        with self.lock:
            self.seen.add(proxy)

    def free(self, proxy):
        if not proxy:
            return
        with self.lock:
            if len(self.items) < self.want:
                self.items.append((proxy, 1))

    def drop(self, proxy):
        if not proxy:
            return
        with self.lock:
            self.seen.add(proxy)

    def count(self):
        with self.lock:
            return len(self.items)

    def status(self):
        with self.lock:
            return {"items": len(self.items), "refreshing": self.refreshing,
                    "cycle": self.cycle, "dry": self.dry,
                    "took": self.last_took}

class Farm:

    def __init__(self, store, threads, target=None, conf=None):
        self.store = store
        self.threads = max(1, min(MAX_THREADS, threads))
        self.conf = conf if isinstance(conf, dict) else {}
        self.target = target or 0
        self.baseline = store.count()
        self.idle = self.threads
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.done = 0
        self.ok = 0
        self.rate_limit = 0
        self.other = 0
        self.proxy_fail = 0
        self.last_error = ""
        self.last_status = None
        self.last_proxy = ""
        self.took = 0.0
        self.started = time.time()
        self.last_ok_at = time.time()
        self.workers = []
        self.proxies = ProxyPool(want=max(12, self.threads * 3), conf=self.conf)
        self.job_threads = max(1, min(self.threads, MAX_WORKERS))

    def running(self):
        return bool(self.workers) and not self.stop.is_set()

    def start(self):
        self.started = time.time()
        pool = self.proxies
        # modo direto/rotativa nao depende de coleta: nao espera o pool
        if not pool.direto() and pool.modo() != "rotativa":
            while not self.stop.is_set():
                if pool.count() >= 1 or pool.cycle > 0:
                    break
                self.stop.wait(0.25)
        have = max(1, min(self.threads, MAX_WORKERS))
        for _ in range(have):
            t = threading.Thread(target=self._loop, daemon=True)
            t.start()
            self.workers.append(t)

    def halt(self):
        self.stop.set()

    def _loop(self):
        while not self.stop.is_set():
            if self.target and self.store.count() - self.baseline >= self.target:
                self.stop.set()
                break
            with self.lock:
                blocking = self.rate_limit >= 2 and self.ok == 0
            if blocking and self.idle:
                self.stop.wait(60)
                with self.lock:
                    self.rate_limit = 0
                continue
            need = getattr(self.proxies, "need", None)
            if callable(need) and need() and not self.proxies.direto():
                self.proxies.spawn()
            proxy = self.proxies.take()
            if proxy is None:
                # modo "sem proxy": o farm continua com o IP da maquina.
                # Antes isto caia no continue e o farm nunca andava,
                # ignorando a escolha da pessoa.
                if not self.proxies.direto():
                    self.proxies.spawn()
                    if not self.proxies.cycle:
                        self.stop.wait(0.3)
                        continue
            attempt = self.store.count() + 1
            t0 = time.time()
            try:
                record, err = farmer.harvest_one(attempt, proxy=proxy)
            except Exception as exc:
                record, err = None, "excecao: %s" % exc
            took = time.time() - t0
            net_dead = bool(record is None and err and
                            ("conexao:" in err or "HTTP 0:" in err))
            if net_dead:
                self.proxies.drop(proxy)
            else:
                self.proxies.free(proxy)
            with self.lock:
                self.done += 1
                self.took = took
                self.last_proxy = proxy
                self.last_status = record is not None
                if record:
                    self.ok += 1
                    self.rate_limit = 0
                    self.last_ok_at = time.time()
                elif net_dead:
                    self.proxy_fail += 1
                    self.last_error = "proxy morto: " + proxy
                elif err and "429" in err:
                    self.rate_limit += 1
                    self.last_error = "rate limit: " + proxy
                else:
                    self.other += 1
                    self.last_error = err or "falhou"
            if record:
                if not self.target or \
                        self.store.count() - self.baseline < self.target:
                    self.store.add(record)
                    self.proxies.forgive()
                continue
            with self.lock:
                streak = min(4, self.rate_limit)
            self.stop.wait(min(4.0, 0.15 + streak * 0.5))
            with self.lock:
                self.idle -= 1

    def snapshot(self):
        with self.lock:
            elapsed = max(0.5, time.time() - self.started)
            return {
                "done": self.done, "ok": self.ok, "rl": self.rate_limit,
                "other": self.other, "err": self.last_error,
                "status": self.last_status, "took": self.took,
                "proxy": self.last_proxy, "pfail": self.proxy_fail,
                "proxies": self.proxies.count(),
                "refreshing": self.proxies.refreshing,
                "cycle": self.proxies.cycle,
                "speed": self.ok / elapsed,
                "idle": time.time() - self.last_ok_at,
                "total": self.store.count(),
                "last": self.last_error,
            }

    def live_keys(self):
        return self.store.count()

def read_state():
    import json
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return int(data.get("threads", DEFAULT_THREADS))
    except (OSError, ValueError, TypeError):
        return DEFAULT_THREADS

def _ler_conf():
    """Config do app (provider, proxy_modo, proxy_url...)."""
    for caminho in (os.path.join(DATA_DIR, "config.json"),
                    os.path.join(BASE_DIR, "dados", "config.json")):
        try:
            with open(caminho, encoding="utf-8") as f:
                dados = json.load(f)
            if isinstance(dados, dict):
                return dados
        except (OSError, ValueError):
            continue
    return {}


def write_state(threads):
    import json
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"threads": threads}, f)
    except OSError:
        pass

class Panel:
    def __init__(self, conf=None):
        self.term = tui.Term()
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
        except OSError:
            pass
        self.store = farmer.KeyStore(KEYS_FILE)
        self.job = None
        # conf vem do app; se nao vier, le do disco. Sem isto o painel
        # do farm ignorava o modo de proxy escolhido no CONFIG.
        self.conf = conf if isinstance(conf, dict) else _ler_conf()
        self.threads_text = str(read_state())
        self.editing = False
        self.toast = ""
        self.toast_at = 0.0
        self.shown = None

    def say(self, text):
        self.toast = text
        self.toast_at = time.time()

    def threads(self):
        try:
            value = int(self.threads_text or DEFAULT_THREADS)
        except ValueError:
            value = DEFAULT_THREADS
        return max(1, min(MAX_THREADS, value))

    def begin(self):
        if self.job and self.job.running():
            return
        # rele a config a cada inicio: a pessoa pode ter trocado o proxy
        self.conf = _ler_conf() or self.conf
        self.job = Farm(self.store, self.threads(), conf=self.conf)
        self.job.start()
        self.say("rodando com %d threads" % self.threads())

    def halt(self):
        if self.job:
            self.job.halt()
            self.say("parado - o que foi gerado continua salvo")

    def render(self):
        cols_px, rows_px = self.term.size()
        cols, inner = tui.layout(cols_px, rows_px)
        snap = self.job.snapshot() if self.job else None
        lines = []

        head = (tui.ORANGE + tui.BOLD + "GAMBIARRA-INFINITE  -  FARM" + tui.RESET)
        link = tui.DIM + farmer.DISCORD + tui.RESET
        lines.append(tui.box_top(cols, "FARM", tui.ORANGE_DK))
        lines.append(tui.pair(head, link, inner))
        lines.append(tui.box_sep(inner))

        running = bool(self.job and self.job.running())
        dot = (tui.GREEN + tui.GLYPHS.dot_on + tui.RESET if running
               else tui.DIM + tui.GLYPHS.dot_off + tui.RESET)
        state = ("RODANDO" if running else "PARADO")
        lines.append(tui.box_row(
            dot + " " + (tui.GREEN if running else tui.DIM) + state + tui.RESET
            + tui.DIM + "    arquivo: " + tui.RESET + KR(KEYS_FILE), inner))
        lines.append(tui.pair(
            tui.GRAY + "keys geradas: " + tui.RESET + tui.ORANGE + tui.BOLD
            + str(self.store.count()) + tui.RESET,
            tui.DIM + "B abre o Chrome anonimo" + tui.RESET, inner))
        lines.append(tui.box_sep(inner))

        if snap:
            mark = ("OK" if snap["status"] else "FALHOU")
            colour = tui.GREEN if snap["status"] else tui.RED
            last = snap["err"].replace("\n", " ")[:max(8, inner - 46)] if snap["err"] else ""
            lines.append(tui.pair(
                tui.GRAY + "ultima tentativa: " + tui.RESET + colour + mark + tui.RESET
                + tui.DIM + "  %.1fs  via %s" % (snap["took"], snap["proxy"] or "-")
                + tui.RESET,
                tui.DIM + "tent %d  ok %d  429 %d  proxy morto %d"
                % (snap["done"], snap["ok"], snap["rl"], snap["pfail"]) + tui.RESET,
                inner))
            if last:
                lines.append(tui.box_row(tui.RED + "   " + last + tui.RESET, inner))
            else:
                lines.append(tui.box_row("", inner))
            speed = (tui.GRAY + "ritmo " + tui.RESET + tui.WHITE
                     + "%.2f keys/s" % snap["speed"] + tui.RESET
                     + tui.DIM + "   proxies: " + tui.RESET
                     + tui.WHITE + str(snap["proxies"]) + tui.RESET + tui.DIM
                     + (" (procurando...)" if snap["refreshing"]
                        else " (rodada %d)" % snap["cycle"]) + tui.RESET)
            idle = ""
            if snap["idle"] > 30 and running:
                idle = (tui.YELLOW + "   sem key há %ds - o site está recusando"
                        % int(snap["idle"]) + tui.RESET)
            lines.append(tui.box_row(speed + idle, inner, pad=2))
            lines.append(tui.box_sep(inner))
        else:
            lines.append(tui.box_row(
                tui.DIM + "ENTER comeca. cada conta sai por um proxy free "
                "diferente, o mais rapido." + tui.RESET, inner))
            lines.append(tui.box_sep(inner))

        label = tui.GRAY + "Threads: " + tui.RESET
        if self.editing:
            field = (tui.BG_ORANGE + " " + (self.threads_text or " ")
                     + tui.GLYPHS.cursor + " " + tui.RESET)
            hint = tui.DIM + "  0-9 digita  ENTER confirma  ESC cancela" + tui.RESET
        else:
            field = tui.WHITE + tui.BOLD + " " + str(self.threads()) + " " + tui.RESET
            hint = tui.DIM + "  T para editar" + tui.RESET
        lines.append(tui.box_row(label + field + hint, inner))

        table = [("PC fraco", "2-4 GB RAM, i3 antigo", "4"),
                 ("PC entrada", "4-8 GB, Ryzen 3", "8"),
                 ("PC normal", "8-16 GB, Ryzen 5", "12"),
                 ("PC forte", "16-32 GB, Ryzen 7", "20"),
                 ("PC super",
                  "32 GB+, Ryzen 9 / i9", "32")]
        lines.append(tui.box_sep(inner))
        header = (tui.DIM + "%-11s %-22s %s" % ("MAQUINA", "EXEMPLO", "THREADS")
                  + tui.RESET)
        lines.append(tui.box_row(header, inner, pad=3))
        for name, spec, rec in table:
            col = tui.ORANGE if str(self.threads()) == rec else tui.GRAY
            mark = " <-" if str(self.threads()) == rec else ""
            lines.append(tui.box_row(
                tui.GRAY + "%-11s" % name + tui.DIM + " %-22s" % spec + tui.RESET
                + col + "%4s" % rec + tui.RESET + tui.ORANGE + mark + tui.RESET,
                inner, pad=3))
        lines.append(tui.box_sep(inner))

        keys = (tui.WHITE + "ENTER" + tui.RESET + tui.DIM + " comecar   " + tui.RESET
                + tui.WHITE + "T" + tui.RESET + tui.DIM + " threads   " + tui.RESET
                + tui.WHITE + "P" + tui.RESET + tui.DIM + " parar   " + tui.RESET
                + tui.WHITE + "B" + tui.RESET + tui.DIM + " chrome anon   " + tui.RESET
                + tui.WHITE + "K" + tui.RESET + tui.DIM + " keys   " + tui.RESET
                + tui.WHITE + "Q" + tui.RESET + tui.DIM + " sair" + tui.RESET)
        lines.append(tui.box_row(keys, inner))
        lines.append(tui.box_bottom(inner, tui.ORANGE_DK))

        if self.toast and time.time() - self.toast_at < 4:
            lines.append(tui.ORANGE + "  " + self.toast[: max(10, inner - 2)] + tui.RESET)
        while len(lines) < rows_px - 1:
            lines.append("")
        return tui.screen(lines[: rows_px - 1], cols_px)

    def keys_screen(self):
        cols_px, rows_px = self.term.size()
        cols, inner = tui.layout(cols_px, rows_px)
        entries = self.store.entries()[-14:]
        lines = [tui.box_top(cols, "ULTIMAS KEYS", tui.ORANGE_DK),
                 tui.box_row(tui.DIM + "arquivo: " + tui.RESET + KR(KEYS_FILE), inner)]
        for e in entries:
            lines.append(tui.box_row(
                tui.GRAY + "#%-4s" % str(e.get("attempt", "?")) + tui.RESET
                + tui.WHITE + " " + str(e.get("user", "-"))[:26] + tui.RESET
                + tui.DIM + "  " + str(e.get("key", ""))[:24] + "..." + tui.RESET,
                inner))
        if not entries:
            lines.append(tui.box_row(tui.DIM + "nenhuma key ainda" + tui.RESET, inner))
        lines.append(tui.box_row(tui.DIM + "qualquer tecla volta" + tui.RESET, inner))
        lines.append(tui.box_bottom(inner, tui.ORANGE_DK))
        while len(lines) < rows_px - 1:
            lines.append("")
        rows = tui.screen(lines[: rows_px - 1], cols_px)
        self.term.write(tui.full_frame(rows))
        self.term.flush()
        self.term.read_key_blocking()
        self.paint(force=True)

    def paint(self, force=False):
        rows = self.render()
        body = [tui.strip(r) for r in rows]
        if not force and body == self.shown:
            return
        self.shown = body
        self.term.write(tui.full_frame(rows) if force else tui.frame(rows))
        self.term.flush()

    def run(self):
        self.term.enter()
        try:
            self.paint(force=True)
            while True:
                key = self.term.read_key_blocking()
                if self.editing:
                    if key == tui.KEY_ENTER:
                        self.editing = False
                        write_state(self.threads())
                        if self.job and self.job.running():
                            self.job.halt()
                            self.job = None
                            self.say("threads salvas - ENTER comeca de novo")
                    elif key == tui.KEY_ESC:
                        self.editing = False
                    elif key == tui.KEY_BACKSPACE:
                        self.threads_text = self.threads_text[:-1]
                    elif isinstance(key, str) and len(key) == 1 and key.isdigit():
                        if len(self.threads_text) < 3:
                            self.threads_text += key
                    self.paint()
                    continue
                if key == tui.KEY_ENTER:
                    self.begin()
                elif key in ("t", "T"):
                    self.editing = True
                    self.threads_text = ""
                elif key in ("p", "P"):
                    self.halt()
                elif key in ("i", "I", "k", "K"):
                    self.keys_screen()
                elif key in ("b", "B"):
                    threading.Thread(target=self.anon_browser, daemon=True).start()
                elif key in ("q", "Q"):
                    self.halt()
                    break
                self.paint()
        finally:
            self.term.leave()

    def anon_browser(self):
        import browser
        self.say("abrindo Chrome anonimo (perfil novo)...")
        proc = browser.open_incognito()
        if proc is None:
            self.say("Chrome/Edge nao encontrado")
            return
        self.say("Chrome anonimo aberto - logue e crie a conta")

def KR(path):
    return tui.WHITE + path + tui.RESET

def main():
    if not sys.stdout.isatty():
        return headless()
    Panel().run()
    print()
    print("  keys.json: %s" % KEYS_FILE)
    print("  total: %d" % farmer.KeyStore(KEYS_FILE).count())
    return 0

def headless():
    threads = read_state()
    store = farmer.KeyStore(KEYS_FILE)
    job = Farm(store, threads, conf=_ler_conf())
    job.start()
    print("  farmer headless: %d threads, saida em %s" % (threads, KEYS_FILE))
    try:
        while True:
            time.sleep(5)
            s = job.snapshot()
            print("  keys=%d tentativas=%d ok=%d 429=%d outras=%d %.2f/s"
                  % (s["total"], s["done"], s["ok"], s["rl"], s["other"], s["speed"]))
    except KeyboardInterrupt:
        job.halt()
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
