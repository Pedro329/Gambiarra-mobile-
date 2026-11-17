"""Custom Provider - base url propria com rotacao de keys e contexto.

Ideia: a pessoa informa UMA base url compativel com OpenAI, adiciona as
keys que tiver para ela, e o programa passa a rotacionar essas keys
exatamente como faz com o NightRouter (mesma fila, mesmos cooldowns,
mesma troca quando a key estoura).

Cada provider custom fica salvo em dados/custom_providers.json:

    {
      "nome": "meu-gateway",          # id curto, sem espaco
      "titulo": "Meu Gateway",        # rotulo na tela
      "base": "https://x/v1",         # sem barra no fim
      "modelo": "gpt-4o-mini",        # opcional: modelo padrao
      "keys": ["sk-...", "sk-..."]
    }

O provider ativo continua sendo escolhido em config.json -> "provider",
usando o nome do custom precedido de "custom:".
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
ARQ = os.path.join(DATA_DIR, "custom_providers.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

_lock = threading.Lock()
_cache = {"at": 0.0, "lista": []}


def _normalizar_nome(texto):
    """Vira um id seguro: minusculo, sem espaco nem acento."""
    t = (texto or "").strip().lower()
    for de, para in (("a", "a"),):
        pass
    t = t.replace(" ", "-").replace("_", "-")
    t = re.sub(r"[^a-z0-9\-]", "", t)
    t = re.sub(r"-+", "-", t).strip("-")
    return t[:40] or "custom"


def _limpar_key(k):
    """Normaliza UMA key sem alterar o conteudo.

    Keys sao case-sensitive (maiuscula e minuscula sao chaves diferentes).
    Aqui so tiramos espaco/aspas/quebra de linha do comeco e do fim.
    """
    if not isinstance(k, str):
        return ""
    return k.strip().strip('"\'').strip()


def _limpar_base(base):
    """Deixa a base url no formato que o cliente usa."""
    b = (base or "").strip()
    if not b:
        return ""
    if not b.startswith(("http://", "https://")):
        b = "https://" + b
    return b.rstrip("/")


def carregar(forcar=False):
    """Lista de providers custom salvos."""
    with _lock:
        if not forcar and time.time() - _cache["at"] < 2.0:
            return list(_cache["lista"])
        try:
            with open(ARQ, encoding="utf-8") as f:
                dados = json.load(f)
        except (OSError, ValueError):
            dados = []
        if isinstance(dados, dict):
            dados = dados.get("providers") or []
        saida = []
        for p in dados if isinstance(dados, list) else []:
            if not isinstance(p, dict):
                continue
            nome = _normalizar_nome(p.get("nome"))
            base = _limpar_base(p.get("base"))
            if not base:
                continue
            keys = [_limpar_key(k) for k in (p.get("keys") or [])]
            keys = [k for k in keys if k]
            saida.append({
                "nome": nome,
                "titulo": (p.get("titulo") or nome).strip(),
                "base": base,
                "modelo": (p.get("modelo") or "").strip(),
                "modo": ((p.get("modo") or "free").strip().lower()
                         if (p.get("modo") or "free").strip().lower()
                         in ("free", "saldo") else "free"),
                # "" = detectar sozinho pelo formato da base
                "adapter": (p.get("adapter") or "").strip().lower(),
                "keys": keys,
            })
        _cache["lista"] = saida
        _cache["at"] = time.time()
        return list(saida)


def _gravar(lista, proteger=True):
    """Grava a lista de customs.

    `proteger=True` funde as keys: se a lista nova for de um provider que
    ja existe e trouxer MENOS keys que a versao em disco, mantem as que
    faltam. Foi assim que a key do anyapi desapareceu — um codigo leu a
    base, mexeu num objeto e gravou por cima, e a chave sumiu sem aviso.
    Remover key de verdade passa por remover_key(), que desliga isso.
    """
    if proteger:
        try:
            with open(ARQ, encoding="utf-8") as f:
                antigo = json.load(f)
            if not isinstance(antigo, list):
                antigo = []
        except (OSError, ValueError):
            antigo = []
        por_nome_antigo = {}
        for p in antigo:
            if isinstance(p, dict):
                por_nome_antigo[_normalizar_nome(p.get("nome"))] = p
        for p in lista:
            if not isinstance(p, dict):
                continue
            velho = por_nome_antigo.get(_normalizar_nome(p.get("nome")))
            if not velho:
                continue
            antes = [_limpar_key(k) for k in (velho.get("keys") or [])]
            agora = [_limpar_key(k) for k in (p.get("keys") or [])]
            faltando = [k for k in antes if k and k not in agora]
            if faltando:
                p["keys"] = agora + faltando
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = ARQ + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(lista, f, indent=2, ensure_ascii=False)
        os.replace(tmp, ARQ)
        _cache["at"] = 0.0
        return True
    except OSError:
        return False


def por_nome(nome):
    """Busca um custom pelo id (aceita com ou sem o prefixo custom:)."""
    alvo = _normalizar_nome((nome or "").replace("custom:", ""))
    for p in carregar():
        if p["nome"] == alvo:
            return p
    return None


def adicionar(nome, base, keys=None, titulo="", modelo="", modo="free",
              adapter=""):
    """Cria ou atualiza um provider custom. Devolve o registro salvo."""
    base = _limpar_base(base)
    if not base:
        raise ValueError("base url vazia")
    if not base.startswith(("http://", "https://")):
        raise ValueError("base url invalida")
    modo = (modo or "free").strip().lower()
    if modo not in ("free", "saldo"):
        modo = "free"
    ident = _normalizar_nome(nome or base.split("//")[-1].split("/")[0])
    lista = carregar(forcar=True)
    registro = None
    for p in lista:
        if p["nome"] == ident:
            registro = p
            break
    if registro is None:
        registro = {"nome": ident, "titulo": titulo or ident,
                    "base": base, "modelo": modelo or "", "modo": modo,
                    "adapter": "", "keys": []}
        lista.append(registro)
    registro["base"] = base
    registro["modo"] = modo
    if adapter:
        registro["adapter"] = adapter.strip().lower()
    if titulo:
        registro["titulo"] = titulo.strip()
    if modelo:
        registro["modelo"] = modelo.strip()
    if keys:
        conhecidas = set(registro.get("keys") or [])
        for k in keys:
            k = (k or "").strip()
            if k and k not in conhecidas:
                registro["keys"].append(k)
                conhecidas.add(k)
    _gravar(lista)
    return registro


def atualizar_campo(nome, campo, valor):
    """Grava um campo de um custom (ex: modo)."""
    ident = _normalizar_nome((nome or "").replace("custom:", ""))
    lista = carregar(forcar=True)
    for p in lista:
        if p["nome"] == ident:
            p[campo] = valor
            return _gravar(lista)
    return False


def remover_key(nome, key):
    """Tira UMA key de um custom (conta que acabou o saldo)."""
    ident = _normalizar_nome((nome or "").replace("custom:", ""))
    lista = carregar(forcar=True)
    for p in lista:
        if p["nome"] != ident:
            continue
        antes = len(p.get("keys") or [])
        p["keys"] = [k for k in (p.get("keys") or []) if k != key]
        if len(p["keys"]) != antes:
            # remocao intencional: sem a protecao, senao a key volta
            _gravar(lista, proteger=False)
            return True
        return False
    return False


def remover(nome):
    ident = _normalizar_nome((nome or "").replace("custom:", ""))
    lista = [p for p in carregar(forcar=True) if p["nome"] != ident]
    return _gravar(lista)


def adicionar_keys(nome, keys):
    """Acrescenta keys a um custom (usado pelo Farm Key tambem)."""
    ident = _normalizar_nome((nome or "").replace("custom:", ""))
    lista = carregar(forcar=True)
    for p in lista:
        if p["nome"] != ident:
            continue
        conhecidas = set(p.get("keys") or [])
        for k in keys:
            k = (k or "").strip()
            if k and k not in conhecidas:
                p["keys"].append(k)
                conhecidas.add(k)
        _gravar(lista)
        return len(p["keys"])
    return 0


def keys_do_ativo():
    """Keys do custom ativo, se o provider ativo for um custom."""
    import providers
    nome = providers.nome_atual()
    if not nome.startswith("custom:"):
        return []
    p = por_nome(nome)
    return list(p["keys"]) if p else []


# ---------------------------------------------------------------- teste
def testar(prov, key="", timeout=15):
    """(ok, mensagem) - o endpoint /models responde?"""
    base = prov["base"] if isinstance(prov, dict) else _limpar_base(prov)
    if not base:
        return False, "url invalida"
    url = base + "/models"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    if key:
        req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            corpo = r.read(400000).decode("utf-8", "replace")
        try:
            dados = json.loads(corpo)
            itens = dados.get("data") or dados.get("models") or []
            n = len(itens) if isinstance(itens, list) else 0
        except ValueError:
            n = 0
        if n:
            return True, "%d modelos" % n
        return True, "respondeu"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, "key recusada (HTTP %d)" % e.code
        if e.code == 404:
            return False, "sem /models nesse endereco"
        return False, "HTTP %d" % e.code
    except Exception as e:
        return False, "sem conexao: %s" % type(e).__name__


def modelos(prov, key=""):
    """Ids de modelo que o custom expoe."""
    base = prov["base"] if isinstance(prov, dict) else _limpar_base(prov)
    if not base:
        return []
    req = urllib.request.Request(base + "/models")
    req.add_header("User-Agent", UA)
    if key:
        req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            dados = json.loads(r.read(600000).decode("utf-8", "replace"))
    except Exception:
        return []
    itens = dados.get("data") or dados.get("models") or []
    saida = []
    for m in itens if isinstance(itens, list) else []:
        if isinstance(m, dict):
            ident = m.get("id") or m.get("name")
            if ident:
                saida.append(str(ident))
        elif isinstance(m, str):
            saida.append(m)
    return sorted(set(saida))


if __name__ == "__main__":
    ps = carregar(forcar=True)
    print("custom providers: %d" % len(ps))
    for p in ps:
        print("  %-18s %-40s %d keys" % (p["nome"], p["base"], len(p["keys"])))
