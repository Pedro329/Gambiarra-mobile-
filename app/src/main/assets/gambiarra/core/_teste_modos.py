"""Teste dos dois modos do Custom Provider, com upstream falso.

FREE  -> lista so gratuitos; rate limit NAO remove conta; rotaciona modelo
SALDO -> lista todos; erro de sem saldo REMOVE a conta e vai pra proxima
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

import custom_modo
import custom_provider
import providers

recebidas = []


def catalogo():
    """Catalogo com modelos gratuitos e pagos, dos 3 jeitos possiveis."""
    return {"data": [
        {"id": "modelo-a-free"},
        {"id": "modelo-b", "pricing": {"prompt": 0, "completion": 0}},
        {"id": "modelo-c", "free": True},
        {"id": "modelo-pago-1", "pricing": {"prompt": 0.5, "completion": 1.5}},
        {"id": "modelo-pago-2"},
    ]}


class Upstream(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(catalogo()).encode())

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(n) or b"{}")
        key = self.headers.get("Authorization", "").replace("Bearer ", "")
        recebidas.append({"key": key, "model": corpo.get("model")})

        # conta vazia: responde sem saldo em QUALQUER modelo
        if key == "sk-vazia":
            self.send_response(402)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {
                "message": "insufficient balance, please top up",
                "code": "insufficient_quota"}}).encode())
            return
        # conta limitada: rate limit em modelo-a, ok no resto
        if key == "sk-limitada" and corpo.get("model") == "modelo-a-free":
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {
                "message": "rate limit reached, too many requests"}}).encode())
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "id": "x", "object": "chat.completion", "created": 1,
            "model": corpo.get("model"),
            "choices": [{"index": 0, "message": {
                "role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                      "total_tokens": 2}}).encode())

    def log_message(self, *a):
        pass


def main():
    porta = 8933
    srv = HTTPServer(("127.0.0.1", porta), Upstream)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d/v1" % porta

    ok = falha = 0

    def checar(rot, cond, extra=""):
        nonlocal ok, falha
        if cond:
            ok += 1
            print("  [OK]    %s %s" % (rot, extra))
        else:
            falha += 1
            print("  [FALHA] %s %s" % (rot, extra))

    custom_provider.remover("modo-teste")
    custom_modo.reviver("modo-teste")

    print("=== 1. deteccao de modelo free ===")
    itens = catalogo()["data"]
    livres = [i["id"] for i in itens if custom_modo.modelo_free(i)]
    checar("3 gratuitos detectados",
           set(livres) == {"modelo-a-free", "modelo-b", "modelo-c"}, str(livres))
    pagos = [i["id"] for i in itens if not custom_modo.modelo_free(i)]
    checar("2 pagos fora", set(pagos) == {"modelo-pago-1", "modelo-pago-2"},
           str(pagos))

    print("\n=== 2. modo FREE lista so gratuitos ===")
    prov = custom_provider.adicionar("modo-teste", base, ["sk-boa"],
                                     titulo="Modo Teste", modo="free")
    ids, _ = custom_modo.listar(prov, "sk-boa", "free", forcar=True)
    checar("3 na lista", len(ids) == 3, str(ids))
    checar("nenhum pago", not any("pago" in i for i in ids), str(ids))

    print("\n=== 3. modo SALDO lista todos ===")
    ids2, _ = custom_modo.listar(prov, "sk-boa", "saldo", forcar=True)
    checar("5 na lista", len(ids2) == 5, str(ids2))

    print("\n=== 4. rate limit NAO mata a conta ===")
    checar("429 nao e sem saldo",
           not custom_modo.e_sem_saldo(429, "rate limit reached"))
    checar("429 e rate limit",
           custom_modo.e_rate_limit(429, "rate limit reached"))
    checar("402 e sem saldo",
           custom_modo.e_sem_saldo(402, "insufficient balance"))
    checar("402 nao e rate limit",
           not custom_modo.e_rate_limit(402, "insufficient balance"))

    print("\n=== 5. modo SALDO remove conta sem saldo ===")
    # a conta vazia vem PRIMEIRO na fila: o teste prova que ela e removida
    # e que o router segue para a proxima (sk-boa) em vez de morrer
    custom_modo.reviver("modo-teste")
    custom_provider.remover("modo-teste")
    custom_provider.adicionar("modo-teste", base,
                              ["sk-vazia", "sk-boa"], modo="saldo")
    custom_modo.definir_modo("modo-teste", "saldo")
    providers.definir("custom:modo-teste")
    import keyring
    import grpool
    import grserver

    chaves_antes = list(custom_provider.por_nome("modo-teste")["keys"])
    keyring.reload(force=True)
    # limpa marca de "morta" que sobrou de execucao anterior: rotation()
    # joga key morta para o fim da fila, e o teste precisa da vazia primeiro
    for k in chaves_antes:
        keyring.mark_live(k)
    keyring.reload(force=True)
    checar("base tem vazia + boa",
           set(chaves_antes) == {"sk-vazia", "sk-boa"}, str(chaves_antes))

    # o pool anda em circulo com cursor: reposiciona para a vazia primeiro
    # ATENCAO: rotation_keys() do gateway puxa de keyring, nao de State.keys.
    # Por isso a ordem tem de ser garantida na PROPRIA base do custom.
    checar("vazia vem primeiro na rotacao",
           grserver.rotation_keys()[0] == "sk-vazia",
           str(grserver.rotation_keys()))

    porta_gw = 8941
    grserver.PORT = porta_gw
    grserver.State.keys = ["sk-vazia", "sk-boa"]
    grserver.State.selected = "modelo-a-free"
    grserver.State.routing = True
    grserver.State.model_map = {"modelo-a-free": "modelo-a-free"}
    grpool.POOL.load(grserver.State.keys)
    with grpool.POOL.lock:
        grpool.POOL.cursor = 0
    servidor = grserver.build()
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    time.sleep(0.8)

    recebidas.clear()
    req = urllib.request.Request(
        "http://127.0.0.1:%d/v1/chat/completions" % porta_gw,
        data=json.dumps({"model": "modelo-a-free", "messages": [
            {"role": "user", "content": "oi"}]}).encode(),
        headers={"Content-Type": "application/json"})
    texto = ""
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            texto = json.loads(r.read().decode())["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        texto = "HTTP %d" % e.code
    print("      upstream recebeu:", recebidas)
    checar("respondeu com a conta boa", texto == "ok", texto)
    checar("tentou a conta vazia primeiro",
           any(x["key"] == "sk-vazia" for x in recebidas), str(recebidas))
    checar("conta vazia foi removida da base",
           "sk-vazia" not in custom_provider.por_nome("modo-teste")["keys"],
           str(custom_provider.por_nome("modo-teste")["keys"]))
    checar("registrou como morta",
           "sk-vazia" in custom_modo.listar_mortas("modo-teste"),
           str(list(custom_modo.listar_mortas("modo-teste").keys())))
    mortas = custom_modo.listar_mortas("modo-teste")
    if "sk-vazia" in mortas:
        print("      motivo: %s" % mortas["sk-vazia"]["motivo"][:70])

    servidor.shutdown()

    print("\n=== 6. reviver conta ===")
    custom_modo.reviver("modo-teste", "sk-vazia")
    checar("saiu do cemiterio",
           "sk-vazia" not in custom_modo.listar_mortas("modo-teste"))

    print("\n=== 7. NightRouter intacto ===")
    providers.definir("nightrouter")
    checar("provider padrao", providers.nome_atual() == "nightrouter")
    checar("_sem_saldo falso no night",
           grpool._sem_saldo(402, "insufficient balance") is False)
    keyring.reload(force=True)

    providers.definir("nightrouter")
    custom_modo.reviver("modo-teste")
    custom_provider.remover("modo-teste")
    srv.shutdown()
    print("\n" + "=" * 46)
    print("  %d ok | %d falhas" % (ok, falha))
    return 0 if falha == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
