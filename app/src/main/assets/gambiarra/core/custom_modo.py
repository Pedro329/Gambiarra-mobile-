"""Modo de uso do Custom Provider: FREE ou SALDO.

FREE
    Lista so os modelos gratuitos do upstream (sufixo -free, pricing zero,
    ou campo free=true). Quando o modelo toma rate limit/quota, o pool
    rotaciona para o proximo da cadeia. Nada e removido da base.

SALDO
    Lista todos os modelos e usa o que a pessoa escolher. Quando o
    upstream responde "sem saldo" (insufficient balance, 402, quota
    esgotada), a CONTA e removida da base e o router passa para a
    proxima conta/ provider automaticamente.

A deteccao e por assinatura de erro, porque os gateways compativeis com
OpenAI nao expoem /v1/balance de forma padrao (testado: 404 no
NightRouter). O que sempre aparece e o erro na hora da chamada.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(HERE), "dados")
ARQ_MORTAS = os.path.join(DATA_DIR, "custom_contas_mortas.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

MODO_FREE = "free"
MODO_SALDO = "saldo"
MODOS = (MODO_FREE, MODO_SALDO)

# ------------------------------------------------------ assinaturas de erro
# tudo em minusculo: comparado contra o corpo inteiro da resposta de erro
SEM_SALDO = (
    "insufficient balance",
    "insufficient_quota",
    "insufficient credit",
    "insufficient credits",
    "insufficient_credit",
    "insufficient_credits",
    "insufficient funds",
    "not enough balance",
    "not enough credit",
    "no balance",
    "out of credit",
    "out of credits",
    "you're out of credits",
    "not enough credits",
    "add credits",
    "credit balance is too low",
    "billing hard limit",
    "exceeded your current quota",
    "quota exceeded",
    "saldo insuficiente",
    "sem saldo",
    "without balance",
)

# 402 e o codigo canonico de "pague primeiro"
CODIGO_SEM_SALDO = 402

# rate limit de verdade: NAO remove conta, so troca de modelo/chave
RATE_LIMIT = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "tokens per minute",
    "requests per minute",
    "tpm",
    "rpm",
    "throttl",
    "overloaded",
    "capacity",
)

_lock = threading.Lock()


# ----------------------------------------------------------------- modo
def modo_atual():
    """Lê o modo do custom ativo (free por padrao)."""
    try:
        import providers
        import custom_provider
        nome = providers.nome_atual()
        if not nome.startswith("custom:"):
            # provider fixo com opcoes na aba custom (Bike4Mind)
            if providers.atual().get("na_custom"):
                import provider_fixos
                return provider_fixos.modo_de(nome)
            return MODO_FREE
        p = custom_provider.por_nome(nome)
        if not p:
            return MODO_FREE
        m = (p.get("modo") or MODO_FREE).lower()
        return m if m in MODOS else MODO_FREE
    except Exception:
        return MODO_FREE


def definir_modo(nome_custom, modo):
    """Grava o modo de um custom ou de um provider fixo (free/saldo)."""
    modo = (modo or "").lower()
    if modo not in MODOS:
        return False
    nome = (nome_custom or "").replace("custom:", "")
    try:
        import provider_fixos
        if provider_fixos.e_fixo_na_custom(nome):
            return provider_fixos.definir_modo(nome, modo)
    except Exception:
        pass
    try:
        import custom_provider
        return custom_provider.atualizar_campo(nome_custom, "modo", modo)
    except Exception:
        return False


# ------------------------------------------------------- modelo e free?
def preco_zero(entrada):
    """A entrada de /models diz que o modelo e gratuito?"""
    if not isinstance(entrada, dict):
        return False
    preco = entrada.get("pricing") or {}
    if isinstance(preco, dict) and preco:
        for v in preco.values():
            if isinstance(v, (int, float)):
                if float(v) != 0:
                    return False
            elif isinstance(v, str):
                try:
                    if float(v) != 0:
                        return False
                except ValueError:
                    continue
        return True
    return False


def modelo_free(entrada):
    """Uma entrada de /models e de modelo gratuito?

    Aceita os tres sinais que os gateways usam: sufixo -free, pricing
    zerado em todas as chaves, ou o campo booleano free.
    """
    if isinstance(entrada, str):
        return entrada.endswith("-free") or entrada.endswith(":free")
    if not isinstance(entrada, dict):
        return False
    mid = str(entrada.get("id") or entrada.get("name") or "")
    if mid.endswith("-free") or mid.endswith(":free"):
        return True
    if entrada.get("free") is True:
        return True
    if isinstance(entrada.get("is_free"), bool) and entrada["is_free"]:
        return True
    # alguns gateways expoem "tier"/"group"
    for campo in ("tier", "group", "plan"):
        valor = str(entrada.get(campo) or "").lower()
        if valor in ("free", "gratis", "grátis"):
            return True
    return preco_zero(entrada)


def id_do_modelo(entrada):
    if isinstance(entrada, str):
        return entrada.strip()
    if isinstance(entrada, dict):
        v = entrada.get("id") or entrada.get("name")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


# ------------------------------------------------------------ listagem
def listar(prov, key="", modo=None, timeout=20, forcar=False):
    """Modelos do custom conforme o modo.

    modo free  -> so os gratuitos
    modo saldo -> todos
    Devolve (lista_de_ids, bruto_do_upstream).
    """
    if not isinstance(prov, dict):
        prov = {"base": str(prov), "keys": []}
    modo = (modo or prov.get("modo") or MODO_FREE).lower()
    if modo not in MODOS:
        modo = MODO_FREE

    # respeita o cache breve para nao pagar /models a cada chamada
    if not key:
        keys = prov.get("keys") or []
        key = keys[0] if keys else ""

    base = (prov.get("base") or "").rstrip("/")
    if not base:
        return [], []
    # gateways que nao seguem o padrao OpenAI tem outro caminho de /models
    try:
        import adaptador
        modo_gw = adaptador.detectar(base, prov.get("adapter", ""))
        url_models = adaptador.url_models(base, modo_gw)
    except Exception:
        url_models = base + "/models"
    # cache por base+modo: o adapter muda a url, entao entra na chave
    chave_cache = "%s|%s|%s" % (url_models, modo, bool(key))
    if not forcar:
        with _lock:
            item = _cache.get(chave_cache)
            if item and time.time() - item[0] < 120:
                return list(item[1]), item[2]
    req = urllib.request.Request(url_models)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    if key:
        req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            corpo = r.read(800000).decode("utf-8", "replace")
        dados = json.loads(corpo)
    except Exception:
        return [], []

    itens = dados.get("data") if isinstance(dados, dict) else dados
    if not isinstance(itens, list):
        itens = dados.get("models") if isinstance(dados, dict) else []
    if not isinstance(itens, list):
        itens = []

    ids = []
    for it in itens:
        mid = id_do_modelo(it)
        if not mid:
            continue
        if modo == MODO_FREE and not modelo_free(it):
            continue
        ids.append(mid)
    ids = sorted(set(ids))

    with _lock:
        _cache[chave_cache] = (time.time(), list(ids), itens)
    return ids, itens


_cache = {}


def modelos_para_tela(prov, key=""):
    """(ids, modo) pronto para desenhar a lista do router."""
    modo = (prov.get("modo") or MODO_FREE).lower()
    ids, _bruto = listar(prov, key, modo)
    return ids, modo


# ------------------------------------------------- erro = sem saldo?
def e_sem_saldo(status, texto):
    """O upstream disse que a conta nao tem saldo?"""
    if status == CODIGO_SEM_SALDO:
        return True
    low = (texto or "").lower()
    if any(s in low for s in RATE_LIMIT):
        return False      # eh limite de taxa, nao falta de dinheiro
    return any(s in low for s in SEM_SALDO)


def e_rate_limit(status, texto):
    """So limite de taxa: troca de modelo/chave, NAO mata a conta."""
    low = (texto or "").lower()
    if any(s in low for s in RATE_LIMIT):
        return True
    return status == 429 and not e_sem_saldo(status, texto)


# ------------------------------------------------- contas mortas (db)
def _ler_mortas():
    try:
        with open(ARQ_MORTAS, encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar_mortas(dados):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = ARQ_MORTAS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=1, ensure_ascii=False)
        os.replace(tmp, ARQ_MORTAS)
        return True
    except OSError:
        return False


def morta(nome_custom, key):
    """Essa conta ja foi marcada como sem saldo?"""
    dados = _ler_mortas()
    return key in (dados.get(nome_custom) or {})


def marcar_morta(nome_custom, key, motivo=""):
    """Remove a conta (key) da base e registra o motivo."""
    nome = (nome_custom or "").replace("custom:", "")
    dados = _ler_mortas()
    dados.setdefault(nome, {})[key] = {
        "quando": time.strftime("%Y-%m-%d %H:%M:%S"),
        "motivo": (motivo or "")[:180],
    }
    _gravar_mortas(dados)
    # tira da lista do provider (custom ou fixo com keys proprias)
    removida = False
    try:
        import provider_fixos
        if provider_fixos.e_fixo_na_custom(nome):
            removida = provider_fixos.remover_key(nome, key)
    except Exception:
        pass
    if not removida:
        try:
            import custom_provider
            custom_provider.remover_key(nome_custom, key)
        except Exception:
            pass
    with _lock:
        _cache.clear()
    return True


def reviver(nome_custom, key=None):
    """Devolve a(s) conta(s) para a lista (sai do cemiterio)."""
    dados = _ler_mortas()
    if key:
        dados.get(nome_custom, {}).pop(key, None)
    else:
        dados.pop(nome_custom, None)
    return _gravar_mortas(dados)


def listar_mortas(nome_custom=None):
    dados = _ler_mortas()
    if nome_custom:
        return dados.get(nome_custom) or {}
    return dados


def keys_vivas(nome_custom):
    """Keys do provider que ainda nao foram marcadas como sem saldo."""
    nome = (nome_custom or "").replace("custom:", "")
    try:
        mortas = set((_ler_mortas().get(nome) or {}).keys())
        import provider_fixos
        if provider_fixos.e_fixo_na_custom(nome):
            return [k for k in provider_fixos.keys_de(nome) if k not in mortas]
        import custom_provider
        p = custom_provider.por_nome(nome)
        if not p:
            return []
        return [k for k in p["keys"] if k not in mortas]
    except Exception:
        return []


if __name__ == "__main__":
    print("modo atual:", modo_atual())
    for st, txt in ((402, "insufficient balance"),
                    (429, "rate limit reached, too many requests"),
                    (400, "exceeded your current quota"),
                    (401, "invalid api key")):
        print("  %s %-42s sem_saldo=%-5s rate_limit=%s"
              % (st, txt[:42], e_sem_saldo(st, txt), e_rate_limit(st, txt)))
