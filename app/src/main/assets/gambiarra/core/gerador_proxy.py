"""Gerador de proxy [BETA].

Coleta listas frescas de proxy publico, testa com o checker que ja
existe no proxies.py e devolve so os que respondem de verdade.

Fontes:
    http    -> ProxyScrape v2 (ssl=all, anonymity=all)
    socks4  -> ProxyScrape v2 (socks4)

Formato do item devolvido:
    "host:porta"          http
    "socks4://host:porta" socks4

O prefixo socks4:// e o que o Chrome aceita em --proxy-server e o que
o proxies.py usa para saber qual handshake fazer.
"""
import queue
import socket
import ssl
import threading
import time

import proxies

FONTE_HTTP = ("https://api.proxyscrape.com/v2/?request=getproxies"
              "&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all")
FONTE_SOCKS4 = ("https://api.proxyscrape.com/v2/?request=getproxies"
                "&protocol=socks4&timeout=10000&country=all")

PREFIXO_SOCKS4 = "socks4://"

# host de teste: mesmo do checker do proxies.py
CHECK_HOST = proxies.CHECK_HOST
CHECK_PORT = 443


def eh_socks(proxy):
    return bool(proxy) and proxy.startswith(PREFIXO_SOCKS4)


def limpar_endereco(proxy):
    """"socks4://1.2.3.4:1080" -> "1.2.3.4:1080" """
    if not proxy:
        return ""
    p = proxy.strip()
    for pre in (PREFIXO_SOCKS4, "http://", "https://"):
        if p.startswith(pre):
            return p[len(pre):]
    return p


def baixar(protocolo="http", timeout=30):
    """Lista crua da fonte escolhida."""
    url = FONTE_SOCKS4 if protocolo == "socks4" else FONTE_HTTP
    try:
        bruto = proxies._fetch(url, timeout=timeout)
    except Exception:
        return []
    if isinstance(bruto, bytes):
        bruto = bruto.decode("utf-8", "replace")
    saida = []
    for linha in (bruto or "").splitlines():
        linha = linha.strip()
        if not linha or ":" not in linha or " " in linha:
            continue
        host, _, porta = linha.partition(":")
        try:
            if not (1 <= int(porta) <= 65535):
                continue
        except ValueError:
            continue
        # ATENCAO: aqui `protocolo` e "socks4"/"http", nao um endereco.
        # Usar eh_socks() daqui devolvia False sempre (ele procura o
        # prefixo "socks4://") e nenhum SOCKS4 era marcado como tal.
        if protocolo == "socks4":
            saida.append(PREFIXO_SOCKS4 + host + ":" + porta)
        else:
            saida.append(host + ":" + porta)
    return saida


# ------------------------------------------------------------- handshake
def _conectar_socks4(proxy, host, port, timeout=8):
    """Abre um tunel SOCKS4a e devolve o socket (ou None)."""
    end = limpar_endereco(proxy)
    phost, _, pport = end.partition(":")
    try:
        raw = socket.create_connection((phost, int(pport)), timeout=timeout)
    except Exception:
        return None
    try:
        try:
            ip = socket.inet_aton(socket.gethostbyname(host))
            pedido = (b"\x04\x01" + port.to_bytes(2, "big") + ip
                      + b"\x00")
        except OSError:
            # SOCKS4a: 0.0.0.1 + nome do host
            pedido = (b"\x04\x01" + port.to_bytes(2, "big")
                      + b"\x00\x00\x00\x01" + b"\x00"
                      + host.encode() + b"\x00")
        raw.sendall(pedido)
        resp = raw.recv(8)
        if len(resp) < 8 or resp[0] != 0x00 or resp[1] != 0x5A:
            raw.close()
            return None
        return raw
    except Exception:
        try:
            raw.close()
        except OSError:
            pass
        return None


def testar(proxy, timeout=8):
    """(proxy, segundos) se funciona de verdade; None se nao."""
    if not proxy:
        return None
    t0 = time.time()
    if eh_socks(proxy):
        # SOCKS4 nao faz CONNECT: testa TLS de verdade
        raw = _conectar_socks4(proxy, CHECK_HOST, CHECK_PORT, timeout=timeout)
        if raw is None:
            return None
        try:
            raw.settimeout(timeout)
            ctx = ssl.create_default_context()
            # proxy residencial costuma terminar o TLS em outro lugar:
            # aceita o certificado e prova o conteudo, que e o que importa
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            tls = ctx.wrap_socket(raw, server_hostname=CHECK_HOST)
            tls.sendall(("HEAD / HTTP/1.1\r\nHost: %s\r\n"
                         "User-Agent: %s\r\nConnection: close\r\n\r\n"
                         % (CHECK_HOST, proxies.UA)).encode())
            dados = tls.recv(200)
            tls.close()
        except Exception:
            try:
                raw.close()
            except OSError:
                pass
            return None
        if not dados.startswith(b"HTTP/"):
            return None
        return proxy, time.time() - t0
    # http usa o checker que ja existia
    try:
        return proxies.check(proxy, timeout=timeout)
    except Exception:
        return None


def verificar(candidatos, workers=120, time_budget=25):
    """Testa tudo em paralelo e devolve os vivos, mais rapido primeiro."""
    vivos = []
    trava = threading.Lock()
    fila = queue.Queue()
    for c in candidatos:
        fila.put(c)
    fim = time.time() + time_budget

    def operario():
        while True:
            if time.time() > fim:
                return
            try:
                item = fila.get_nowait()
            except queue.Empty:
                return
            try:
                r = testar(item)
            except Exception:
                r = None
            if r:
                with trava:
                    vivos.append(r)

    threads = [threading.Thread(target=operario, daemon=True)
               for _ in range(min(workers, max(1, len(candidatos))))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=max(1, fim - time.time() + 5))
    vivos.sort(key=lambda x: x[1])
    return vivos


def gerar(target=40, protocolos=("http", "socks4"), time_budget=25,
          workers=120, progresso=None):
    """Coleta + verifica. Devolve (vivos, bruto_por_protocolo).

    vivos -> [(proxy, segundos)]
    bruto -> {"http": [...], "socks4": [...]}
    """
    bruto = {}
    por_proto = []
    for proto in protocolos:
        lista = baixar(proto)
        bruto[proto] = lista
        if progresso:
            try:
                progresso(proto, len(lista))
            except Exception:
                pass
        por_proto.append(lista)
    # INTERCALA as fontes. Antes o http (600+) enchia a fila e o
    # time_budget acabava antes de chegar no socks4 (130), entao o
    # socks4 nunca era testado.
    candidatos = []
    vistos = set()
    i = 0
    while any(i < len(l) for l in por_proto):
        for lista in por_proto:
            if i < len(lista):
                c = lista[i]
                if c not in vistos:
                    vistos.add(c)
                    candidatos.append(c)
        i += 1
    if not candidatos:
        return [], bruto
    vivos = verificar(candidatos, workers=workers, time_budget=time_budget)
    return vivos[:max(1, target)], bruto


def salvar(vivos):
    """Grava no cache do proxies.py para o farm reaproveitar."""
    try:
        proxies.save(vivos)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    t0 = time.time()
    vivos, bruto = gerar(target=40)
    for proto, lista in bruto.items():
        print("%-7s bruto: %d" % (proto, len(lista)))
    print("vivos : %d  (%.1fs)" % (len(vivos), time.time() - t0))
    for p, ms in vivos[:15]:
        print("   %-30s %.2fs" % (p, ms))
