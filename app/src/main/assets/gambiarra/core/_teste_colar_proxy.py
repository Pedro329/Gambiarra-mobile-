"""Regressao: colar/editar a URL do proxy rotativo.

Bug de 16/11/2026 — a tela de proxy consumia DUAS teclas por volta do
laco: mp.le_tecla(0.09) na linha de cima e mp.le_texto(0.09) dentro do
bloco de edicao. Cada volta descartava uma tecla, entao uma colagem de
52 caracteres chegava mutilada na tela ("ht:/..." em vez de
"http://..."), e o usuario achava que a tela estava travada.

Tambem: a tecla "colar" (Ctrl+V / botao direito) caia no ramo
"len(tecla)==1", que era falso para a string "colar" — descarte silencioso.
Agora ela chama mp.colar_area() e insere o texto inteiro de uma vez.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import navegadores   # noqa: E402

ok = falha = 0


def checar(rot, cond, extra=""):
    global ok, falha
    if cond:
        ok += 1
        print("  [OK]    %s %s" % (rot, extra))
    else:
        falha += 1
        print("  [FALHA] %s %s" % (rot, extra))


# ---- simulacao fiel do laco da tela de proxy -------------------------

def laco_antigo(teclas):
    """Como era: le_tecla na linha de cima, le_texto na edicao."""
    fila = list(teclas)
    buffer = ""
    i = 0
    while i < len(fila):
        tecla_cima = fila[i]          # mp.le_tecla(0.09)
        i += 1
        if tecla_cima is None:
            continue
        if tecla_cima == "enter":
            break
        # dentro de editando: mp.le_texto(0.09) consome OUTRA tecla
        if i < len(fila):
            tecla = fila[i]
            i += 1
            if tecla and len(tecla) == 1:
                buffer += tecla
    return buffer


def laco_novo(teclas):
    """Como ficou: uma unica leitura por volta."""
    buffer = ""
    for tecla in teclas:
        if tecla is None:
            continue
        if tecla == "enter":
            break
        if tecla == "colar":
            continue          # tratado a parte, por colar_area()
        if len(tecla) == 1:
            buffer += tecla
    return buffer


def main():
    url = "http://usuario-exemplo:senha-exemplo@proxy.exemplo.com:8080"
    teclas = list(url) + ["enter"]

    print("=== 1. colagem de 52 caracteres ===")
    antigo = laco_antigo(teclas)
    novo = laco_novo(teclas)
    checar("laco antigo perdia metade",
           antigo != url, "%d/%d chars %r" % (len(antigo), len(url), antigo[:12]))
    checar("laco novo preserva tudo",
           novo == url, "%d/%d chars" % (len(novo), len(url)))

    print("\n=== 2. exatamente a mutilacao relatada ===")
    # perdia 1 de cada 2 caracteres: "http://" -> "tp/e" (o "tp/" da tela)
    checar("antigo perdia os caracteres pares",
           len(antigo) == len(novo) // 2, "%d vs %d" % (len(antigo), len(novo)))
    checar("antigo comecava no meio do 'http://'",
           antigo.startswith("tp/"), antigo[:8])
    checar("novo comeca com 'http://'", novo.startswith("http://"), novo[:8])

    print("\n=== 3. tecla 'colar' nao some mais ===")
    # a string "colar" tem 5 chars; o ramo antigo exigia len==1
    so_colar = laco_novo(["colar", "enter"])
    checar("'colar' nao vira texto", so_colar == "", repr(so_colar))
    checar("'colar' escapa do filtro de 1 char",
           len("colar") != 1, "len=%d" % len("colar"))

    print("\n=== 4. a URL que o usuario colou e valida ===")
    okk, msg = navegadores.validar_url(url)
    checar("validar_url aceita", okk, msg)

    print("\n=== 5. limpeza de quebra de linha da colagem ===")
    com_lixo = url + "\r\n"
    limpo = com_lixo.strip().replace("\r", "").replace("\n", "")
    checar("quebra de linha removida", limpo == url, repr(limpo[-6:]))

    print("\n=== 6. proxy com auth: servidor e auth separados ===")
    import humano
    srv, auth = humano._separar_auth(url)
    checar("servidor", srv == "proxy.exemplo.com:8080", srv)
    checar("usuario", auth and auth[0] == "usuario-exemplo", str(auth))
    checar("senha", auth and auth[1] == "senha-exemplo", str(auth))

    print("\n" + "=" * 46)
    print("  %d ok | %d falhas" % (ok, falha))
    return 0 if falha == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
