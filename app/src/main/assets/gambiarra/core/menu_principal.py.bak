"""Tela principal do Night Router, nos dois temas.

Um painel so, com as opcoes:
    Farm Key        gera contas e testa as que ja tem
    AutoAgent       configura opencode ou deepseek harness
    Jailbreak       liga/desliga o contexto sem censura
    Config          tema, navegador, proxy, threads
    Fechar servidor encerra tudo

Navegacao: setas + enter. Tambem aceita 1..5.
"""
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import navegadores
import temas

try:
    import msvcrt
except ImportError:
    msvcrt = None

ESC = "\x1b["
RESET = temas.RESET
BOLD = temas.BOLD
LIMPA_LINHA = ESC + "K"
LIMPA_FIM = ESC + "J"
HOME = ESC + "H"

ITENS = ("farm", "agente", "jailbreak", "config", "servidor_info", "fechar")

TITULOS = {
    "farm": ("Farm Key", "gera contas novas e testa as que ja tem"),
    "agente": ("AutoAgent", "configura opencode ou deepseek harness"),
    "jailbreak": ("Jailbreak", "liga/desliga o contexto sem censura"),
    "config": ("Config", "tema, navegador, proxy, threads"),
    "servidor_info": ("ServerInfo", "base url, keys, tokens e modelos"),
    "fechar": ("Fechar servidor", "encerra tudo com seguranca"),
}

# largura fixa da coluna de titulo, para as descricoes alinharem
LARG_TITULO = 17


# ---------------------------------------------------------------- teclado

_BUFFER = []


def le_tecla(timeout=None):
    """Tecla normalizada. None se o tempo acabar."""
    if _BUFFER:
        return _BUFFER.pop(0)
    if msvcrt is None:
        return sys.stdin.read(1)
    if timeout is not None:
        limite = time.time() + timeout
        while time.time() < limite:
            if msvcrt.kbhit():
                return _traduzir()
            time.sleep(0.006)
        return None
    return _traduzir()


def le_texto(timeout=None):
    """Tecla para DIGITAR TEXTO: mantem maiuscula e espaco.

    `le_tecla` normaliza tudo para minusculo porque serve aos atalhos do
    menu (J/K/J=baixo). Isso DESTROI keys, senhas e URLs que tenham
    maiuscula. Quem le conteudo do usuario usa esta funcao.
    """
    if msvcrt is None:
        return sys.stdin.read(1)
    if timeout is not None:
        limite = time.time() + timeout
        while time.time() < limite:
            if msvcrt.kbhit():
                return _traduzir_texto()
            time.sleep(0.006)
        return None
    return _traduzir_texto()


def _traduzir_texto():
    """Como _traduzir, mas sem baixar a caixa nem trocar o espaco."""
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
    if ch in ("\x08", "\x7f"):
        return "backspace"
    if ch == "\x16":
        return "colar"
    # espaco e maiusculas seguem intactos
    return ch


def _traduzir():
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
    if ch in ("\x08", "\x7f"):
        return "backspace"
    if ch == "\x16":            # ctrl+v
        return "colar"
    if ch == " ":
        return "espaco"
    return ch.lower()


def colar_area():
    """Texto do clipboard, ou "" se nao der para ler.

    No Windows usa a API nativa com algumas tentativas: o clipboard
    fica travado por um instante quando outro programa o esta usando.
    """
    if os.name == "nt":
        for _ in range(12):
            texto = _colar_win32()
            if texto:
                return texto
            time.sleep(0.05)
        return ""
    for cmd in (["wl-paste", "-n"], ["xclip", "-selection", "clipboard", "-o"],
                ["xsel", "--clipboard", "--output"]):
        try:
            saida = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=3)
            if saida.returncode == 0 and saida.stdout:
                return saida.stdout
        except Exception:
            continue
    return ""


def _colar_win32():
    import ctypes
    from ctypes import wintypes
    CF_UNICODETEXT = 13
    u32 = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.OpenClipboard.restype = wintypes.BOOL
    u32.GetClipboardData.argtypes = [wintypes.UINT]
    u32.GetClipboardData.restype = wintypes.HANDLE
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    try:
        if not u32.OpenClipboard(None):
            return ""
    except Exception:
        return ""
    try:
        if not u32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        handle = u32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = k32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            k32.GlobalUnlock(handle)
    except Exception:
        return ""
    finally:
        try:
            u32.CloseClipboard()
        except Exception:
            pass


def drenar():
    """Esvazia o buffer para nao herdar teclas antigas."""
    if msvcrt is None:
        return
    while msvcrt.kbhit():
        try:
            _traduzir()
        except Exception:
            break
    _BUFFER.clear()


# ------------------------------------------------------------------ tela

def preparar_terminal():
    """Prepara o console: cores ANSI e janela do tamanho do buffer."""
    if os.name == "nt":
        os.system("")
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)
            modo = ctypes.c_uint32()
            k.GetConsoleMode(h, ctypes.byref(modo))
            k.SetConsoleMode(h, modo.value | 0x0004)
        except Exception:
            pass
        _maximizar()
        _pegar_foco()
        time.sleep(0.25)


def _pegar_foco():
    """Traz o console para a frente e rouba o foco do teclado.

    Quem abre o iniciar.bat esta com o Explorer em foco: sem isso, o
    usuario digita 5 ou Enter e a tecla vai para a pasta, nao para o
    app. O SetForegroundWindow sozinho e bloqueado pelo Windows quando
    outra janela esta em primeiro plano, entao usamos o truque do Alt
    (que libera a restricao) e insistimos algumas vezes.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        u = ctypes.windll.user32
        k = ctypes.windll.kernel32

        hwnd = k.GetConsoleWindow()
        if not hwnd:
            return
        # Alt "solta" a trava do primeiro plano
        u.keybd_event(0x12, 0, 0, 0)
        u.keybd_event(0x12, 0, 2, 0)
        for _ in range(6):
            u.ShowWindow(hwnd, 9)          # SW_RESTORE
            u.SetForegroundWindow(hwnd)
            u.BringWindowToTop(hwnd)
            u.SetActiveWindow(hwnd)
            if u.GetForegroundWindow() == hwnd:
                break
            time.sleep(0.08)
    except Exception:
        pass


def _maximizar():
    """Deixa a janela do console do tamanho da tela, respeitando o buffer.

    `mode con` no .bat muda o buffer mas nao necessariamente a janela
    fisica (ficava 708x480 px = ~12 linhas visiveis). Aqui ajustamos a
    JANELA (SetConsoleWindowInfo) dentro dos limites do buffer.
    """
    if os.name != "nt":
        # no Linux/macOS quem controla o tamanho e o emulador de terminal
        return
    try:
        import ctypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class RECT(ctypes.Structure):
            _fields_ = [("Left", ctypes.c_long), ("Top", ctypes.c_long),
                        ("Right", ctypes.c_long), ("Bottom", ctypes.c_long)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                        ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]

        class CSBI(ctypes.Structure):
            _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD),
                        ("wAttributes", ctypes.c_ushort),
                        ("srWindow", SMALL_RECT),
                        ("dwMaximumWindowSize", COORD)]

        k = ctypes.windll.kernel32
        u = ctypes.windll.user32
        hwnd = k.GetConsoleWindow()
        if not hwnd:
            return

        h = k.GetStdHandle(-11)
        info = CSBI()
        if not k.GetConsoleScreenBufferInfo(h, ctypes.byref(info)):
            return

        # 1) descobre o tamanho da celula da fonte em pixels. A janela
        # atual tem col_j celulas ocupando px_w pixels; a fonte nao muda,
        # entao essa razao vale para a tela inteira.
        r = RECT()
        tela_w = u.GetSystemMetrics(0)
        tela_h = u.GetSystemMetrics(1)
        col_j = info.srWindow.Right - info.srWindow.Left + 1
        lin_j = info.srWindow.Bottom - info.srWindow.Top + 1
        cel_w = cel_h = 0.0
        if u.GetClientRect(hwnd, ctypes.byref(r)):
            px_w = r.Right - r.Left
            px_h = r.Bottom - r.Top
            if px_w > 100 and px_h > 100 and col_j > 0 and lin_j > 0:
                cel_w = px_w / float(col_j)
                cel_h = px_h / float(lin_j)

        # 2) quantas celulas cabem na tela (se mediu); sem medida, pede
        # um valor generoso e deixa o console limitar
        if cel_w > 0 and cel_h > 0:
            quer_c = max(100, min(int(tela_w / cel_w) - 1, 300))
            quer_l = max(30, min(int(tela_h / cel_h) - 2, 100))
        else:
            quer_c, quer_l = 200, 60

        # 3) o buffer tem de ser >= janela; cresce antes de encolher
        novo = COORD(ctypes.c_short(min(quer_c, 320)),
                     ctypes.c_short(max(info.dwSize.Y, quer_l)))
        k.SetConsoleScreenBufferSize(h, novo)
        k.GetConsoleScreenBufferInfo(h, ctypes.byref(info))

        # 4) aplica a janela: 0,0 ate o canto, so se couber no buffer
        larg = min(quer_c, info.dwSize.X)
        alt = min(quer_l, info.dwSize.Y)
        if larg >= 40 and alt >= 10:
            janela = SMALL_RECT(0, 0, ctypes.c_short(larg - 1),
                                ctypes.c_short(alt - 1))
            k.SetConsoleWindowInfo(h, True, ctypes.byref(janela))

        u.ShowWindow(hwnd, 3)          # maximiza de fato
    except Exception:
        pass


def tamanho():
    """Tamanho (colunas, linhas) que REALMENTE aparecem na janela.

    O console reporta o buffer (ex.: 320x86) mesmo quando a janela
    fisica exhibe muito menos. Medimos a janela em pixels e dividimos
    pela celula da fonte. Se a janela expuser menos linhas do que cabe
    no buffer, e esse numero que o layout tem de usar.
    """
    try:
        cols_rep, rows_rep = os.get_terminal_size()
    except OSError:
        cols_rep, rows_rep = 118, 40

    if os.name == "nt":
        real = _medir_janela(cols_rep, rows_rep)
        if real:
            return real
    return max(50, min(cols_rep, 200)), max(10, min(rows_rep, 70))


def _medir_janela(cols_rep, rows_rep):
    """Celulas que a janela do console exibe, medindo em pixels."""
    if os.name != "nt":
        # no Linux/macOS o terminal ja informa o tamanho certo
        return (cols_rep, rows_rep)
    try:
        import ctypes

        class RECT(ctypes.Structure):
            _fields_ = [("Left", ctypes.c_long), ("Top", ctypes.c_long),
                        ("Right", ctypes.c_long), ("Bottom", ctypes.c_long)]

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                        ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]

        class CSBI(ctypes.Structure):
            _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD),
                        ("wAttributes", ctypes.c_ushort),
                        ("srWindow", SMALL_RECT),
                        ("dwMaximumWindowSize", COORD)]

        k = ctypes.windll.kernel32
        u = ctypes.windll.user32
        hwnd = k.GetConsoleWindow()
        if not hwnd:
            return None

        r = RECT()
        if not u.GetClientRect(hwnd, ctypes.byref(r)):
            return None
        px_w = r.Right - r.Left
        px_h = r.Bottom - r.Top
        if px_w < 80 or px_h < 80:
            return None

        h = k.GetStdHandle(-11)
        info = CSBI()
        if not k.GetConsoleScreenBufferInfo(h, ctypes.byref(info)):
            return None
        col_j = info.srWindow.Right - info.srWindow.Left + 1
        lin_j = info.srWindow.Bottom - info.srWindow.Top + 1
        if col_j <= 0 or lin_j <= 0:
            return None

        # tamanho da celula em pixels medido pela janela ATUAL
        cel_w = px_w / float(col_j)
        cel_h = px_h / float(lin_j)
        if cel_w < 1 or cel_h < 1:
            return None

        # quantas celulas a janela exibe de fato, segundo os pixels
        larg_px = u.GetClientRect(hwnd, ctypes.byref(r))
        px_w = r.Right - r.Left
        px_h = r.Bottom - r.Top
        if px_w < 80 or px_h < 40:
            return None
        col_real = int(px_w / cel_w)
        lin_real = int(px_h / cel_h)
        # nunca reporta mais do que o buffer tem
        col_real = max(40, min(col_real, info.dwSize.X))
        lin_real = max(8, min(lin_real, info.dwSize.Y))
        return col_real, lin_real
    except Exception:
        return None


def _janela_visivel():
    """(colunas, linhas) que realmente aparecem na tela fisica.

    O console pode reportar um buffer/janela logica enorme (ex.: 237x64)
    enquanto, com a fonte em uso, so ~100x17 cabem no monitor. Medimos o
    tamanho da janela em pixels e dividimos pelo tamanho da celula da
    fonte para saber quantas colunas/linhas de fato aparecem.
    """
    if os.name != "nt":
        # Linux/macOS: a propria API do terminal ja responde certo
        return tamanho()
    try:
        import ctypes
        from ctypes import wintypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                        ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]

        class CSBI(ctypes.Structure):
            _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD),
                        ("wAttributes", ctypes.c_ushort),
                        ("srWindow", SMALL_RECT),
                        ("dwMaximumWindowSize", COORD)]

        class RECT(ctypes.Structure):
            _fields_ = [("Left", ctypes.c_long), ("Top", ctypes.c_long),
                        ("Right", ctypes.c_long), ("Bottom", ctypes.c_long)]

        k = ctypes.windll.kernel32
        u = ctypes.windll.user32
        h = k.GetStdHandle(-11)

        info = CSBI()
        if not k.GetConsoleScreenBufferInfo(h, ctypes.byref(info)):
            return None
        col_logicas = info.srWindow.Right - info.srWindow.Left + 1
        lin_logicas = info.srWindow.Bottom - info.srWindow.Top + 1
        if col_logicas <= 0 or lin_logicas <= 0:
            return None

        hwnd = k.GetConsoleWindow()
        if not hwnd:
            return (col_logicas, lin_logicas)

        # tamanho do CLIENTE da janela em pixels (area util, sem bordas)
        rect = RECT()
        if not u.GetClientRect(hwnd, ctypes.byref(rect)):
            return (col_logicas, lin_logicas)
        px_larg = rect.Right - rect.Left
        px_alt = rect.Bottom - rect.Top
        if px_larg <= 0 or px_alt <= 0:
            return (col_logicas, lin_logicas)

        # tamanho de UMA celula da fonte em pixels
        cel_larg = px_larg / float(col_logicas)
        cel_alt = px_alt / float(lin_logicas)
        if cel_larg < 1 or cel_alt < 1:
            return (col_logicas, lin_logicas)

        # quanto cabe na tela do monitor (descontando barra de tarefas)
        tela_larg = u.GetSystemMetrics(0)
        tela_alt = u.GetSystemMetrics(1)
        cabe_col = int(tela_larg / cel_larg)
        cabe_lin = int((tela_alt - 90) / cel_alt)

        # o que realmente aparece = o menor entre logico e fisico
        return (max(40, min(col_logicas, cabe_col)),
                max(10, min(lin_logicas, cabe_lin)))
    except Exception:
        return None


def _espacos(texto, cols):
    v = temas.largura_visivel(texto)
    if v < cols:
        return texto + " " * (cols - v)
    if v > cols:
        return _cortar(texto, cols)
    return texto


def _cortar(texto, limite):
    """Corta o texto no limite VISIVEL, preservando as sequencias ANSI.

    Uma linha maior que a largura do terminal faz o console embrulhar e
    empurrar tudo, o que desmonta o layout. Aqui isso nunca acontece.
    """
    import re as _re

    LIMITE_CHARS = 12000
    padrao = _re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
    saida = []
    contados = 0
    pos = 0
    for m in padrao.finditer(texto):
        # texto visivel antes desta sequencia
        pedaco = texto[pos:m.start()]
        espaco = limite - contados
        if len(pedaco) > espaco:
            saida.append(pedaco[:espaco])
            contados = limite
            break
        saida.append(pedaco)
        contados += len(pedaco)
        saida.append(m.group(0))
        pos = m.end()
        if contados >= limite:
            break
    else:
        pedaco = texto[pos:]
        espaco = limite - contados
        if espaco > 0:
            saida.append(pedaco[:espaco])
            contados += min(len(pedaco), espaco)
    # garante que a linha nao estoure mesmo com muitos ansi
    resultado = "".join(saida)
    if len(resultado) > LIMITE_CHARS:
        resultado = resultado[:LIMITE_CHARS]
    if contados < limite:
        resultado += " " * (limite - contados)
    return resultado + RESET


def _centro(texto, cols):
    v = temas.largura_visivel(texto)
    return " " * max(0, (cols - v) // 2) + texto


def em_selecao():
    """True quando o usuario esta selecionando texto com o mouse.

    Com o QuickEdit ligado, o Windows congela o desenho enquanto se
    arrasta o mouse. Se continuarmos escrevendo, a selecao se desfaz e
    o texto copiado sai errado. Aqui percebemos o modo selecao pelo
    tamanho da selecao do console e pausamos a pintura.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class CSBI(ctypes.Structure):
            _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD),
                        ("wAttributes", ctypes.c_ushort),
                        ("srWindow", ctypes.c_short * 4),
                        ("dwMaximumWindowSize", COORD)]

        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-5)          # saida
        info = CSBI()
        if not k.GetConsoleScreenBufferInfo(h, ctypes.byref(info)):
            return False
        # consulta o modo de entrada: ENABLE_MOUSE_INPUT | selecao ativa
        modo = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(modo)):
            return False
        # bit 0x0080 = ENABLE_EXTENDED_FLAGS; a selecao em si aparece
        # como cursor diferente, entao usamos a API de titulo: durante a
        # selecao o conhost acrescenta "Select" ao titulo
        tamanho = k.GetConsoleTitleW
        buf = ctypes.create_unicode_buffer(512)
        k.GetConsoleTitleW(buf, 512)
        return "select" in buf.value.lower()
    except Exception:
        return False


def desenhar(linhas, cols, rows):
    """Desenha a tela posicionando cada linha (ESC[n;1H).

    Antes de escrever, apaga o que sobrou de telas anteriores: os
    submenus desenham menos linhas que o menu principal, e sem isso o
    menu antigo continuava aparecendo atras. A limpeza e linha a linha
    com ESC[K -- ESC[2J / ESC[J bagunçam o posicionamento no conhost.
    """
    limite = max(1, min(len(linhas), rows - 1))
    largura = max(10, cols - 3)
    # durante a selecao com o mouse nao repintamos: escrever desfaz a
    # selecao e o usuario perde o que estava marcando
    if em_selecao():
        return
    partes = []
    # 1) limpa as linhas da area antes de desenhar
    for i in range(1, min(rows, 200)):
        partes.append("\x1b[%d;1H\x1b[K" % i)
    # 2) desenha o conteudo novo
    for i in range(limite):
        partes.append("\x1b[%d;1H" % (i + 1))
        partes.append(_espacos(linhas[i], largura))
    partes.append("\x1b[%d;1H" % limite)
    partes.append(RESET)
    texto = "".join(partes)
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        buf.write(texto.encode("utf-8", "replace"))
        buf.flush()
    else:
        sys.stdout.write(texto)
        sys.stdout.flush()


# --------------------------------------------------------------- molduras

def moldura_legacy(linhas, largura):
    p = temas.LEGACY_PALETA
    topo = p["escura"] + "╭" + "─" * (largura - 2) + "╮" + RESET
    base = p["escura"] + "╰" + "─" * (largura - 2) + "╯" + RESET
    corpo = []
    for l in linhas:
        v = temas.largura_visivel(l)
        corpo.append(p["escura"] + "│" + RESET + l
                     + " " * max(0, largura - 2 - v)
                     + p["escura"] + "│" + RESET)
    return [topo] + corpo + [base]


def moldura_infinity(linhas, largura, t):
    borda = temas.rgb(140, 120, 255)
    # blocos de 8: degradê igual, mas com ~14 sequencias em vez de ~112.
    # O conhost do Windows para de desenhar a tela quando uma linha tem
    # centenas de escapes de cor.
    n = max(1, largura - 2)
    partes = []
    ultimo = None
    BLOCO = 8
    i = 0
    while i < n:
        qtd = min(BLOCO, n - i)
        r, g, b = temas.arco_iris(i / float(n) + t * 0.15, brilho=0.6)
        if (r, g, b) != ultimo:
            partes.append(temas.rgb(r, g, b))
            ultimo = (r, g, b)
        partes.append("─" * qtd)
        i += qtd
    meio = "".join(partes)
    topo = borda + "╭" + meio + borda + "╮" + RESET
    base = borda + "╰" + meio + borda + "╯" + RESET
    corpo = []
    for l in linhas:
        v = temas.largura_visivel(l)
        corpo.append(borda + "│" + RESET + l
                     + " " * max(0, largura - 2 - v)
                     + borda + "│" + RESET)
    return [topo] + corpo + [base]


def divisor(largura, tema, t=0.0):
    if tema == temas.INFINITY:
        # blocos de 8 colunas: degradê suave com poucas sequencias ANSI
        n = max(1, largura - 2)
        partes = []
        ultimo = None
        BLOCO = 8
        i = 0
        while i < n:
            qtd = min(BLOCO, n - i)
            r, g, b = temas.arco_iris(i / float(n) + t * 0.1, brilho=0.45)
            if (r, g, b) != ultimo:
                partes.append(temas.rgb(r, g, b))
                ultimo = (r, g, b)
            partes.append("─" * qtd)
            i += qtd
        return "".join(partes) + RESET
    p = temas.LEGACY_PALETA
    return p["escura"] + "─" * (largura - 2) + RESET


# ------------------------------------------------------------------ menu

def cartao(itens, escolhido, tema, t=0.0):
    """Lista de opcoes com destaque."""
    p = temas.paleta(tema)
    linhas = []
    for i, chave in enumerate(itens):
        titulo, dica = TITULOS[chave]
        sel = (i == escolhido)
        if tema == temas.INFINITY:
            if sel:
                # marcador ASCII: o "▸" colorido virava "?" no conhost
                marca = p["destaque"] + BOLD + "> " + RESET
                # define a cor do texto ANTES do fundo: sem isso o titulo
                # herdava a cor anterior e ficava invisivel sobre o fundo
                fundo = temas.rgb(255, 255, 255, fundo=True)
                nome = (fundo + BOLD + temas.rgb(40, 20, 100)
                        + " " + titulo.ljust(LARG_TITULO) + RESET
                        + " " + p["texto"] + dica + RESET)
            else:
                marca = "  "
                nome = (BOLD + " " + p["texto2"] + titulo.ljust(LARG_TITULO)
                        + RESET + " " + p["fraco"] + dica + RESET)
        else:
            if sel:
                marca = p["destaque"] + "> " + RESET
                nome = (p["fundo_destaque"] + BOLD + temas.rgb(20, 0, 0)
                        + " " + titulo.ljust(LARG_TITULO) + RESET
                        + " " + p["texto"] + dica + RESET)
            else:
                marca = "  "
                nome = (BOLD + " " + p["texto2"] + titulo.ljust(LARG_TITULO)
                        + RESET + " " + p["fraco"] + dica + RESET)
        linhas.append("  " + marca + nome)
    return linhas


def status_bar(conf, tema, t=0.0, servidor=None, jailbreak=False, largura=118):
    p = temas.paleta(tema)
    vivo = servidor is not None
    # glifos que o CMD desenha sem virar caixa
    on = p["ok"] + "█ " + RESET
    off = p["fraco"] + "░ " + RESET
    estado = (on + p["ok"] + "ON" + RESET) if vivo else (off + p["fraco"] + "OFF" + RESET)
    nucl = (p["ok"] + "█ ON" + RESET) if jailbreak else (p["fraco"] + "░ OFF" + RESET)

    esq = (p["fraco"] + "servidor " + RESET + estado
           + p["fraco"] + "   jailbreak " + RESET + nucl)
    meio = p["fraco"] + "tema " + RESET + p["texto2"] + temas.NOMES.get(
        conf.get("tema"), "-") + RESET
    # o que sobra da linha depois do "servidor/jailbreak/tema" e do
    # navegador. Antes era fixo em 22 e cortava "Automatico (proxies
    # free coletados)" mesmo com a janela larga.
    desc = navegadores.descrever(conf)
    usados = (temas.largura_visivel("servidor █ ON   jailbreak █ ON")
              + temas.largura_visivel("tema INFINITE"))
    sobra = largura - usados - 14
    limite = max(12, min(48, sobra))
    if temas.largura_visivel(desc) > limite:
        desc = desc[:limite - 1] + "…"
    dir_ = p["fraco"] + desc + RESET
    return esq, meio, dir_


# --------------------------------------------------------------- animacao

def arte_topo(tema, largura, t, quadro=0):
    """ASCII do topo, ja pintado conforme o tema."""
    if tema == temas.INFINITY:
        linhas = temas.limpar_ascii(temas.ascii_do_tema(temas.INFINITY),
                                    largura - 6)
        return [_centro(l, largura - 2)
                for l in temas.pintar_ascii_infinity(linhas, t)]
    linhas = temas.ascii_do_tema(temas.LEGACY)
    linhas = linhas[:10]
    if linhas:
        maior = max(len(l) for l in linhas)
        if maior > largura - 6:
            fator = (largura - 6) / float(maior)
            linhas = [l[:int(maior * fator)] for l in linhas]
    return [_centro(l, largura - 2) for l in temas.pintar_ascii_legacy(linhas)]


def rodape(tema, largura, t=0.0):
    p = temas.paleta(tema)
    dica = "setas mover   enter escolher   1-6 atalho   esc sair"
    if tema == temas.INFINITY:
        # cor solida (o arco-iris por caractere gerava centenas de escapes
        # e o conhost parava de desenhar a tela)
        r, g, b = temas.arco_iris(t * 0.2, brilho=0.75)
        esq = temas.rgb(r, g, b) + dica + RESET
        r2, g2, b2 = temas.arco_iris(t * 0.2 + 0.5, brilho=0.9)
        disc = temas.rgb(r2, g2, b2) + temas.DISCORD + RESET
    else:
        esq = p["fraco"] + dica + RESET
        disc = p["suave"] + temas.DISCORD + RESET
    vazio = largura - 4 - temas.largura_visivel(dica) - temas.largura_visivel(temas.DISCORD)
    if vazio < 1:
        return " " + esq
    return " " + esq + " " * vazio + disc


class App:

    def __init__(self, conf, servidor=None):
        self.conf = dict(conf)
        self.tema = conf.get("tema") or temas.LEGACY
        self.servidor = servidor
        self.escolhido = 0
        self.rodando = True
        self.jailbreak = bool(conf.get("jailbreak"))
        self.mensagem = ""
        self.mensagem_ate = 0.0
        self.status_extra = ""
        self.t0 = time.time()

    def aviso(self, texto, segundos=4):
        self.mensagem = texto
        self.mensagem_ate = time.time() + segundos

    def render(self, cols, rows):
        t = time.time() - self.t0
        # usa a largura real da janela (com 2 colunas de folga para nunca
        # encostar na borda). Antes travava em 118 e o app ficava no canto
        # esquerdo em telas grandes.
        largura = max(50, cols - 2)
        p = temas.paleta(self.tema)

        # ---- arte do topo ----
        arte = arte_topo(self.tema, largura, t)

        # O menu e o que importa: calcula quantas linhas a arte pode usar
        # sem empurrar as opcoes para fora da tela.
        # titulo(1) + divisor(1) + status(2) + divisor(1) + opcoes(5)
        # + msg(1) + divisor(1) + rodape(1) + vazio(1) + 2 bordas = 15
        FIXO = 15
        # usa a altura real da janela: travar em 45 deixava uma faixa
        # preta grande embaixo em monitores altos
        altura = max(20, rows)
        disponivel = max(1, altura - 1 - FIXO)
        if len(arte) > disponivel:
            while len(arte) > disponivel and len(arte) > 3:
                arte = [arte[i] for i in range(0, len(arte), 2)]
        if len(arte) > disponivel:
            arte = arte[:disponivel]

        corpo = []
        corpo.extend(arte)
        corpo.append("")

        # so o nome do tema, sem texto extra
        nome = "INFINITE" if self.tema == temas.INFINITY else "LEGACY"
        if self.tema == temas.INFINITY:
            titulo = temas.rolar_arco(nome, t, brilho=1.0)
        else:
            titulo = p["brilho"] + BOLD + nome + RESET
        corpo.append(_centro(titulo, largura - 2))
        corpo.append(divisor(largura, self.tema, t))

        esq, meio, dir_ = status_bar(self.conf, self.tema, t, self.servidor,
                                     self.jailbreak, largura)
        corpo.append("  " + esq + "   " + meio)
        corpo.append("  " + p["fraco"] + dir_ + RESET)
        corpo.append(divisor(largura, self.tema, t))

        corpo.extend(cartao(ITENS, self.escolhido, self.tema, t))

        if self.mensagem and time.time() < self.mensagem_ate:
            if self.tema == temas.INFINITY:
                txt = temas.pintar_arco("  " + self.mensagem, t * 0.4, brilho=0.9)
            else:
                txt = "  " + p["alerta"] + self.mensagem + RESET
            corpo.append(txt)
        else:
            corpo.append("")

        corpo.append(divisor(largura, self.tema, t))
        corpo.append(rodape(self.tema, largura, t))

        if self.tema == temas.INFINITY:
            caixa = moldura_infinity(corpo, largura, t)
        else:
            caixa = moldura_legacy(corpo, largura)

        # centraliza verticalmente quando ha sobra de verdade
        sobra_tela = rows - 1 - len(caixa)
        saida = [""] * max(0, sobra_tela // 2)
        for l in caixa:
            saida.append(_centro(l, cols))
        return saida

    def desenhar(self, cols, rows):
        desenhar(self.render(cols, rows), cols, rows)

    def run(self):
        preparar_terminal()
        drenar()
        sys.stdout.write(ESC + "?25l")
        # diagnostico: registra o que o app realmente enxerga
        try:
            import tempfile
            c, r = tamanho()
            vis = _janela_visivel()
            with open(os.path.join(tempfile.gettempdir(), "nr_diag.txt"), "w") as f:
                f.write("cols=%s rows=%s visivel=%s os_size=%s\n"
                        % (c, r, vis, os.get_terminal_size()))
        except Exception:
            pass
        try:
            while self.rodando:
                cols, rows = tamanho()
                self.desenhar(cols, rows)
                tecla = le_tecla(0.12)
                if tecla is None:
                    continue
                if tecla in ("cima", "k"):
                    self.escolhido = (self.escolhido - 1) % len(ITENS)
                elif tecla in ("baixo", "j"):
                    self.escolhido = (self.escolhido + 1) % len(ITENS)
                elif tecla in ("1", "2", "3", "4", "5", "6"):
                    self.escolhido = min(int(tecla) - 1, len(ITENS) - 1)
                    tecla = "enter"
                elif tecla == "esc":
                    self.escolhido = len(ITENS) - 1
                    tecla = "enter"
                if tecla == "enter":
                    acao = ITENS[self.escolhido]
                    if not self.agir(acao, cols, rows):
                        break
        finally:
            sys.stdout.write(RESET + ESC + "?25h" + ESC + "2J" + HOME)
            sys.stdout.flush()

    def agir(self, acao, cols, rows):
        """Executa a opcao. Devolve False para encerrar."""
        if acao == "fechar":
            self.aviso("fechando...")
            self.desenhar(cols, rows)
            time.sleep(0.4)
            return False
        if acao == "farm":
            self.status_extra = "farm"
            try:
                import tela_farm
                tela_farm.abrir(self, cols, rows)
            except Exception as exc:
                self.aviso("farm: %s" % str(exc)[:60], 6)
            self.conf = temas.carregar()
            self.jailbreak = bool(self.conf.get("jailbreak"))
            return True
        if acao == "agente":
            try:
                import tela_agente
                tela_agente.abrir(self, cols, rows)
            except Exception as exc:
                self.aviso("agente: %s" % str(exc)[:60], 6)
            return True
        if acao == "jailbreak":
            self.jailbreak = not self.jailbreak
            temas.definir("jailbreak", self.jailbreak)
            self.conf["jailbreak"] = self.jailbreak
            self.aviso("jailbreak %s" % ("ON" if self.jailbreak else "OFF"))
            try:
                import estado_servidor
                estado_servidor.definir_jailbreak(self.jailbreak)
            except Exception:
                pass
            return True
        if acao == "servidor_info":
            try:
                import tela_serverinfo
                tela_serverinfo.abrir(self, cols, rows)
            except Exception as exc:
                self.aviso("serverinfo: %s" % str(exc)[:60], 6)
            return True
        if acao == "config":
            try:
                import tela_config
                novo = tela_config.abrir(self.conf, cols, rows)
                if novo:
                    self.conf = novo
                    if novo.get("tema"):
                        self.tema = novo["tema"]
                    if novo.get("_reiniciar"):
                        # o provider mudou: a url do upstream e escolhida
                        # ao subir o servidor, entao reabre o programa
                        self.reiniciar()
                        return False
            except Exception as exc:
                self.aviso("config: %s" % str(exc)[:60], 6)
            return True
        return True

    def reiniciar(self):
        """Fecha o app e abre de novo, mantendo a janela atual."""
        try:
            sys.stdout.write(RESET + ESC + "?25h" + ESC + "2J" + HOME)
            sys.stdout.flush()
        except Exception:
            pass
        self.rodando = False
        try:
            import subprocess
            raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if os.name == "nt":
                bat = os.path.join(raiz, "iniciar.bat")
                if os.path.exists(bat):
                    subprocess.Popen(["cmd", "/c", "start", "",
                                      "cmd", "/c", bat],
                                     close_fds=True)
                    return
            py = sys.executable
            ini = os.path.join(raiz, "iniciar.py")
            if os.path.exists(ini):
                subprocess.Popen([py, "-u", "-X", "utf8", ini], cwd=raiz,
                                 close_fds=True)
        except Exception:
            pass


def abrir(conf=None, servidor=None):
    if conf is None:
        conf = temas.carregar()
    App(conf, servidor).run()
