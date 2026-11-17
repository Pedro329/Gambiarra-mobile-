"""Seleciona proxies que funcionam nos DOIS alvos: routerplex e emailnator.

Um proxy que serve para o RouterPlex mas nao abre o emailnator e inutil
para o fluxo. Testa os dois e so devolve quem passa em ambos.
"""
import ssl
import threading
import time

import proxies

ALVOS = [
    ("routerplex.com", "/sign-up"),
    ("www.emailnator.com", "/"),
]

UA = proxies.UA
TIMEOUT = 10

# marcadores de bloqueio do cloudflare
BLOQUEIO = (b"Just a moment", b"_cf_chl_opt",
            b"Sorry, you have been blocked", b"cf-mitigated")


def _testar_alvo(proxy, host, caminho, timeout=TIMEOUT):
    """Devolve (ok, ms) para um host."""
    t0 = time.time()
    s = None
    try:
        s = proxies._tunnel(proxy, host, timeout=timeout)
        if s is None:
            return False, 0
        s.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: %s\r\n"
                   "Accept: text/html,application/xhtml+xml\r\n"
                   "Accept-Language: pt-BR,pt;q=0.9,en;q=0.8\r\n"
                   "Connection: close\r\n\r\n" % (caminho, host, UA)).encode())
        dados = b""
        s.settimeout(timeout)
        while len(dados) < 6000:
            try:
                d = s.recv(8192)
            except Exception:
                break
            if not d:
                break
            dados += d
        if not dados.startswith(b"HTTP/"):
            return False, 0
        try:
            status = int(dados.split(b" ", 2)[1])
        except Exception:
            return False, 0
        if status != 200:
            return False, 0
        for marca in BLOQUEIO:
            if marca in dados:
                return False, 0
        # tem que ter conteudo de verdade
        if len(dados) < 1500:
            return False, 0
        return True, int((time.time() - t0) * 1000)
    except Exception:
        return False, 0
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass


def proxy_serve(proxy, timeout=TIMEOUT):
    """True se o proxy passa nos dois alvos. Devolve (ok, ms_total)."""
    total = 0
    for host, caminho in ALVOS:
        ok, ms = _testar_alvo(proxy, host, caminho, timeout)
        if not ok:
            return False, 0
        total += ms
    return True, total


def bons(quantidade=5, limite_candidatos=400, workers=120):
    """Coleta e filtra em paralelo. Sempre devolve algo ou lista vazia."""
    print("  coletando listas de proxies...")
    try:
        todos = sorted(proxies.collect(limit=8000))
    except Exception as e:
        print("  erro ao coletar:", str(e)[:70])
        todos = []
    if not todos:
        return []

    # primeiro filtro rapido: tunnel no routerplex
    print("  %d candidatos; fase 1 (routerplex)..." % len(todos))
    fase1 = []
    trava = threading.Lock()

    def f1(p):
        ok, ms = _testar_alvo(p, "routerplex.com", "/sign-up", timeout=8)
        if ok:
            with trava:
                fase1.append(p)

    _rodar(todos[:limite_candidatos], f1, workers)
    print("  fase 1: %d passaram" % len(fase1))

    if not fase1:
        return []

    print("  fase 2 (emailnator)...")
    finais = []
    trava2 = threading.Lock()

    def f2(p):
        ok, ms = _testar_alvo(p, "www.emailnator.com", "/", timeout=10)
        if ok:
            with trava2:
                finais.append((ms, p))

    _rodar(fase1, f2, workers)
    finais.sort()
    print("  fase 2: %d servem para os dois" % len(finais))
    return [p for _, p in finais[:quantidade]]


def _rodar(lista, funcao, workers):
    fila = list(lista)
    trava = threading.Lock()

    def trab():
        while True:
            with trava:
                if not fila:
                    return
                item = fila.pop(0)
            try:
                funcao(item)
            except Exception:
                pass

    ts = [threading.Thread(target=trab, daemon=True)
          for _ in range(min(workers, max(1, len(lista))))]
    for t in ts:
        t.start()
    for t in ts:
        t.join()


if __name__ == "__main__":
    import sys
    q = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    r = bons(q)
    print()
    print("BONS (%d):" % len(r))
    for p in r:
        print("  ", p)
