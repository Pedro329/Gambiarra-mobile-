import json
import os
import secrets
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import grpool

HOST = "127.0.0.1"
PORT = int(os.environ.get("GR_PORT", "8080"))
PUBLIC_PREFIX = "gambiarraapi/"
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
}

def answer_of(data):
    """Text of a completion. A reasoning model can fill reasoning_content and
    leave content empty - that still counts as an answer, otherwise the caller
    sees "completed with no content" and gives up."""
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = msg.get("content") or ""
    if not text:
        text = msg.get("reasoning_content") or msg.get("reasoning") or ""
    if not text:
        for key in ("text", "output_text"):
            value = choice.get(key) or msg.get(key)
            if isinstance(value, str) and value:
                text = value
                break
    if not text:
        for part in msg.get("content") if isinstance(msg.get("content"), list) else []:
            if isinstance(part, dict) and part.get("text"):
                text += part["text"]
    return text

def has_answer(data):
    return bool(answer_of(data).strip())

def fix_tool_calls(choice):
    """A tool call with empty content IS a complete answer. Normalise it so
    clients that check content or arguments do not choke:
    id present, type=function, arguments always a JSON string, finish_reason."""
    msg = choice.get("message") or {}
    calls = msg.get("tool_calls") or choice.get("tool_calls")
    if not calls:
        if choice.get("finish_reason") == "" or choice.get("finish_reason") is None:
            choice["finish_reason"] = "stop"
        return
    fixed = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        fn = call.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, dict):
            fn["arguments"] = json.dumps(args, ensure_ascii=False)
        elif args is None:
            fn["arguments"] = "{}"
        elif not isinstance(args, str):
            fn["arguments"] = json.dumps(args)
        call["type"] = "function"
        call["function"] = fn
        if not call.get("id"):
            call["id"] = "call_" + uuid.uuid4().hex[:24]
        fixed.append(call)
    msg["tool_calls"] = fixed
    msg.setdefault("role", "assistant")
    if msg.get("content") is None:
        msg["content"] = ""
    choice["message"] = msg
    choice["finish_reason"] = "tool_calls"

class State:
    keys = []
    selected = None
    routing = False
    uncensored = None
    model_map = {}
    system_context = {}
    global_context = None
    local_key = None
    started = time.time()
    # contadores mostrados no ServerInfo (o menu le direto daqui)
    requests = 0
    tokens_in = 0
    tokens_out = 0
    trocas = []          # (quando, modelo_pedido, modelo_usado)

def contar(pedido=None, usado=None, entrada=0, saida=0):
    """Registra uma chamada concluida. Thread-safe o bastante: sao so
    incrementos, e um numero perdido nao muda nada na tela."""
    State.requests += 1
    State.tokens_in += int(entrada or 0)
    State.tokens_out += int(saida or 0)
    if pedido and usado and pedido != usado:
        State.trocas.append((time.time(), pedido, usado))
        del State.trocas[:-40]

def rotation_keys():
    """Keys que o upstream deve receber agora."""
    try:
        import keyring
        return keyring.rotation() or State.keys
    except Exception:
        return State.keys
_lock = threading.Lock()

def _json(handler, code, obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    try:
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        for k, v in CORS.items():
            handler.send_header(k, v)
        handler.end_headers()
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
        handler.close_connection = True

def _err(handler, code, message, kind="error"):
    _json(handler, code, {"error": {"message": message, "type": kind,
                                    "code": kind}})

def _auth_ok(handler):
    return True

def legacy_shape(data):
    """Turn a chat completion into the old /v1/completions body, which wants
    a plain "text" field instead of a message object."""
    out = dict(data)
    choices = []
    for item in data.get("choices") or []:
        if not isinstance(item, dict):
            continue
        msg = item.get("message") or {}
        text = msg.get("content")
        if not isinstance(text, str):
            text = answer_of(data)
        choices.append({"text": text or "", "index": item.get("index", 0),
                        "logprobs": None,
                        "finish_reason": item.get("finish_reason") or "stop"})
    out["choices"] = choices
    return out

def safe_compare(a, b):
    """compare_digest refuses non-ASCII strings, and http.server decodes header
    values as latin-1, so both sides are clamped to ASCII bytes first."""
    if a is None or b is None:
        return False
    try:
        left = a.encode("latin-1", "replace")
        right = b.encode("latin-1", "replace")
    except Exception:
        return a == b
    if left == right:
        return True
    # the caller may have sent utf-8 bytes; compare those too
    return a.encode("utf-8", "replace") == b.encode("utf-8", "replace")

def public_models():
    ids = [PUBLIC_PREFIX + pretty(m) for m in State.model_map]
    return [{"id": m, "object": "model", "created": int(State.started),
             "owned_by": "gambiarra"} for m in ids]

def pretty(name):
    return name[:-5] if name.endswith("-free") else name

def resolve_public(name):
    if not name:
        name = State.selected or ""
    if name.startswith(PUBLIC_PREFIX):
        name = name[len(PUBLIC_PREFIX):]
    for real in State.model_map:
        if real == name or real[:-5] == name or pretty(real) == name:
            return State.model_map[real]
    if name + "-free" in State.model_map:
        return State.model_map[name + "-free"]
    if name.endswith("-free"):
        return name
    return None

class _AnthropicSink:
    """Reads the OpenAI SSE the upstream sends and emits Anthropic events."""
    __slots__ = ("handler", "event", "state", "buf", "mid", "block", "tools")

    def __init__(self, handler, event, state, mid):
        self.handler = handler
        self.event = event
        self.state = state
        self.buf = b""
        self.mid = mid
        self.block = 0
        self.tools = {}

    def write(self, data):
        self.buf += data
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            raw = line[5:].strip()
            if raw in (b"[DONE]", b"", b"null"):
                continue
            try:
                obj = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            self._chunk(obj)

    def _chunk(self, obj):
        for choice in obj.get("choices") or []:
            delta = choice.get("delta") or {}
            text = delta.get("content")
            if text:
                if not self.state["text"]:
                    self.state["text"] = True
                self.event("content_block_delta", {
                    "type": "content_block_delta", "index": 0,
                    "delta": {"type": "text_delta", "text": text}})
            for call in delta.get("tool_calls") or []:
                pos = call.get("index", 0)
                entry = self.tools.get(pos)
                if entry is None:
                    self.state["text"] = self.state["text"] or False
                    self.block += 1
                    entry = {"index": self.block, "id": call.get("id") or
                             "toolu_" + uuid.uuid4().hex[:24],
                             "name": (call.get("function") or {}).get("name", "")}
                    self.tools[pos] = entry
                    self.event("content_block_start", {
                        "type": "content_block_start", "index": entry["index"],
                        "content_block": {"type": "tool_use", "id": entry["id"],
                                          "name": entry["name"],
                                          "input": {}}})
                args = (call.get("function") or {}).get("arguments")
                if args:
                    self.event("content_block_delta", {
                        "type": "content_block_delta", "index": entry["index"],
                        "delta": {"type": "input_json_delta",
                                  "partial_json": args}})
        if self.state.get("text") and not self.state.get("started"):
            self.state["started"] = True

class _Sink:
    __slots__ = ("handler",)

    def __init__(self, handler):
        self.handler = handler

    def write(self, data):
        self.handler.wfile.write(data)
        self.handler.wfile.flush()

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            return None

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in CORS.items():
            self.send_header(k, v)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ("/v1/models", "/models", "/gambiarraapi/modelos"):
            _json(self, 200, {"object": "list", "data": public_models()})
            return
        if path.startswith("/v1/models/"):
            # clients fetch a single model before opening a chat
            wanted = path[len("/v1/models/"):]
            for entry in public_models():
                if entry["id"] in (wanted, PUBLIC_PREFIX + wanted) or \
                        entry["id"].endswith("/" + wanted):
                    _json(self, 200, entry)
                    return
            _err(self, 404, "model not found: " + wanted, "not_found")
            return
        if path in ("/health", ""):
            _json(self, 200, {"status": "ok", "keys": grpool.POOL.count(),
                              "routing": State.routing,
                              "models": len(State.model_map),
                              "uptime": int(time.time() - State.started)})
            return
        if path in ("/gambiarraapi/status", "/v1/status"):
            rows, total = grpool.POOL.describe(limit=20)
            _json(self, 200, {"keys": total, "live": grpool.POOL.live_count(),
                              "routing": State.routing,
                              "selected": State.selected,
                              "uncensored": State.uncensored,
                              "rows": [{"index": r[0], "state": r[1],
                                        "cooldown": r[2]} for r in rows]})
            return
        _err(self, 404, "not found: " + path + " (use /v1/models or "
             "/v1/chat/completions)", "not_found")

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        if not self._auth_ok():
            _err(self, 401, "API key invalida: use a key de gambiarra_key.txt",
                 "invalid_api_key")
            return
        req = self._body()
        if req is None:
            _err(self, 400, "invalid json", "invalid_request_error")
            return
        if path.endswith("/chat/completions"):
            self._chat(req)
            return
        if path.endswith("/completions"):
            # legacy text endpoint: many clients still post here
            prompt = req.get("prompt")
            if isinstance(prompt, list):
                prompt = "\n".join(str(p) for p in prompt)
            req = dict(req)
            req["messages"] = [{"role": "user",
                                "content": str(prompt or "")}]
            self._chat(req, legacy=True)
            return
        if path == "/v1/messages":
            self._anthropic(req)
            return
        _err(self, 404, "not found: " + path + " (use /v1/chat/completions, "
             "/v1/completions or /v1/messages)", "not_found")

    def _auth_ok(self):
        """Only the key written by the gateway itself gets in. Without this any
        local process could spend every farmed key."""
        expected = State.local_key
        if not expected:
            return True
        try:
            auth = self.headers.get("Authorization") or ""
            token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
            if not token:
                token = (self.headers.get("x-api-key") or "").strip()
            if not token:
                token = (self.headers.get("api-key") or "").strip()
        except Exception:
            return False
        return safe_compare(token, expected)

    def _prepare(self, req, model, system):
        chain = []
        if isinstance(system, str) and system.strip():
            chain.append({"role": "system", "content": system})
        elif isinstance(system, list):
            text = "\n".join(p.get("text", "") for p in system
                             if isinstance(p, dict) and p.get("type") == "text")
            if text.strip():
                chain.append({"role": "system", "content": text})
        for m in req.get("messages") or []:
            if not isinstance(m, dict):
                continue
            clean = self._clean_message(m)
            if clean is not None:
                chain.append(clean)
        ctx = State.system_context.get(model)
        if not ctx and model.startswith(PUBLIC_PREFIX):
            ctx = State.system_context.get(model[len(PUBLIC_PREFIX):])
        if not ctx:
            ctx = State.global_context
        if ctx:
            chain.insert(0, {"role": "system", "content": ctx})
        return chain

    @staticmethod
    def _clean_message(m):
        """Keep everything the model needs: tool_calls and tool_call_id must
        survive, or the upstream hangs waiting for a turn it cannot rebuild."""
        role = m.get("role")
        if not role:
            return None
        out = {"role": role}
        content = m.get("content")
        out["content"] = "" if content is None else content
        if m.get("name"):
            out["name"] = m["name"]
        calls = m.get("tool_calls")
        if isinstance(calls, list) and calls:
            fixed = []
            for call in calls:
                if not isinstance(call, dict):
                    continue
                fn = call.get("function") or {}
                args = fn.get("arguments")
                if isinstance(args, dict):
                    args = json.dumps(args, ensure_ascii=False)
                elif args is None:
                    args = "{}"
                fixed.append({"id": call.get("id") or "call_" + uuid.uuid4().hex[:20],
                              "type": "function",
                              "function": {"name": fn.get("name") or "",
                                           "arguments": args}})
            if fixed:
                out["tool_calls"] = fixed
        if m.get("tool_call_id"):
            out["tool_call_id"] = m["tool_call_id"]
        if not out["content"] and not out.get("tool_calls") \
                and not out.get("tool_call_id") and role != "assistant":
            return None
        return out

    def _chat(self, req, legacy=False):
        model = req.get("model")
        upstream = resolve_public(model)
        if not upstream:
            _err(self, 404, "modelo '%s' nao existe. use /v1/models" % model,
                 "model_not_found")
            return
        messages = self._prepare(req, upstream, None)
        payload = {"model": upstream, "messages": messages}
        for field in ("temperature", "top_p", "max_tokens", "max_completion_tokens",
                      "stop", "presence_penalty", "frequency_penalty", "tools",
                      "tool_choice", "response_format", "seed"):
            if field in req and req[field] is not None:
                payload[field] = req[field]
        stream = bool(req.get("stream"))
        if stream:
            self._stream(upstream, model, payload)
            return
        try:
            used, text = grpool.complete_for(upstream, rotation_keys(), payload)
        except grpool.UpstreamError as e:
            code = e.code if e.status in (429, 401, 403, 503) else "upstream"
            _json(self, e.status if 400 <= e.status < 600 else 502,
                  {"error": {"message": e.message, "type": code, "code": code}})
            return
        try:
            data = json.loads(text)
        except ValueError:
            _err(self, 502, "resposta invalida do upstream", "upstream")
            return
        answer = answer_of(data)
        choices = data.get("choices") or []
        if answer and choices and not (choices[0].get("message") or {}).get("content"):
            msg = choices[0].setdefault("message", {})
            msg["content"] = answer
        if choices:
            fix_tool_calls(choices[0])
        uso = data.get("usage") or {}
        contar(model, used, uso.get("prompt_tokens") or 0,
               uso.get("completion_tokens") or 0)
        data["model"] = pretty(model) if model else model
        if legacy:
            data = legacy_shape(data)
        _json(self, 200, data)

    def _stream(self, upstream, model, payload):
        self.close_connection = True
        state = {}

        def on_open(target, token):
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("Connection", "close")
                for k, v in CORS.items():
                    self.send_header(k, v)
                self.end_headers()
            except Exception:
                return None
            state["open"] = True
            # a partir daqui a resposta vai sair: entra na contagem
            contar(model, target)
            return _Sink(self)

        try:
            grpool.stream_for(upstream, rotation_keys(), payload, on_open)
        except grpool.UpstreamError as e:
            if state.get("open"):
                return
            code = e.code if e.status in (429, 401, 403, 503) else "upstream"
            _json(self, e.status if 400 <= e.status < 600 else 502,
                  {"error": {"message": e.message, "type": code, "code": code}})
        except Exception as e:
            if state.get("open"):
                return
            _err(self, 502, str(e)[:200], "upstream")

    def _anthropic_stream(self, upstream, model, payload):
        self.close_connection = True
        state = {}
        mid = "msg_" + uuid.uuid4().hex[:24]

        def event(name, obj):
            self.wfile.write(b"event: " + name.encode() + b"\n"
                             + b"data: " + json.dumps(obj, ensure_ascii=False).encode()
                             + b"\n\n")
            self.wfile.flush()

        def on_open(target, token):
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("Connection", "close")
                for k, v in CORS.items():
                    self.send_header(k, v)
                self.end_headers()
                event("message_start", {
                    "type": "message_start",
                    "message": {"id": mid, "type": "message", "role": "assistant",
                                "model": model, "content": [], "stop_reason": None,
                                "usage": {"input_tokens": 0, "output_tokens": 0}}})
                event("content_block_start", {
                    "type": "content_block_start", "index": 0,
                    "content_block": {"type": "text", "text": ""}})
            except Exception:
                return None
            state.update({"open": True, "text": False, "tools": {},
                          "started": False})
            contar(model, target)
            return _AnthropicSink(self, event, state, mid)

        try:
            grpool.stream_for(upstream, rotation_keys(), payload, on_open)
            try:
                event("content_block_stop", {"type": "content_block_stop",
                                             "index": 0})
                event("message_delta", {
                    "type": "message_delta",
                    "delta": {"stop_reason": "tool_use" if state.get("tools")
                              else "end_turn"},
                    "usage": {"output_tokens": 0}})
                event("message_stop", {"type": "message_stop"})
            except Exception:
                pass
        except grpool.UpstreamError as e:
            if state.get("open"):
                try:
                    event("message_stop", {"type": "message_stop"})
                except Exception:
                    pass
                return
            code = e.code if e.status in (429, 401, 403, 503) else "upstream"
            _json(self, e.status if 400 <= e.status < 600 else 502,
                  {"error": {"message": e.message, "type": code, "code": code}})
        except Exception as e:
            if state.get("open"):
                return
            _err(self, 502, str(e)[:200], "upstream")

    def _anthropic(self, req):
        model = req.get("model")
        upstream = resolve_public(model)
        if not upstream:
            _err(self, 404, "modelo '%s' nao existe" % model, "model_not_found")
            return
        messages = self._prepare(req, upstream, req.get("system"))
        payload = {"model": upstream, "messages": messages,
                   "max_tokens": req.get("max_tokens") or 4096}
        for field in ("temperature", "top_p", "stop_sequences"):
            if field in req:
                payload[field] = req[field]
        if "stop_sequences" in payload:
            payload["stop"] = payload.pop("stop_sequences")
        if req.get("stream"):
            self._anthropic_stream(upstream, model, payload)
            return
        try:
            used, text = grpool.complete_for(upstream, rotation_keys(), payload)
        except grpool.UpstreamError as e:
            _err(self, e.status if e.status >= 400 else 502, e.message, e.code)
            return
        try:
            data = json.loads(text)
        except ValueError:
            _err(self, 502, "resposta invalida do upstream", "upstream")
            return
        choice = (data.get("choices") or [{}])[0]
        fix_tool_calls(choice)
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        usage = data.get("usage") or {}
        blocks = []
        if content:
            blocks.append({"type": "text", "text": content})
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            blocks.append({"type": "tool_use", "id": call.get("id"),
                           "name": fn.get("name"), "input": args})
        if not blocks:
            blocks.append({"type": "text", "text": ""})
        _json(self, 200, {
            "id": "msg_" + uuid.uuid4().hex[:24],
            "type": "message", "role": "assistant", "model": model,
            "content": blocks,
            "stop_reason": ("tool_use" if msg.get("tool_calls") else "end_turn"),
            "usage": {"input_tokens": usage.get("prompt_tokens", 0),
                      "output_tokens": usage.get("completion_tokens", 0)},
        })

class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64

    def handle_error(self, request, client_address):
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionAbortedError,
                            ConnectionResetError, TimeoutError)):
            return
        try:
            sys.stderr.write("erro no request: %s\n" % exc)
        except Exception:
            pass

def build():
    return Server((HOST, PORT), Handler)
