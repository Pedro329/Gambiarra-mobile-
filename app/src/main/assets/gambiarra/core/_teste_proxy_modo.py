"""O farm respeita o modo de proxy escolhido no CONFIG?

Antes o ProxyPool ignorava a config por completo: sempre coletava e
sempre devolvia proxy, qualquer que fosse a escolha da pessoa. Este
teste cobre os quatro modos que o farm pode receber.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import farmer_panel   # noqa: E402
import gerador_proxy  # noqa: E402
import navegadores    # noqa: E402

ok = falha = 0


def checar(rot, cond, extra=""):
    global ok, falha
    if cond:
        ok += 1
        print("  [OK]    %s %s" % (rot, extra))
    else:
        falha += 1
        print("  [FALHA] %s %s" % (rot, extra))


def pool(conf):
    """ProxyPool sem disparar coleta em background."""
    p = farmer_panel.ProxyPool.__new__(farmer_panel.ProxyPool)
    import threading
    p.want = 4
    p.conf = conf
    p.lock = threading.Lock()
    p.items = []
    p.seen = set()
    p.refreshing = False
    p._topping = False
    p.cycle = 0
    p.dry = 0
    p.last_took = 0.0
    return p


def main():
    print("=== 1. modo existe na tela ===")
    checar("gerador em MODOS", "gerador" in navegadores.MODOS)
    checar("rotulo do gerador",
           "Gerador Proxy [BETA]" in navegadores.ROTULO_MODO["gerador"],
           navegadores.ROTULO_MODO["gerador"])
    checar("nenhum deixa claro que e seu IP",
           "IP" in navegadores.ROTULO_MODO["nenhum"],
           navegadores.ROTULO_MODO["nenhum"])

    print("\n=== 2. modo 'nenhum' = conexao direta ===")
    p = pool({"proxy_modo": "nenhum"})
    checar("direto()", p.direto() is True)
    checar("take() devolve None", p.take() is None)
    checar("nao coleta", p.items == [])

    print("\n=== 3. modo 'rotativa' = URL fixa ===")
    url = "http://user:pass@127.0.0.1:8080"
    p = pool({"proxy_modo": "rotativa", "proxy_url": url})
    checar("nao e direto", p.direto() is False)
    checar("take() = url configurada", p.take() == url, str(p.take()))
    checar("fixo() devolve a url", p.fixo() == url)
    p2 = pool({"proxy_modo": "rotativa", "proxy_url": ""})
    checar("rotativa sem url -> None", p2.take() is None)

    print("\n=== 4. modo 'gerador' usa o gerador ===")
    p = pool({"proxy_modo": "gerador"})
    checar("modo lido", p.modo() == "gerador")
    checar("nao e direto", p.direto() is False)

    print("\n=== 5. modo 'auto' continua no coletor antigo ===")
    p = pool({"proxy_modo": "auto"})
    checar("modo auto", p.modo() == "auto")
    checar("nao e direto", p.direto() is False)
    checar("fixo() vazio no auto", p.fixo() == "")

    print("\n=== 6. conf ausente cai no padrao auto ===")
    p = pool({})
    checar("padrao auto", p.modo() == "auto")
    p = pool({"proxy_modo": ""})
    checar("vazio -> auto", p.modo() == "auto")

    print("\n=== 7. Farm recebe a config ===")
    conf = {"proxy_modo": "nenhum"}
    class Store:
        def count(self):
            return 0
    f = farmer_panel.Farm(Store(), 2, conf=conf)
    checar("Farm.conf guardado", f.conf == conf)
    checar("ProxyPool do farm em direto", f.proxies.direto() is True)
    checar("pool vazio no direto", f.proxies.items == [])
    f2 = farmer_panel.Farm(Store(), 2)
    checar("Farm sem conf -> dict", isinstance(f2.conf, dict))

    print("\n=== 8. gerador: prefixos ===")
    checar("eh_socks socks4://", gerador_proxy.eh_socks("socks4://1.2.3.4:1080"))
    checar("eh_socks http", not gerador_proxy.eh_socks("1.2.3.4:8080"))
    checar("limpar_endereco",
           gerador_proxy.limpar_endereco("socks4://1.2.3.4:1080") == "1.2.3.4:1080")
    checar("limpar_endereco http",
           gerador_proxy.limpar_endereco("http://1.2.3.4:80") == "1.2.3.4:80")

    print("\n" + "=" * 46)
    print("  %d ok | %d falhas" % (ok, falha))
    return 0 if falha == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
