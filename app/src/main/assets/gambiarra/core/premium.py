"""Proxies Premium do ProxyScrape (arquivo do usuario).

Formato: usuario:senha@ip:porta
O Chrome aceita embutido na URL: http://usuario:senha@ip:porta
"""
import os
import random

ARQ = os.path.join(os.path.expanduser("~"), "Downloads",
                   "proxyscrape_premium_http_proxies.txt")


def carregar(caminho=None):
    caminho = caminho or ARQ
    if not os.path.exists(caminho):
        return []
    saida = []
    with open(caminho, encoding="utf-8", errors="replace") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            if "@" in linha and ":" in linha:
                saida.append("http://" + linha)
            elif linha.count(":") == 1:
                saida.append("http://" + linha)
    # sem repeticao, mantendo a ordem
    vistos = set()
    unicos = []
    for p in saida:
        if p not in vistos:
            vistos.add(p)
            unicos.append(p)
    return unicos


def embaralhar(lista):
    copia = list(lista)
    random.shuffle(copia)
    return copia


if __name__ == "__main__":
    l = carregar()
    print("carregados:", len(l))
    for p in l[:5]:
        # nao imprime a senha inteira
        print("  ", p.split("@")[0][:14] + "***@" + p.split("@")[1])
