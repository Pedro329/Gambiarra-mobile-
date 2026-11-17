"""Keys dos providers FIXOS que aparecem na aba de Custom Providers.

O NightRouter usa as keys do Farm (keys.json). O Bike4Mind e fixo como o
NightRouter - nao da para excluir nem trocar a base - mas as keys dele sao
proprias e ficam aqui, com a mesma rotacao e o mesmo cemiterio de contas
sem saldo dos custom providers.

Grava em dados/provider_keys.json:
    {"bike4mind": ["b4m_live_...", "b4m_live_..."]}
"""
import json
import os
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(HERE), "dados")
ARQ = os.path.join(DATA_DIR, "provider_keys.json")

_lock = threading.Lock()
_cache = {"at": 0.0, "dados": {}}

# providers fixos que ficam na aba custom
FIXOS_NA_CUSTOM = ("bike4mind",)


def _limpar(k):
    if not isinstance(k, str):
        return ""
    return k.strip().strip('"\'').strip()


def carregar(forcar=False):
    with _lock:
        if not forcar and time.time() - _cache["at"] < 2.0:
            return dict(_cache["dados"])
        try:
            with open(ARQ, encoding="utf-8") as f:
                dados = json.load(f)
        except (OSError, ValueError):
            dados = {}
        if not isinstance(dados, dict):
            dados = {}
        saida = {}
        for nome, keys in dados.items():
            if not isinstance(nome, str):
                continue
            if nome.startswith("_modo:"):
                # marcador de modo, nao e lista de keys
                saida[nome] = str(keys or "saldo").lower()
                continue
            if isinstance(keys, str):
                keys = [keys]
            limpas = [_limpar(k) for k in (keys or [])]
            saida[nome] = [k for k in limpas if k]
        _cache["dados"] = saida
        _cache["at"] = time.time()
        return dict(saida)


def _gravar(dados, proteger=True):
    """Grava as keys. Com proteger=True nunca perde key existente."""
    if proteger:
        atual = carregar(forcar=True)
        for nome, antigas in atual.items():
            # _modo:<nome> guarda uma STRING ("free"/"saldo"), nao uma
            # lista. Iterar string daria caractere por caractere e
            # corromperia o arquivo inteiro. Funde so listas.
            if nome.startswith("_modo:") or isinstance(antigas, str):
                continue
            novas = dados.get(nome)
            if not isinstance(novas, list):
                novas = []
            faltando = [k for k in antigas if k not in novas]
            if faltando:
                dados[nome] = list(novas) + faltando
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = ARQ + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)
        os.replace(tmp, ARQ)
        _cache["at"] = 0.0
        return True
    except OSError:
        return False


def keys_de(nome):
    return list(carregar().get(nome) or [])


def adicionar(nome, keys):
    """Acrescenta keys e devolve o total."""
    dados = carregar(forcar=True)
    atuais = dados.get(nome) or []
    for k in keys or []:
        k = _limpar(k)
        if k and k not in atuais:
            atuais.append(k)
    dados[nome] = atuais
    _gravar(dados)
    return len(atuais)


def remover_key(nome, key):
    dados = carregar(forcar=True)
    atuais = dados.get(nome) or []
    if key not in atuais:
        return False
    dados[nome] = [k for k in atuais if k != key]
    _gravar(dados, proteger=False)   # remocao intencional
    return True


def limpar(nome):
    dados = carregar(forcar=True)
    dados[nome] = []
    _gravar(dados, proteger=False)


def e_fixo_na_custom(nome):
    return (nome or "").replace("custom:", "") in FIXOS_NA_CUSTOM


# ------------------------------------------------------------- modo
def modo_de(nome):
    """free | saldo do provider fixo."""
    dados = carregar()
    modo = str(dados.get("_modo:" + nome) or "saldo").lower()
    return modo if modo in ("free", "saldo") else "saldo"


def definir_modo(nome, modo):
    modo = (modo or "").lower()
    if modo not in ("free", "saldo"):
        return False
    dados = carregar(forcar=True)
    dados["_modo:" + nome] = modo
    return _gravar(dados)
