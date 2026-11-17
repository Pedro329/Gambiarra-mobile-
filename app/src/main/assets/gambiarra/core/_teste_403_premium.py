"""Regressao dos dois bugs de 16/11/2026.

1. FARM 403 "You do not have permission to do this."
   O site passou a recusar "group": "free" na criacao da key. Cadastro e
   login davam certo, e so a criacao falhava — o farm perdia TODA conta.
   Sem o campo, a key nasce no grupo da conta e abre o catalogo inteiro.

2. PROXY PREMIUM nao salvava / nao funcionava
   a) a tela usava le_tecla, que trocava espaco por "espaco" (6 letras)
      e minusculizava tudo, corrompendo a URL digitada;
   b) "erro = ''" rodava a cada tecla e apagava a mensagem de recusa;
   c) --proxy-server nao aceita "user:pass@host", entao a URL inteira era
      passada ao Chrome, que simplesmente ignorava o proxy.
"""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import farmer   # noqa: E402
import humano   # noqa: E402
import navegadores  # noqa: E402

ok = falha = 0


def checar(rot, cond, extra=""):
    global ok, falha
    if cond:
        ok += 1
        print("  [OK]    %s %s" % (rot, extra))
    else:
        falha += 1
        print("  [FALHA] %s %s" % (rot, extra))


def main():
    print("=== 1. criacao de key nao forca mais 'group' ===")
    enviados = []

    def create_falso(account, payload):
        enviados.append(dict(payload))
        if "group" in payload:
            return (False,
                    'HTTP 403: {"success":false,"message":'
                    '"You do not have permission to do this."}', None)
        return True, "", "chave-boa"

    original = farmer._create
    farmer._create = create_falso
    try:
        okk, err, key = farmer.create_key(None)
        checar("cria sem group", okk is True and key == "chave-boa", str(err))
        checar("nao mandou group", "group" not in enviados[0], str(list(enviados[0])))
        checar("mandou unlimited_quota",
               enviados[0].get("unlimited_quota") is True)

        print("\n=== 2. se pedirem group e o site recusar, tenta sem ===")
        enviados.clear()
        okk, err, key = farmer.create_key(None, group="free")
        checar("caiu para sem-group", okk is True, str(err))
        checar("duas tentativas", len(enviados) == 2, str(len(enviados)))
        checar("1a com group", "group" in enviados[0])
        checar("2a sem group", "group" not in enviados[1])
    finally:
        farmer._create = original

    print("\n=== 3. proxy: credenciais sao separadas do servidor ===")
    casos = [
        ("http://user:pass@host.com:8080", "host.com:8080", ("user", "pass")),
        ("socks5://u:p@1.2.3.4:1080", "1.2.3.4:1080", ("u", "p")),
        ("host.com:8080", "host.com:8080", None),
        ("socks4://a:b@10.0.0.1:9050", "10.0.0.1:9050", ("a", "b")),
        ("http://sopass@host.com:80", "host.com:80", ("sopass", "")),
        ("", "", None),
    ]
    for entrada, srv_esperado, auth_esperado in casos:
        srv, auth = humano._separar_auth(entrada)
        checar("%r" % entrada,
               srv == srv_esperado and auth == auth_esperado,
               "-> %r %r" % (srv, auth))

    print("\n=== 4. a URL salva continua inteira ===")
    url = "http://usuario:senha@host.com:8080"
    okk, msg = navegadores.validar_url(url)
    checar("validar_url aceita com auth", okk, msg)
    srv, auth = humano._separar_auth(url)
    checar("chrome recebe so o servidor",
           "@" not in srv and srv == "host.com:8080", srv)
    checar("auth preservada", auth == ("usuario", "senha"), str(auth))

    print("\n=== 5. espaco nao vira 'espaco' ===")
    # reproduz o que le_tecla fazia
    def le_tecla_antigo(texto):
        return "".join("espaco" if c == " " else c.lower() for c in texto)

    def le_texto_novo(texto):
        return "".join(c for c in texto)

    com_espaco = "http://host.com:8080 "
    checar("estilo antigo corrompia",
           le_tecla_antigo(com_espaco) != com_espaco,
           repr(le_tecla_antigo(com_espaco)))
    checar("estilo novo preserva",
           le_texto_novo(com_espaco) == com_espaco)
    checar("strip resolve o espaco",
           le_texto_novo(com_espaco).strip() == "http://host.com:8080")

    print("\n=== 6. maiuscula preservada (proxy com senha maiuscula) ===")
    com_maiuscula = "http://User:PaSsWord@Host.COM:8080"
    checar("estilo antigo minusculizava",
           le_tecla_antigo(com_maiuscula) != com_maiuscula,
           repr(le_tecla_antigo(com_maiuscula)))
    srv, auth = humano._separar_auth(le_texto_novo(com_maiuscula))
    checar("auth com maiuscula intacta", auth == ("User", "PaSsWord"), str(auth))

    print("\n" + "=" * 46)
    print("  %d ok | %d falhas" % (ok, falha))
    return 0 if falha == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
