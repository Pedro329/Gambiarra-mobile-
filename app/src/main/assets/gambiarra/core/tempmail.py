"""Provedores de e-mail temporario para o farm.

Cada provedor devolve um endereco e uma funcao para ler a caixa.
Quem le a caixa e o backend: a interface nunca mostra e-mail.

As APIs abaixo foram testadas sem chave em 2026-11-14:

  mail.tm        cria conta via REST, token JWT, inbox por Bearer
  guerrillamail  sessao por sid_token, leitura por f/id
  temp-mail.io   token por endereco, listagem por e-mail
  maildrop       GraphQL, caixa publica por nome

O Gmailnator fica em gmailnator.py porque precisa de chave.
O modulo nao guarda nada em disco: quem chama decide onde salvar.
"""
import json
import secrets
import string
import socket
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
TIMEOUT = 20
ALNUM = string.ascii_lowercase + string.digits


# ------------------------------------------------------------------ util

def _nome(n=10):
    return "".join(secrets.choice(ALNUM) for _ in range(n))


def _req(url, dados=None, metodo=None, hdr=None, timeout=TIMEOUT):
    """Faz uma requisicao e devolve (status, texto). Nunca levanta."""
    corpo = None
    if dados is not None:
        corpo = json.dumps(dados).encode()
    elif metodo == "POST":
        corpo = b""
    req = urllib.request.Request(url, data=corpo,
                                 method=metodo or ("POST" if dados is not None
                                                   else "GET"))
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    if corpo is not None:
        req.add_header("content-type", "application/json")
    for k, v in (hdr or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(400000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, exc.read(2000).decode("utf-8", "replace")
        except Exception:
            return exc.code, ""
    except (urllib.error.URLError, socket.timeout, OSError):
        return None, ""
    except Exception:
        return None, ""


def _json(txt):
    try:
        return json.loads(txt)
    except Exception:
        return None


# ------------------------------------------------------------- mail.tm

def _mailtm_criar():
    st, t = _req("https://api.mail.tm/domains")
    d = _json(t) or {}
    if st != 200 or not isinstance(d, list) or not d:
        d2 = (d.get("hydra:member") if isinstance(d, dict) else None) or []
        d = d2
    if not d:
        return None
    dominio = d[0].get("domain")
    if not dominio:
        return None
    nome = _nome()
    endereco = "%s@%s" % (nome, dominio)
    senha = "Gamb" + _nome(12)
    st, t = _req("https://api.mail.tm/accounts",
                 {"address": endereco, "password": senha})
    if st not in (200, 201):
        return None
    st, t = _req("https://api.mail.tm/token",
                 {"address": endereco, "password": senha})
    d = _json(t) or {}
    tok = d.get("token")
    if not tok:
        return None
    return {"email": endereco, "token": tok}


def _mailtm_ler(ctx):
    hdr = {"Authorization": "Bearer " + ctx["token"]}
    st, t = _req("https://api.mail.tm/messages", hdr=hdr)
    d = _json(t)
    if st != 200:
        return []
    itens = d if isinstance(d, list) else (d.get("hydra:member") or [])
    saida = []
    for m in itens:
        corpo = ""
        mid = m.get("id")
        if mid:
            st2, t2 = _req("https://api.mail.tm/messages/" + str(mid), hdr=hdr)
            dm = _json(t2) or {}
            corpo = dm.get("text") or dm.get("html") or ""
        saida.append({"de": (m.get("from") or {}).get("address", ""),
                      "assunto": m.get("subject", ""),
                      "corpo": corpo})
    return saida


# ------------------------------------------------------ guerrillamail

def _guerrilla_criar():
    st, t = _req("https://api.guerrillamail.com/ajax.php?f=get_email_address")
    d = _json(t) or {}
    if st != 200 or not d.get("email_addr"):
        return None
    return {"email": d["email_addr"], "sid": d.get("sid_token", "")}


def _guerrilla_ler(ctx):
    st, t = _req("https://api.guerrillamail.com/ajax.php"
                 "?f=check_email&seq=0&sid_token=%s" % ctx.get("sid", ""))
    d = _json(t) or {}
    itens = d.get("list") or []
    saida = []
    for m in itens:
        mid = m.get("mail_id")
        corpo = ""
        if mid:
            st2, t2 = _req("https://api.guerrillamail.com/ajax.php"
                           "?f=fetch_email&email_id=%s&sid_token=%s"
                           % (mid, ctx.get("sid", "")))
            dm = _json(t2) or {}
            corpo = dm.get("mail_body") or ""
        saida.append({"de": m.get("mail_from", ""),
                      "assunto": m.get("mail_subject", ""),
                      "corpo": corpo})
    return saida


# -------------------------------------------------------- temp-mail.io

def _tmpio_criar():
    st, t = _req("https://api.internal.temp-mail.io/api/v3/email/new",
                 {"min_name_length": 8, "max_name_length": 12})
    d = _json(t) or {}
    if st != 200 or not d.get("email"):
        return None
    return {"email": d["email"], "token": d.get("token", "")}


def _tmpio_ler(ctx):
    st, t = _req("https://api.internal.temp-mail.io/api/v3/email/%s/messages"
                 % urllib.parse.quote(ctx["email"]))
    d = _json(t)
    if st != 200 or not isinstance(d, list):
        return []
    return [{"de": m.get("from", ""), "assunto": m.get("subject", ""),
             "corpo": m.get("body_text") or m.get("body_html") or ""}
            for m in d]


# ------------------------------------------------------------ maildrop

def _maildrop_criar():
    nome = _nome(9)
    return {"email": nome + "@maildrop.cc"}


def _maildrop_ler(ctx):
    consulta = ('query { inbox(mailbox:"%s") { id headerfrom subject } }'
                % ctx["email"].replace('"', ""))
    st, t = _req("https://api.maildrop.cc/graphql", {"query": consulta},
                 "POST")
    d = _json(t) or {}
    itens = (d.get("data") or {}).get("inbox") or []
    saida = []
    for m in itens:
        mid = m.get("id")
        corpo = ""
        if mid:
            c2 = ('query { message(mailbox:"%s", id:"%s") { data } }'
                  % (ctx["email"].replace('"', ""), str(mid).replace('"', "")))
            st2, t2 = _req("https://api.maildrop.cc/graphql", {"query": c2},
                           "POST")
            dm = _json(t2) or {}
            corpo = ((dm.get("data") or {}).get("message") or {}).get("data", "")
        saida.append({"de": m.get("headerfrom", ""),
                      "assunto": m.get("subject", ""),
                      "corpo": corpo})
    return saida


# -------------------------------------------------------------- catalogo

PROVEDORES = [
    {"id": "mailtm", "nome": "mail.tm", "sem_key": True,
     "criar": _mailtm_criar, "ler": _mailtm_ler,
     "nota": "conta por REST, token JWT"},
    {"id": "guerrilla", "nome": "Guerrilla Mail", "sem_key": True,
     "criar": _guerrilla_criar, "ler": _guerrilla_ler,
     "nota": "sessao por sid_token"},
    {"id": "tmpio", "nome": "temp-mail.io", "sem_key": True,
     "criar": _tmpio_criar, "ler": _tmpio_ler,
     "nota": "token por endereco"},
    {"id": "maildrop", "nome": "Maildrop", "sem_key": True,
     "criar": _maildrop_criar, "ler": _maildrop_ler,
     "nota": "GraphQL, caixa publica"},
]

POR_ID = {p["id"]: p for p in PROVEDORES}


def criar(prov_id):
    """Cria um endereco. Devolve dict com email + contexto, ou None."""
    p = POR_ID.get(prov_id)
    if not p:
        return None
    try:
        return p["criar"]()
    except Exception:
        return None


def ler(prov_id, ctx):
    """Le a caixa. Devolve lista de {"de","assunto","corpo"}."""
    p = POR_ID.get(prov_id)
    if not p:
        return []
    try:
        return p["ler"](ctx)
    except Exception:
        return []


def codigo_de(texto, digitos=6):
    """Tira o primeiro codigo numerico do texto."""
    import re
    if not texto:
        return None
    padroes = [r"\b(\d{%d})\b" % digitos, r"\b(\d{4,8})\b"]
    for pat in padroes:
        achado = re.search(pat, texto)
        if achado:
            return achado.group(1)
    return None


def esperar(prov_id, ctx, segundos=120, intervalo=4):
    """Fica lendo a caixa ate achar um codigo. Quem chama e o backend."""
    import time as _time
    limite = _time.time() + segundos
    while _time.time() < limite:
        for m in ler(prov_id, ctx):
            achado = codigo_de((m.get("assunto") or "") + "\n"
                               + (m.get("corpo") or ""))
            if achado:
                return achado
        _time.sleep(intervalo)
    return None
