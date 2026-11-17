"""Loading do tema INFINITE.

Sequencia:
  1. revelacao do ASCII letra por letra, em ordem aleatoria, com "decode"
  2. onda de brilho varrendo o logo
  3. barra de progresso arco-iris com particulas e metricas ao vivo
  4. saida com dissolve

Sem \x1b[2J: redesenha no lugar para nao empurrar o historico.
"""
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import temas

ESC = "\x1b["
HOME = ESC + "H"
LIMPA_LINHA = ESC + "K"
LIMPA_FIM = ESC + "J"

GLIFOS_DECODE = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%&*+=<>/\\|"
PARTICULAS = "·∙⋅*+×✦✧⋆"


def _tamanho():
    try:
        s = os.get_terminal_size()
        return max(40, s.columns), max(12, s.lines)
    except OSError:
        return 100, 30


def _tela(linhas, cols, rows):
    """Escreve as linhas por posicionamento absoluto.

    Sem \\r\\n: linha que enche a largura ja quebra sozinha no console,
    e o CRLF pularia duas linhas.
    """
    limite = max(0, rows - 1)
    out = []
    for i in range(limite):
        linha = linhas[i] if i < len(linhas) else ""
        out.append("\x1b[%d;1H" % (i + 1))
        out.append(limpa_espacos(linha, cols))
        out.append(LIMPA_LINHA)
    out.append("\x1b[%d;1H" % max(1, limite))
    out.append(LIMPA_FIM)
    sys.stdout.write("".join(out))
    sys.stdout.flush()


def limpa_espacos(texto, cols):
    visivel = temas.largura_visivel(texto)
    if visivel < cols:
        return texto + " " * (cols - visivel)
    return texto


def _centro(texto, cols):
    visivel = temas.largura_visivel(texto)
    return " " * max(0, (cols - visivel) // 2) + texto


def _ascii_compacto(cols):
    linhas = temas.limpar_ascii(temas.ascii_do_tema(temas.INFINITY), cols - 8)
    return [l for l in linhas if l.strip()]


def fase_decodificar(cols, rows, duracao=1.5):
    """Revela o ASCII embaralhando os caracteres ate acertar."""
    logo = _ascii_compacto(cols)
    if not logo:
        return
    # lista de (linha, coluna) que precisam ser reveladas
    pontos = []
    for y, linha in enumerate(logo):
        for x, ch in enumerate(linha):
            if ch != " ":
                pontos.append((y, x))
    random.shuffle(pontos)

    topo = max(0, (rows - len(logo)) // 2 - 3)
    total = len(pontos)
    t0 = time.time()
    while True:
        t = time.time() - t0
        fracao = min(1.0, t / duracao)
        revelados = int(fracao * total)

        grade = [list(l) for l in logo]
        for i in range(revelados, min(total, revelados + total // 3)):
            y, x = pontos[i]
            if grade[y][x] != " ":
                grade[y][x] = random.choice(GLIFOS_DECODE)

        linhas = [""] * topo
        for y, row in enumerate(grade):
            texto = "".join(row)
            # o que ja esta revelado ganha cor arco-iris; o resto fica fraco
            partes = []
            ultimo = None
            for x, ch in enumerate(texto):
                if ch == " ":
                    partes.append(ch)
                    continue
                revelado = (y, x) in set(pontos[:revelados])
                if revelado:
                    r, g, b = temas.arco_iris(x / float(len(texto) + 1) + t * 0.4)
                else:
                    r, g, b = (70, 60, 110)
                if (r, g, b) != ultimo:
                    partes.append(temas.rgb(r, g, b))
                    ultimo = (r, g, b)
                partes.append(ch)
            linhas.append(_centro("".join(partes) + temas.RESET, cols))

        dica = temas.pintar_arco("  iniciando o servidor  ", fase=t * 0.6,
                                 brilho=0.7)
        linhas.append("")
        linhas.append(_centro(dica, cols))
        _tela(linhas, cols, rows)
        if fracao >= 1.0:
            break
        time.sleep(0.03)


def fase_brilho(cols, rows, duracao=0.9):
    """Onda de luz passando pelo logo ja revelado."""
    logo = _ascii_compacto(cols)
    if not logo:
        return
    topo = max(0, (rows - len(logo)) // 2 - 3)
    largura = max(len(l) for l in logo)
    t0 = time.time()
    while True:
        t = time.time() - t0
        fracao = t / duracao
        varre = fracao * (largura * 1.6) - largura * 0.3
        linhas = [""] * topo
        for linha in logo:
            partes = []
            ultimo = None
            for x, ch in enumerate(linha):
                if ch == " ":
                    partes.append(ch)
                    continue
                dist = abs(x - varre)
                brilho = max(0.0, 1.0 - dist / 26.0)
                base_r, base_g, base_b = temas.arco_iris(
                    x / float(largura) + 0.15, brilho=0.72)
                r = min(255, int(base_r + brilho * 255 * 0.85))
                g = min(255, int(base_g + brilho * 255 * 0.85))
                b = min(255, int(base_b + brilho * 255 * 0.85))
                if (r, g, b) != ultimo:
                    partes.append(temas.rgb(r, g, b))
                    ultimo = (r, g, b)
                partes.append(ch)
            linhas.append(_centro("".join(partes) + temas.RESET, cols))
        linhas.append("")
        linhas.append(_centro(
            temas.rolar_arco("INFINITE", t, brilho=1.0), cols))
        _tela(linhas, cols, rows)
        if fracao >= 1.0:
            break
        time.sleep(0.025)


def fase_progresso(cols, rows, etapas, pausa=0.16, tarefa=None):
    """Barra arco-iris + etapas marcadas + metricas ao vivo.

    etapas: lista de textos. tarefa: funcao opcional chamada na thread
    principal entre quadros (para nao travar em sleep puro).
    """
    logo = _ascii_compacto(cols)
    topo = max(0, (rows - len(logo) - len(etapas) - 8) // 2)
    cells = min(46, max(24, cols - 30))
    t0 = time.time()
    indice = 0
    estado = ["." for _ in etapas]

    while indice <= len(etapas):
        t = time.time() - t0
        fracao = min(1.0, indice / float(max(1, len(etapas))))
        marca = temas.barra(fracao, cells, temas.INFINITY, t)
        pct = "%3d%%" % int(fracao * 100)

        spin = temas.spinner(int(t * 12), temas.INFINITY)
        if indice < len(etapas):
            atual = etapas[indice]
        else:
            atual = "pronto"

        linhas = [""] * topo
        largura = max((len(l) for l in logo), default=1)
        for linha in logo:
            partes = []
            ultimo = None
            for x, ch in enumerate(linha):
                if ch == " ":
                    partes.append(ch)
                    continue
                r, g, b = temas.arco_iris(x / float(largura) + t * 0.12,
                                          brilho=0.75)
                if (r, g, b) != ultimo:
                    partes.append(temas.rgb(r, g, b))
                    ultimo = (r, g, b)
                partes.append(ch)
            linhas.append(_centro("".join(partes) + temas.RESET, cols))

        linhas.append("")
        linhas.append(_centro(
            temas.rolar_arco("INFINITE", t) + temas.RESET, cols))
        linhas.append("")
        linha_barra = (temas.pintar_arco(spin, t * 0.5) + "  " + marca
                       + "  " + temas.INFINITY_PALETA["texto"] + pct
                       + temas.RESET)
        linhas.append(_centro(linha_barra, cols))
        linhas.append("")

        for i, texto in enumerate(etapas):
            if i < indice:
                sim = temas.INFINITY_PALETA["ok"] + "✓" + temas.RESET
                cor = temas.INFINITY_PALETA["fraco"]
            elif i == indice:
                sim = (temas.pintar_arco(">", t * 0.7) if True else ">")
                cor = temas.INFINITY_PALETA["texto"]
            else:
                sim = temas.INFINITY_PALETA["fraco"] + "·" + temas.RESET
                cor = temas.INFINITY_PALETA["fraco"]
            linhas.append(_centro("  " + sim + " " + cor + texto
                                  + temas.RESET + "   ", cols))

        # metricas decorativas: enchem a tela e dao sensacao de atividade
        if indice < len(etapas):
            barra_mini = temas.barra(min(1.0, (t * 0.7) % 1.0), 18,
                                     temas.INFINITY, t * 0.5)
            extra = (temas.INFINITY_PALETA["fraco"]
                     + "node " + temas.pintar_arco(str(random.randint(100, 999)),
                                                   t * 0.3)
                     + temas.INFINITY_PALETA["fraco"] + "  " + barra_mini
                     + "  " + str(random.randint(1, 32)) + " thr"
                     + temas.RESET)
            linhas.append("")
            linhas.append(_centro(extra, cols))

        _tela(linhas, cols, rows)

        if indice < len(etapas):
            prazo = time.time() + pausa
            while time.time() < prazo:
                if tarefa:
                    tarefa()
                time.sleep(0.01)
            estado[indice] = "ok"
            indice += 1
        else:
            break


def fase_dissolver(cols, rows, duracao=0.45):
    """Saida: o logo vai se desfazendo em particulas."""
    logo = _ascii_compacto(cols)
    topo = max(0, (rows - len(logo)) // 2 - 2)
    t0 = time.time()
    while True:
        t = time.time() - t0
        fracao = min(1.0, t / duracao)
        linhas = [""] * topo
        for linha in logo:
            partes = []
            for ch in linha:
                if ch == " ":
                    partes.append(ch)
                elif random.random() < fracao * 0.9:
                    r, g, b = temas.arco_iris(random.random(), brilho=0.8)
                    partes.append(temas.rgb(r, g, b)
                                  + random.choice(PARTICULAS))
                else:
                    partes.append(ch)
            linhas.append(_centro("".join(partes) + temas.RESET, cols))
        _tela(linhas, cols, rows)
        if fracao >= 1.0:
            break
        time.sleep(0.03)


def rodar(etapas=None, tarefa=None, cols=None, rows=None, rapido=False):
    """Sequencia completa do loading INFINITE."""
    if cols is None or rows is None:
        cols, rows = _tamanho()
    etapas = etapas or ["carregando tema",
                        "inspecionando navegador",
                        "preparando proxies",
                        "montando o servidor",
                        "quase la"]
    sys.stdout.write(ESC + "?25l")
    try:
        if rapido:
            fase_progresso(cols, rows, etapas, pausa=0.08, tarefa=tarefa)
        else:
            fase_decodificar(cols, rows, 1.2)
            fase_brilho(cols, rows, 0.7)
            fase_progresso(cols, rows, etapas, pausa=0.16, tarefa=tarefa)
            fase_dissolver(cols, rows, 0.35)
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h" + ESC + "2J" + HOME)
        sys.stdout.flush()


def loading_legacy(etapas=None, pausa=0.25):
    """Loading do tema Legacy: simples, vermelho, como sempre foi."""
    p = temas.LEGACY_PALETA
    etapas = etapas or ["carregando", "navegador", "proxies", "servidor", "ok"]
    sys.stdout.write(ESC + "?25l")
    try:
        for i, texto in enumerate(etapas):
            spin = temas.spinner(i, temas.LEGACY)
            barra = temas.barra((i + 1) / float(len(etapas)), 24, temas.LEGACY)
            sys.stdout.write("\r  " + p["brilho"] + spin + temas.RESET + " "
                             + barra + "  " + p["texto2"] + texto
                             + temas.RESET + " " * 12)
            sys.stdout.flush()
            time.sleep(pausa)
        sys.stdout.write("\n")
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h")
        sys.stdout.flush()
