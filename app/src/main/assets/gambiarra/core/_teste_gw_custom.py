"""Prova que o GATEWAY de verdade fala com um custom provider.

Sobe o grserver apontado para um upstream falso, manda um chat real
pelo endpoint /v1/chat/completions e confere:
  - a requisicao chegou no upstream custom
  - usou uma key da rotacao do custom
  - a resposta voltou certa
  - quando a primeira key falha, ele tenta a proxima
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

recebidas = []


class Upstream(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(n) if n else b"{}"
        auth = self.headers.get("Authorization", "").replace("Bearer ", "")
        recebidas.append({"path": self.path, "key": auth,
                          "body": json.loads(corpo or b"{}")})
        if auth == "sk-ruim":
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"rate limited"}}')
            return
        saida = {"id": "x", "object": "chat.completion", "created": 1,
                 "model": "teste", "choices": [{"index": 0, "message": {
                     "role": "assistant", "content": "resposta do custom"},
                     "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 1, "completion_tokens": 2,
                           "total_tokens": 3}}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(saida).encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"data":[{"id":"teste"}]}')

    def log_message(self, *a):
        pass


def main():
    porta_up = 8932
    srv = HTTPServer(("127.0.0.1", porta_up), Upstream)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d/v1" % porta_up

    import custom_provider
    import providers
    custom_provider.remover("teste-gw")
    custom_provider.adicionar("teste-gw", base, ["sk-ruim", "sk-bom"],
                              titulo="GW Teste")
    providers.definir("custom:teste-gw")

    os.environ["GR_UPSTREAM"] = ""
    import grpool
    grpool.UPSTREAM_FIXO = None
    import grserver
    import keyring
    keyring.reload(force=True)

    ok = falha = 0

    def checar(rot, cond, extra=""):
        nonlocal ok, falha
        if cond:
            ok += 1
            print("  [OK]    %s %s" % (rot, extra))
        else:
            falha += 1
            print("  [FALHA] %s %s" % (rot, extra))

    print("=== upstream usado pelo gateway ===")
    print("  ", grpool._upstream())
    checar("aponta pro custom", grpool._upstream() == base, grpool._upstream())

    porta_gw = 8940
    grserver.PORT = porta_gw
    grserver.State.keys = keyring.rotation()
    grserver.State.selected = "teste"
    grserver.State.routing = True
    grserver.State.model_map = {"teste": "teste"}
    grpool.POOL.load(grserver.State.keys)

    servidor = grserver.build()
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    time.sleep(0.8)

    print("\n=== chat real pelo gateway ===")
    recebidas.clear()
    req = urllib.request.Request(
        "http://127.0.0.1:%d/v1/chat/completions" % porta_gw,
        data=json.dumps({"model": "teste", "messages": [
            {"role": "user", "content": "oi"}]}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            dados = json.loads(r.read().decode())
        texto = dados["choices"][0]["message"]["content"]
        checar("resposta chegou", texto == "resposta do custom", texto)
    except urllib.error.HTTPError as e:
        checar("resposta chegou", False, "HTTP %d %s" % (e.code, e.read(200)))

    checar("upstream recebeu", len(recebidas) >= 1,
           "%d chamada(s)" % len(recebidas))
    if recebidas:
        usadas = [x["key"] for x in recebidas]
        ruins = usadas.count("sk-ruim")
        print("   chamadas: %d | key ruim tentada %d vez(es)"
              % (len(usadas), ruins))
        checar("resposta veio", "sk-bom" in usadas)
        checar("key ruim nao repete na cadeia", ruins <= 2,
               "%d tentativas (antes eram 168)" % ruins)
        checar("mandou no path certo",
               all(x["path"].endswith("/chat/completions") for x in recebidas))
        checar("modelo repassado",
               any(x["body"].get("model") == "teste" for x in recebidas))

    servidor.shutdown()
    providers.definir("nightrouter")
    custom_provider.remover("teste-gw")
    srv.shutdown()
    print("\n" + "=" * 46)
    print("  %d ok | %d falhas" % (ok, falha))
    return 0 if falha == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
