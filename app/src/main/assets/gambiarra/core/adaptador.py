"""Adaptador para gateways que NAO falam o padrao OpenAI em /chat/completions.

O router sempre faz POST em `<base>/chat/completions` esperando de volta
`{"choices":[{"message":{"content":"..."}}]}`. Alguns servicos expoem outra
coisa. O Bike4Mind, por exemplo:

    /api/ai/v1/completions   -> SSE (text/event-stream), sempre
    /api/chat                -> JSON puro com o campo "response"
    /api/v1/models           -> lista de modelos

Este modulo traduz. Se o provider ativo nao precisar, o router segue
exatamente como antes, sem custo nenhum.

GRAMATICA DE CADASTRO
    Ao cadastrar a base url, basta escolher o "tipo" (ou usar o modo
    automatico, que testa e descobre):

    openai   -> <base>/chat/completions        (padrao, nada muda)
    b4m      -> <host>/api/ai/v1/completions   (SSE)  + <host>/api/v1/models
    b4m-chat -> <host>/api/chat                (JSON) + <host>/api/v1/models
    sse      -> <base>/completions             (SSE generico)

COMO E ESCOLHIDO
    providers.base_url_atual() continua devolvendo a base. O campo
    "adapter" do custom provider diz qual usar. Sem o campo, detecta pelo
    formato da base (se termina em /api/ai/v1 ou /api/v1, e Bike4Mind).
"""
import json
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

MODO_OPENAI = "openai"
MODO_B4M = "b4m"
MODO_B4M_CHAT = "b4m-chat"
MODO_SSE = "sse"

MODOS = (MODO_OPENAI, MODO_B4M, MODO_B4M_CHAT, MODO_SSE)

# hosts/padroes conhecidos que precisam de traducao
_B4M_MARCAS = ("bike4mind",)


# ------------------------------------------------------------- deteccao
def detectar(base, adapter=""):
    """Qual adaptador usar para esta base url."""
    a = (adapter or "").strip().lower()
    if a in MODOS:
        return a
    b = (base or "").rstrip("/").lower()
    if any(m in b for m in _B4M_MARCAS):
        return MODO_B4M_CHAT        # JSON e mais confiavel que SSE
    if b.endswith("/api/ai/v1"):
        return MODO_B4M_CHAT
    return MODO_OPENAI


def adapter_ativo():
    """Adaptador do provider ativo. Nunca levanta excecao."""
    try:
        import providers
        nome = providers.nome_atual()
        base = providers.base_url_atual()
        prov = providers.atual()
        # provider FIXO declara o adaptador no proprio catalogo
        fixo = (prov or {}).get("adapter") or ""
        if fixo:
            return detectar(base, fixo)
        if not nome.startswith("custom:"):
            return detectar(base)
        import custom_provider
        p = custom_provider.por_nome(nome.replace("custom:", ""))
        return detectar(base, (p or {}).get("adapter", ""))
    except Exception:
        return MODO_OPENAI


# --------------------------------------------------------------- URLs
def url_chat(base, modo):
    """URL para onde o POST do chat vai."""
    b = (base or "").rstrip("/")
    if modo == MODO_B4M_CHAT:
        return _host(b) + "/api/chat"
    if modo == MODO_B4M:
        return _host(b) + "/api/ai/v1/completions"
    if modo == MODO_SSE:
        return b + "/completions"
    return b + "/chat/completions"


def url_models(base, modo):
    """URL da listagem de modelos."""
    b = (base or "").rstrip("/")
    if modo in (MODO_B4M, MODO_B4M_CHAT):
        return _host(b) + "/api/v1/models"
    return b + "/models"


def _host(base):
    """https://host/path/v1 -> https://host"""
    partes = base.split("/", 3)
    if len(partes) >= 3:
        return partes[0] + "//" + partes[2]
    return base


# -------------------------------------------------------- requisicao
def montar(payload, modo):
    """Corpo da requisicao no formato do servico."""
    if modo == MODO_B4M_CHAT:
        # /api/chat recebe uma mensagem unica + historico
        msgs = payload.get("messages") or []
        sistema = ""
        conversa = []
        for m in msgs:
            papel = m.get("role")
            txt = _texto(m.get("content"))
            if papel == "system":
                sistema = (sistema + "\n" + txt).strip()
            elif papel == "assistant":
                conversa.append("assistant: " + txt)
            else:
                conversa.append("user: " + txt)
        ultima = conversa[-1][6:] if conversa and conversa[-1].startswith("user: ") else ""
        historico = conversa[:-1] if ultima else conversa
        msg = ultima
        if historico:
            msg = ("[historico]\n" + "\n".join(historico) + "\n[/historico]\n\n" + ultima)
        if sistema:
            msg = "[instrucoes]\n" + sistema + "\n[/instrucoes]\n\n" + msg
        corpo = {"message": msg, "model": payload.get("model"),
                 "wait": True}
        if payload.get("max_tokens"):
            corpo["maxTokens"] = payload["max_tokens"]
        return corpo
    # openai, b4m (SSE) e sse generico aceitam o corpo original
    return payload


def _texto(conteudo):
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        partes = []
        for p in conteudo:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                partes.append(p["text"])
            elif isinstance(p, str):
                partes.append(p)
        return "".join(partes)
    return "" if conteudo is None else str(conteudo)


# -------------------------------------------------------- resposta
def para_openai(corpo, modo, modelo=""):
    """Converte a resposta do servico para o formato padrao."""
    if modo == MODO_B4M_CHAT:
        try:
            d = json.loads(corpo)
        except ValueError:
            return None
        texto = d.get("response")
        if texto is None:
            rs = d.get("responses")
            texto = rs[0] if isinstance(rs, list) and rs else ""
        return _envelope(str(texto or ""), d.get("model") or modelo)
    if modo in (MODO_B4M, MODO_SSE):
        return _de_sse(corpo, modelo)
    return None


def _envelope(texto, modelo):
    return {
        "id": "chatcmpl-adaptado",
        "object": "chat.completion",
        "created": 0,
        "model": modelo,
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": texto}}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _de_sse(bruto, modelo):
    """Junta os eventos SSE em um unico texto."""
    partes = []
    erro = None
    for linha in (bruto or "").splitlines():
        linha = linha.strip()
        if not linha.startswith("data:"):
            continue
        dados = linha[5:].strip()
        if not dados or dados == "[DONE]":
            continue
        try:
            ev = json.loads(dados)
        except ValueError:
            continue
        tipo = ev.get("type")
        if tipo == "content":
            t = ev.get("text")
            if isinstance(t, str) and t:
                partes.append(t)
        elif tipo == "error":
            erro = ev.get("message") or json.dumps(ev)[:200]
    if erro and not partes:
        return {"__erro__": erro}
    return _envelope("".join(partes), modelo)


# --------------------------------------------------- postagem pronta
def postar(base, token, payload, timeout, modo=None):
    """Faz o POST e devolve (status, corpo_ja_no_padrao_openai).

    Levanta nada: o chamador decide o que fazer com o status.
    """
    modo = modo or detectar(base)
    url = url_chat(base, modo)
    corpo = montar(payload, modo)
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(),
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "text/event-stream")
    req.add_header("User-Agent", UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = r.status
            bruto = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        return 0, "connection: %s" % e.reason
    except Exception as e:
        return 0, "error: %s" % e
    if modo == MODO_OPENAI:
        return status, bruto
    convertido = para_openai(bruto, modo, payload.get("model", ""))
    if convertido is None:
        return status, bruto
    if "__erro__" in convertido:
        return 400, json.dumps({"error": {"message": convertido["__erro__"]}})
    return status, json.dumps(convertido)


if __name__ == "__main__":
    for b in ("https://api.anyapi.ai/v1",
              "https://app.bike4mind.com/api/ai/v1",
              "https://app.bike4mind.com"):
        m = detectar(b)
        print("%-40s -> %-9s" % (b, m))
        print("   chat  :", url_chat(b, m))
        print("   models:", url_models(b, m))
