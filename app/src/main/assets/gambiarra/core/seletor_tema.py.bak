"""Tela de escolha do tema, na primeira execucao.

Roda antes de tudo: sem ela o programa nao sabe se desenha em vermelho
(LEGACY) ou em arco-iris (INFINITE).
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import temas

try:
    import msvcrt
except ImportError:
    msvcrt = None


def _le_tecla():
    """Seta / enter / esc, ou None."""
    if msvcrt is None:
        return sys.stdin.read(1)
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):
        code = msvcrt.getwch()
        return {"H": "cima", "P": "baixo", "K": "esq", "M": "dir"}.get(code)
    if ch in ("\r", "\n"):
        return "enter"
    if ch == "\x1b":
        return "esc"
    if ch == "\x03":
        raise KeyboardInterrupt
    return ch


def _moldura_legacy(linhas, largura):
    p = temas.LEGACY_PALETA
    topo = p["escura"] + "╭" + "─" * (largura - 2) + "╮" + temas.RESET
    base = p["escura"] + "╰" + "─" * (largura - 2) + "╯" + temas.RESET
    corpo = []
    for l in linhas:
        vis = temas.largura_visivel(l)
        corpo.append(p["escura"] + "│" + temas.RESET + l
                     + " " * max(0, largura - 2 - vis)
                     + p["escura"] + "│" + temas.RESET)
    return [topo] + corpo + [base]


def _moldura_infinity(linhas, largura, t):
    topo_p = []
    for i in range(largura):
        r, g, b = temas.arco_iris(i / float(largura) + t * 0.2, brilho=0.7)
        topo_p.append(temas.rgb(r, g, b) + "─")
    topo = temas.rgb(140, 120, 255) + "╭" + "".join(topo_p[1:-1]) + \
        temas.rgb(140, 120, 255) + "╮" + temas.RESET
    base = temas.rgb(140, 120, 255) + "╰" + "".join(topo_p[1:-1]) + \
        temas.rgb(140, 120, 255) + "╯" + temas.RESET
    corpo = []
    for l in linhas:
        vis = temas.largura_visivel(l)
        corpo.append(temas.rgb(140, 120, 255) + "│" + temas.RESET + l
                     + " " * max(0, largura - 2 - vis)
                     + temas.rgb(140, 120, 255) + "│" + temas.RESET)
    return [topo] + corpo + [base]


def _cartao_legacy(escolhido, largura):
    p = temas.LEGACY_PALETA
    linhas = []
    titulo = "ESCOLHA O TEMA"
    linhas.append(temas.centralizar(
        p["brilho"] + temas.BOLD + titulo + temas.RESET, largura - 2))
    linhas.append("")
    opcoes = [
        ("LEGACY", "tema classico", temas.LEGACY),
        ("INFINITE", "tema moderno", temas.INFINITY),
    ]
    for i, (nome, desc, _chave) in enumerate(opcoes):
        sel = (i == escolhido)
        if sel:
            marca = p["destaque"] + "▸ " + temas.RESET
            nome_txt = p["fundo_destaque"] + temas.BOLD + " " + nome.ljust(11) + temas.RESET
            desc_txt = p["texto"] + desc + temas.RESET
        else:
            marca = "  "
            nome_txt = p["texto2"] + " " + nome.ljust(11) + temas.RESET
            desc_txt = p["fraco"] + desc + temas.RESET
        linhas.append("  " + marca + nome_txt + "  " + desc_txt)
    linhas.append("")
    linhas.append("  " + p["fraco"] + "setas escolhem   enter confirma"
                  + temas.RESET)
    linhas.append("  " + p["fraco"] + "da para trocar depois em CONFIG"
                  + temas.RESET)
    return linhas


def _cartao_infinity(escolhido, largura, t):
    linhas = []
    titulo = temas.rolar_arco("ESCOLHA O TEMA", t, brilho=1.0)
    linhas.append(temas.centralizar(temas.BOLD + titulo + temas.RESET, largura - 2))
    linhas.append("")
    opcoes = [
        ("LEGACY", "tema classico", temas.LEGACY),
        ("INFINITE", "tema moderno", temas.INFINITY),
    ]
    for i, (nome, desc, _chave) in enumerate(opcoes):
        sel = (i == escolhido)
        if sel:
            marca = temas.rolar_arco("▸ ", t)
            nome_txt = (temas.rgb(90, 70, 200, fundo=True) + temas.BOLD
                        + " " + nome.ljust(11) + temas.RESET)
            desc_txt = temas.INFINITY_PALETA["texto"] + desc + temas.RESET
        else:
            marca = "  "
            nome_txt = temas.INFINITY_PALETA["texto2"] + " " + nome.ljust(11) + temas.RESET
            desc_txt = temas.INFINITY_PALETA["fraco"] + desc + temas.RESET
        linhas.append("  " + marca + nome_txt + "  " + desc_txt)
    linhas.append("")
    linhas.append("  " + temas.INFINITY_PALETA["fraco"]
                  + "setas escolhem   enter confirma" + temas.RESET)
    linhas.append("  " + temas.INFINITY_PALETA["fraco"]
                  + "da para trocar depois em CONFIG" + temas.RESET)
    return linhas


def escolher(preview=True, tema_inicial=None):
    """Roda a tela. Devolve o tema escolhido e salva no config."""
    try:
        cols = os.get_terminal_size().columns
        linhas_tela = os.get_terminal_size().lines
    except OSError:
        cols, linhas_tela = 100, 30

    largura = max(56, min(cols - 2, 100))
    escolhido = 0
    if tema_inicial == temas.INFINITY:
        escolhido = 1

    # o preview do ascii usa o tema que esta sob o cursor
    def desenha(t):
        atual = temas.INFINITY if escolhido == 1 else temas.LEGACY
        blocos = []
        if preview:
            ascii_linhas = temas.ascii_do_tema(atual)
            if atual == temas.INFINITY:
                ascii_linhas = temas.limpar_ascii(ascii_linhas, largura - 6)
                pintado = temas.pintar_ascii_infinity(ascii_linhas, t)
            else:
                ascii_linhas = ascii_linhas[:12]
                if ascii_linhas:
                    maior = max(len(l) for l in ascii_linhas)
                    if maior > largura - 6:
                        fator = (largura - 6) / float(maior)
                        ascii_linhas = ["".join(l[int(i / fator)]
                                                for i in range(int(len(l) * fator)))
                                        for l in ascii_linhas]
                pintado = temas.pintar_ascii_legacy(ascii_linhas)
            for l in pintado:
                blocos.append(temas.centralizar(l, largura - 2))
            blocos.append("")

        if atual == temas.INFINITY:
            cabecalho = _cartao_infinity(escolhido, largura, t)
            corpo = blocos + cabecalho
            caixa = _moldura_infinity(corpo, largura, t)
        else:
            cabecalho = _cartao_legacy(escolhido, largura)
            corpo = blocos + cabecalho
            caixa = _moldura_legacy(corpo, largura)
        rodape = ""
        if len(caixa) + 2 < linhas_tela:
            if atual == temas.INFINITY:
                rodape = temas.centralizar(
                    temas.rolar_arco(temas.DISCORD, t, brilho=0.8), largura)
            else:
                rodape = temas.centralizar(
                    temas.LEGACY_PALETA["suave"] + temas.DISCORD + temas.RESET,
                    largura)
        return caixa + (["", rodape] if rodape else [])

    sys.stdout.write("\x1b[?25l")
    try:
        t0 = time.time()
        ultimo = None
        while True:
            t = time.time() - t0
            linhas = desenha(t)
            # redesenha no lugar, sem empurrar para o historico
            out = ["\x1b[H"]
            for i, l in enumerate(linhas):
                out.append(l + "\x1b[K")
                if i != len(linhas) - 1:
                    out.append("\r\n")
            out.append("\x1b[J")
            sys.stdout.write("".join(out))
            sys.stdout.flush()

            # espera uma tecla, mas atualiza a animacao a cada 90ms
            tecla = _espera_tecla(0.09)
            if tecla is None:
                continue
            if tecla in ("cima", "k"):
                escolhido = (escolhido - 1) % 2
            elif tecla in ("baixo", "j"):
                escolhido = (escolhido + 1) % 2
            elif tecla == "1":
                escolhido = 0
            elif tecla == "2":
                escolhido = 1
            elif tecla == "esc":
                escolhido = 0
                tecla = "enter"
            if tecla == "enter":
                tema = temas.INFINITY if escolhido == 1 else temas.LEGACY
                conf = temas.carregar()
                conf["tema"] = tema
                conf["primeira_vez"] = False
                temas.salvar(conf)
                return tema
    finally:
        sys.stdout.write("\x1b[?25h\x1b[2J\x1b[H")
        sys.stdout.flush()


_KEYBUF = []


def _espera_tecla(segundos):
    """Le tecla sem bloquear mais que `segundos`."""
    if msvcrt is None:
        import select
        pronto, _, _ = select.select([sys.stdin], [], [], segundos)
        if not pronto:
            return None
        return sys.stdin.read(1)
    if _KEYBUF:
        return _KEYBUF.pop(0)
    limite = time.time() + segundos
    while time.time() < limite:
        if msvcrt.kbhit():
            return _le_tecla()
        time.sleep(0.006)
    return None


def escolher_bloqueante(tema_inicial=None):
    """Versao simples para quando nao ha animacao (fallback)."""
    return escolher(preview=True, tema_inicial=tema_inicial)


if __name__ == "__main__":
    try:
        t = escolher()
        print("tema escolhido:", t)
    except KeyboardInterrupt:
        print()
