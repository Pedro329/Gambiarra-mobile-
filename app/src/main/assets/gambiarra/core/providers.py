"""Providers - catalogo de backends que o hub sabe usar.

O app deixa de ser "o cliente do NightRouter" e passa a ser um HUB:
o usuario escolhe no CONFIG qual provider fala com o upstream, e o
resto (rotas, TPM, farm, proxy) continua igual.

Cada provider declara:
  nome      - id usado no config.json ("provider")
  titulo    - o que aparece na tela
  base      - base url compativel com OpenAI (sem barra no fim)
  precisa   - o que ele exige para funcionar:
              "key" -> usa as keys do Farm Key / keys.json
  testa     - caminho para provar que o provider responde
  nota      - aviso curto mostrado na escolha
"""

import json
import os
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONF_FILE = os.path.join(HERE, "..", "dados", "config.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

PROVIDERS = [
    {
        "nome": "nightrouter",
        "titulo": "NightRouter",
        "base": "https://api.nightrouter.ai/v1",
        "precisa": "key",
        "testa": "/models",
        "nota": "usa as keys do Farm Key",
    },
    {
        # Provider FIXO, igual ao NightRouter: nao da para excluir nem
        # trocar a base url. A diferenca e que ele aparece na aba de
        # Custom Providers com as opcoes dele (keys, testar, modo).
        "nome": "bike4mind",
        "titulo": "Bike4Mind",
        "base": "https://app.bike4mind.com/api/ai/v1",
        "precisa": "key",
        "testa": "/api/v1/models",
        "nota": "fixo - keys proprias na aba Custom Providers",
        "fixo": True,
        "adapter": "b4m-chat",
        "na_custom": True,
    },
]
PADRAO = "nightrouter"
PREFIXO_CUSTOM = "custom:"


def _com_custom():
    """Catalogo fixo + os custom providers salvos pelo usuario.

    Os custom entram com o nome "custom:<id>" para nunca colidir com os
    fixos, e usam a mesma rotacao de keys do NightRouter.
    """
    saida = list(PROVIDERS)
    try:
        import custom_provider
        for p in custom_provider.carregar():
            saida.append({
                "nome": PREFIXO_CUSTOM + p["nome"],
                "titulo": p["titulo"],
                "base": p["base"],
                "precisa": "key",
                "testa": "/models",
                "nota": "custom - %d keys rotacionando" % len(p["keys"]),
                "custom": True,
                "modelo": p.get("modelo") or "",
            })
    except Exception:
        pass
    return saida


def catalogo():
    """Todos os providers disponiveis (fixos + custom)."""
    return _com_custom()


def _mapa():
    return {p["nome"]: p for p in _com_custom()}


# --------------------------------------------------------------- config
def _ler_conf():
    try:
        with open(CONF_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _gravar_conf(conf):
    try:
        os.makedirs(os.path.dirname(CONF_FILE), exist_ok=True)
        with open(CONF_FILE, "w", encoding="utf-8") as f:
            json.dump(conf, f, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


def nome_atual():
    """Id do provider ativo (pode ser "custom:<id>")."""
    conf = _ler_conf()
    return conf.get("provider") or PADRAO


def atual():
    """Provider escolhido no config.json (ou o padrao)."""
    mapa = _mapa()
    return mapa.get(nome_atual(), mapa[PADRAO])


def base_url_atual():
    """Base url do provider ativo."""
    mapa = _mapa()
    nome = nome_atual()
    prov = mapa.get(nome, mapa[PADRAO])
    return prov["base"]


def precisa_key():
    """True se o provider ativo usa as keys do Farm Key."""
    return atual()["precisa"] == "key"


def key_propria():
    """Key que o usuario colou para o provider proprio (se houver)."""
    conf = _ler_conf()
    return conf.get("provider_key") or ""


def definir(nome):
    """Grava o provider escolhido. O app precisa reiniciar depois."""
    if nome not in _mapa():
        return False
    conf = _ler_conf()
    conf["provider"] = nome
    ok = _gravar_conf(conf)
    if ok:
        # troca de provider invalida o cache de keys na hora. Sem isto o
        # keyring servia as keys do provider anterior por ate 2s e o
        # router continuava mandando requisicao para o NightRouter.
        try:
            import keyring
            keyring.reload(force=True)
        except Exception:
            pass
    return ok


def rotulo(prov=None):
    prov = prov or atual()
    return prov["titulo"]


# ---------------------------------------------------------------- teste
def testar(prov, key="", base=""):
    """(ok, mensagem): o provider responde de verdade?

    Faz um GET em /models, que todo gateway compativel com OpenAI tem.
    Diferencia "nao respondeu" de "respondeu mas recusou a key".
    """
    url = (base or prov["base"]).rstrip("/") + prov.get("testa", "/models")
    if not url.startswith("http"):
        return False, "url invalida"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    if key:
        req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            corpo = r.read(200000).decode("utf-8", "replace")
        try:
            dados = json.loads(corpo)
            n = len(dados.get("data") or dados.get("models") or [])
        except ValueError:
            n = 0
        return True, "%d modelos" % n if n else "respondeu"
    except urllib.error.HTTPError as e:
        texto = ""
        try:
            texto = e.read(300).decode("utf-8", "replace")
        except Exception:
            pass
        low = texto.lower()
        if "free usage limit" in low:
            return False, "limite do plano free atingido"
        if e.code in (401, 403):
            return False, "precisa de key valida"
        if e.code == 404:
            return False, "endpoint nao encontrado"
        return False, "HTTP %d" % e.code
    except Exception as e:
        return False, "sem conexao: %s" % type(e).__name__


def modelos_do_provider(prov=None, key="", base=""):
    """Lista de ids que o provider expoe (vazio se nao der)."""
    prov = prov or atual()
    url = (base or prov["base"]).rstrip("/") + "/models"
    if not url.startswith("http"):
        return []
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    if key:
        req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            dados = json.loads(r.read(400000).decode("utf-8", "replace"))
    except Exception:
        return []
    itens = dados.get("data") or dados.get("models") or []
    saida = []
    for m in itens:
        if isinstance(m, dict):
            ident = m.get("id") or m.get("name")
            if ident:
                saida.append(str(ident))
        elif isinstance(m, str):
            saida.append(m)
    return sorted(saida)
