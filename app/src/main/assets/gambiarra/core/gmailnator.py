"""Gmailnator (Emailnator) - o provedor que o farm usa.

API v2 via RapidAPI. Precisa de uma chave que o usuario cola em
CONFIG > MAIL > Gmailnator.

Endpoints usados:
  POST /emails/generate        cria um endereco
  POST /inbox/                 lista a caixa
  GET  /inbox/{messageID}      le uma mensagem

A chave fica no config.json do projeto, em "mail_gmailnator_key".
Nunca vai para o log.
"""
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://gmailnator.p.rapidapi.com/api"
HOST = "gmailnator.p.rapidapi.com"
TIMEOUT = 30

JANELA_RAPIDAPI = 30
_cache = {"em": 0.0, "restante": None}


class SemChave(Exception):
    """A chave do RapidAPI nao foi configurada."""


class Limite(Exception):
    """Estourou a cota do plano."""


def _req(caminho, dados=None, metodo=None, chave="", timeout=TIMEOUT):
    corpo = json.dumps(dados).encode() if dados is not None else None
    req = urllib.request.Request(BASE + caminho, data=corpo,
                                 method=metodo or ("POST" if dados is not None
                                                   else "GET"))
    req.add_header("Content-Type", "application/json")
    req.add_header("x-rapidapi-host", HOST)
    req.add_header("x-rapidapi-key", chave or "")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _marcar(resp.headers)
            return resp.status, resp.read(200000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        _marcar(exc.headers)
        try:
            txt = exc.read(2000).decode("utf-8", "replace")
        except Exception:
            txt = ""
        if exc.code == 429:
            raise Limite(txt[:120])
        return exc.code, txt
    except (urllib.error.URLError, socket.timeout, OSError):
        return None, ""


def _marcar(headers):
    try:
        v = headers.get("x-ratelimit-requests-remaining")
        if v is not None:
            _cache["restante"] = int(v)
            _cache["em"] = time.time()
    except Exception:
        pass


def restante():
    """Quantas chamadas sobram no plano (None se desconhecido)."""
    return _cache["restante"]


def tem_chave(chave):
    return bool(chave and len(chave.strip()) > 10)


def testar(chave):
    """Tenta gerar um endereco para provar que a chave vale.

    Devolve (ok, mensagem).
    """
    if not tem_chave(chave):
        return False, "sem chave"
    try:
        st, txt = _req("/emails/generate", {}, chave=chave)
    except Limite:
        return False, "limite do plano estourado"
    if st == 200:
        d = _json(txt) or {}
        if d.get("email"):
            return True, d["email"]
        return True, "respondeu ok"
    if st == 401 or st == 403:
        return False, "chave invalida"
    if st == 429:
        return False, "limite do plano estourado"
    return False, "HTTP %s" % st


def _json(txt):
    try:
        return json.loads(txt)
    except Exception:
        return None


def criar(chave, tipos=None):
    """Gera um endereco. Devolve o e-mail ou levanta SemChave/Limite."""
    if not tem_chave(chave):
        raise SemChave()
    corpo = {}
    if tipos:
        corpo["type"] = list(tipos)
    st, txt = _req("/emails/generate", corpo, chave=chave)
    if st == 200:
        d = _json(txt) or {}
        if d.get("email"):
            return d["email"]
        raise SemChave()
    if st == 401 or st == 403:
        raise SemChave()
    if st == 429:
        raise Limite(txt[:120])
    return None


def caixa(chave, email, limite=10):
    """Lista as mensagens. Devolve lista de dicts.

    Levanta Limite quando a cota estourou: devolver [] mentiria
    "caixa vazia" e o chamador ficaria em loop esperando um e-mail
    que nunca vai poder ser lido.
    """
    if not tem_chave(chave):
        raise SemChave()
    st, txt = _req("/inbox/", {"email": email, "limit": limite}, chave=chave)
    if st == 429:
        raise Limite(txt[:120])
    if st == 401 or st == 403:
        raise SemChave()
    if st != 200:
        return []
    d = _json(txt) or {}
    return d.get("messages") or []


def ler(chave, message_id):
    """Le o conteudo completo de uma mensagem."""
    if not tem_chave(chave) or not message_id:
        return ""
    st, txt = _req("/inbox/" + urllib.parse.quote(str(message_id)),
                   metodo="GET", chave=chave)
    if st != 200:
        return ""
    d = _json(txt) or {}
    return d.get("content") or ""


def esperar(codigo, chave, email, segundos=120, intervalo=4, log=None):
    """Fica olhando a caixa ate achar um codigo de confirmacao.

    Devolve (codigo, trecho) ou (None, "").
    """
    if not tem_chave(chave):
        return None, ""
    limite = time.time() + segundos
    vistos = set()
    while time.time() < limite:
        try:
            msgs = caixa(chave, email, 10)
        except Limite:
            if log:
                log("gmailnator: limite estourado")
            return None, ""
        for m in msgs:
            mid = m.get("id")
            if not mid or mid in vistos:
                continue
            vistos.add(mid)
            corpo = ler(chave, mid)
            texto = (m.get("subject") or "") + "\n" + (corpo or "")
            achado = codigo_de(texto)
            if achado:
                return achado, texto[:2000]
        time.sleep(intervalo)
    return None, ""


def codigo_de(texto):
    import re
    if not texto:
        return None
    for pat in (r"\b(\d{6})\b", r"\b(\d{4,8})\b"):
        achado = re.search(pat, texto)
        if achado:
            return achado.group(1)
    return None
