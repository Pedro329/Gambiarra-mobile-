"""Teste do Custom Provider de ponta a ponta (sem GUI).

1. cria um custom apontando para um servidor local falso
2. confere que ele entra no catalogo de providers
3. confere que as keys dele viram a fila de rotacao
4. confere o fallback para o NightRouter quando nao e custom
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import custom_provider
import keyring
import providers


# ---- servidor falso compativel com OpenAI
class Falso(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith("/models"):
            auth = self.headers.get("Authorization", "")
            corpo = {"object": "list",
                     "data": [{"id": "teste-a"}, {"id": "teste-b"}]}
            if "ruim" in auth:
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b'{"error":"bad key"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(corpo).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


def main():
    porta = 8931
    srv = HTTPServer(("127.0.0.1", porta), Falso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d/v1" % porta

    ok = 0
    falha = 0

    def checar(rotulo, cond, extra=""):
        nonlocal ok, falha
        if cond:
            ok += 1
            print("  [OK]    %s %s" % (rotulo, extra))
        else:
            falha += 1
            print("  [FALHA] %s %s" % (rotulo, extra))

    print("=== 1. cadastro do custom ===")
    # limpa teste anterior
    custom_provider.remover("teste-local")
    prov = custom_provider.adicionar("teste-local", base,
                                     ["sk-alfa", "sk-beta", "sk-gama"],
                                     titulo="Local Teste")
    checar("salvou base", prov["base"] == base, prov["base"])
    checar("3 keys", len(prov["keys"]) == 3, str(prov["keys"]))

    print("\n=== 2. entra no catalogo ===")
    nomes = [p["nome"] for p in providers.catalogo()]
    checar("custom no catalogo", "custom:teste-local" in nomes, str(nomes))
    checar("nightrouter continua", "nightrouter" in nomes)

    print("\n=== 3. ativa e confere base_url ===")
    providers.definir("custom:teste-local")
    checar("nome_atual", providers.nome_atual() == "custom:teste-local",
           providers.nome_atual())
    checar("base_url_atual", providers.base_url_atual() == base,
           providers.base_url_atual())

    print("\n=== 4. keys do custom viram rotacao ===")
    keyring.reload(force=True)
    rot = keyring.rotation()
    checar("rotacao tem as 3", set(rot) == {"sk-alfa", "sk-beta", "sk-gama"},
           str(rot))
    s = keyring.sources()
    checar("fonte unica custom", len(s) == 1, str([x[0] for x in s]))

    print("\n=== 5. teste de conexao ===")
    o, msg = custom_provider.testar(prov, "sk-alfa")
    checar("testar ok", o, msg)
    checar("2 modelos", msg == "2 modelos", msg)
    o2, msg2 = custom_provider.testar(prov, "ruim")
    checar("key ruim recusada", not o2, msg2)

    print("\n=== 6. adicionar keys depois ===")
    total = custom_provider.adicionar_keys("teste-local", ["sk-delta"])
    checar("agora 4 keys", total == 4, str(total))
    keyring.reload(force=True)
    checar("rotacao 4", len(keyring.rotation()) == 4)

    print("\n=== 7. volta pro nightrouter ===")
    providers.definir("nightrouter")
    checar("nome voltou", providers.nome_atual() == "nightrouter")
    checar("base voltou",
           providers.base_url_atual() == "https://api.nightrouter.ai/v1",
           providers.base_url_atual())
    keyring.reload(force=True)
    checar("rotacao nao usa custom",
           "sk-alfa" not in keyring.rotation())

    print("\n=== 8. limpeza ===")
    custom_provider.remover("teste-local")
    checar("removido", custom_provider.por_nome("teste-local") is None)
    checar("sumiu do catalogo",
           "custom:teste-local" not in [p["nome"] for p in providers.catalogo()])

    srv.shutdown()
    print("\n" + "=" * 46)
    print("  %d ok | %d falhas" % (ok, falha))
    return 0 if falha == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
