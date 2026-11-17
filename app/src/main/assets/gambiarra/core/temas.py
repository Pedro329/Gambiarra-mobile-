"""Sistema de temas do Night Router.

Dois temas, mesma funcionalidade, nada muda no farm:

  Legacy      - a cara de sempre: vermelho, ASCII do banner.txt, loading simples
  INFINITE    - ASCII "INFINITE", arco-iris animado, loading elaborado

O tema fica salvo em dados/config.json. Na primeira vez o programa pergunta.
"""
import json
import os
import random
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(HERE)
DATA_DIR = os.path.join(BASE_DIR, "dados")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
DISCORD = "https://discord.gg/gambiarra"

LEGACY = "legacy"
INFINITY = "infinity"
TEMAS = (LEGACY, INFINITY)

NOMES = {
    LEGACY: "LEGACY",
    INFINITY: "INFINITE",
}

# ------------------------------------------------------------------ cores

ESC = "\x1b["
RESET = ESC + "0m"
BOLD = ESC + "1m"
DIM_TXT = ESC + "2m"


def rgb(r, g, b, fundo=False):
    return "%s%s;2;%d;%d;%dm" % (ESC, "48" if fundo else "38", r, g, b)


def cor256(n, fundo=False):
    return "%s%s;5;%dm" % (ESC, "48" if fundo else "38", n)


# paleta do Legacy: vermelho, igual o farmer de sempre
LEGACY_PALETA = {
    "primaria": cor256(160),
    "brilho": cor256(203),
    "escura": cor256(88),
    "suave": cor256(131),
    "texto": cor256(255),
    "texto2": cor256(250),
    "fraco": cor256(242),
    "linha": cor256(88),
    "ok": cor256(114),
    "erro": cor256(203),
    "alerta": cor256(221),
    "destaque": ESC + "1m" + cor256(203),
    "fundo_destaque": cor256(160, fundo=True) + cor256(231),
}

# paleta do Infinity: roxo/ciano, animada
INFINITY_PALETA = {
    "primaria": rgb(120, 90, 255),
    "brilho": rgb(180, 160, 255),
    "escura": rgb(70, 50, 160),
    "suave": rgb(100, 80, 200),
    "texto": rgb(240, 240, 255),
    "texto2": rgb(200, 200, 230),
    "fraco": rgb(130, 130, 160),
    "linha": rgb(80, 70, 150),
    "ok": rgb(120, 255, 180),
    "erro": rgb(255, 110, 110),
    "alerta": rgb(255, 210, 120),
    "destaque": ESC + "1m" + rgb(200, 180, 255),
    "fundo_destaque": rgb(90, 70, 200, fundo=True) + rgb(255, 255, 255),
}


def paleta(tema):
    return INFINITY_PALETA if tema == INFINITY else LEGACY_PALETA


# --------------------------------------------------------------- arco-iris

def arco_iris(pos, ciclo=1.0, brilho=1.0):
    """Devolve (r,g,b) numa roda de cores suave. pos vai de 0 a 1."""
    h = (pos * ciclo) % 1.0
    i = int(h * 6)
    f = h * 6 - i
    q = 1 - f
    tabela = (
        (1, f, 0), (q, 1, 0), (0, 1, f),
        (0, q, 1), (f, 0, 1), (1, 0, q),
    )
    r, g, b = tabela[i % 6]
    r = int(255 * min(1.0, r * brilho))
    g = int(255 * min(1.0, g * brilho))
    b = int(255 * min(1.0, b * brilho))
    return r, g, b


def pintar_arco(texto, fase=0.0, brilho=1.0, espalhar=1.0, fundo=False):
    """Texto com cada caractere numa cor do arco-iris.

    fase    desloca a roda (anima ao longo do tempo)
    espalhar  quantas voltas de cor ao longo do texto
    """
    if not texto:
        return ""
    n = max(1, len(texto))
    saida = []
    ultimo = None
    for i, ch in enumerate(texto):
        r, g, b = arco_iris(i / float(n) * espalhar + fase, brilho=brilho)
        cor = (r, g, b)
        if cor != ultimo:
            saida.append(rgb(r, g, b, fundo))
            ultimo = cor
        saida.append(ch)
    saida.append(RESET)
    return "".join(saida)


def rolar_arco(texto, t, brilho=1.0, voltas=None):
    """Arco-iris que se move com o tempo (para titulos animados).

    `voltas` controla quantas vezes a roda de cor se repete ao longo do
    texto. Textos curtos precisam de mais voltas para ficar colorido de
    verdade (senao o titulo inteiro sai quase de uma cor so).
    """
    if voltas is None:
        # ~1 volta a cada 7 caracteres, no minimo 1
        voltas = max(1.0, len(texto) / 7.0)
    return pintar_arco(texto, fase=(t * 0.25) % 1.0, brilho=brilho,
                       espalhar=voltas)


# ------------------------------------------------------------------ ascii

ASCII_INFINITY = "ascii_infinity.txt"
BANNER_LEGACY = "banner.txt"


def ler_ascii(nome):
    caminho = os.path.join(HERE, nome)
    try:
        with open(caminho, encoding="utf-8", errors="replace") as f:
            linhas = [l.rstrip("\n").rstrip("\r").rstrip() for l in f]
    except OSError:
        return []
    while linhas and not linhas[0].strip():
        linhas.pop(0)
    while linhas and not linhas[-1].strip():
        linhas.pop()
    return linhas


def ascii_do_tema(tema):
    if tema == INFINITY:
        return ler_ascii(ASCII_INFINITY)
    return ler_ascii(BANNER_LEGACY)


def limpar_ascii(linhas, largura_max):
    """Deixa o ASCII caber na largura sem deformar as letras.

    O ascii do Infinity ja vem desenhado com espacamento duplo entre as
    colunas; fatiar colunas destroi o desenho. Entao aqui SO removemos o
    espacamento duplo (fica na metade da largura e continua legivel) e,
    se ainda nao couber, devolvemos vazio -- quem chamou decide mostrar
    uma versao compacta.
    """
    if not linhas:
        return []
    linhas = [l.rstrip() for l in linhas if l.strip()]
    maior = max((len(l) for l in linhas), default=0)
    if maior <= largura_max:
        return linhas
    # tira a coluna vazia de cada par: 116 -> 58
    compacto = []
    for l in linhas:
        compacto.append("".join(l[i] for i in range(0, len(l), 2)))
    maior = max((len(l) for l in compacto), default=0)
    if maior <= largura_max:
        return [l for l in compacto if l.strip()]
    return linhas


def pintar_ascii_legacy(linhas):
    """Degrade vermelho de cima para baixo, como no farmer original."""
    if not linhas:
        return []
    total = max(1, len(linhas) - 1)
    topo = (255, 72, 52)
    base = (110, 14, 10)
    saida = []
    for i, linha in enumerate(linhas):
        t = i / float(total) if total else 0.0
        r = int(round(topo[0] + (base[0] - topo[0]) * t))
        g = int(round(topo[1] + (base[1] - topo[1]) * t))
        b = int(round(topo[2] + (base[2] - topo[2]) * t))
        saida.append(rgb(r, g, b) + linha + RESET)
    return saida


def pintar_ascii_infinity(linhas, t=0.0, brilho=1.0):
    """Arco-iris diagonal que ondula com o tempo.

    Pinta em blocos de 4 colunas: o desenho ASCII ja tem blocos largos
    (█ ▓ ▒ ░), entao o degradê fica identico e gera 1/4 das sequencias
    ANSI -- o console do Windows engasga com centenas delas por linha.
    """
    if not linhas:
        return []
    saida = []
    largura = max((len(l) for l in linhas), default=1)
    BLOCO = 4
    for linha in linhas:
        partes = []
        ultimo = None
        i = 0
        n = len(linha)
        while i < n:
            pedaco = linha[i:i + BLOCO]
            if not pedaco.strip():
                partes.append(pedaco)
                i += BLOCO
                continue
            onda = (i / float(largura)) * 1.2 + (t * 0.18)
            r, g, b = arco_iris(onda, brilho=brilho)
            cor = (r, g, b)
            if cor != ultimo:
                partes.append(rgb(r, g, b))
                ultimo = cor
            partes.append(pedaco)
            i += BLOCO
        partes.append(RESET)
        saida.append("".join(partes))
    return saida


def ascii_pintado(tema, t=0.0, largura=None):
    linhas = ascii_do_tema(tema)
    if largura:
        linhas = limpar_ascii(linhas, max(20, largura - 4))
    if tema == INFINITY:
        return pintar_ascii_infinity(linhas, t)
    return pintar_ascii_legacy(linhas)


# ----------------------------------------------------------------- config

PADRAO = {
    "tema": None,              # None = ainda nao escolheu
    "navegador": None,         # caminho do executavel
    "proxy_modo": "auto",      # auto | random | rotativa | nenhum
    "proxy_url": "",           # para rotativa/premium
    "threads": 12,
    "jailbreak": False,
    "primeira_vez": True,
    "provider": "nightrouter",
    "mail_gmailnator_key": "",   # chave do RapidAPI
    "mail_ligados": ["gmailnator"],  # provedores ligados
    "mail_farm": "gmailnator",   # qual provedor o farm usa
}


def carregar():
    dados = dict(PADRAO)
    try:
        # utf-8-sig: tolera BOM (arquivo salvo por PowerShell/Notepad)
        with open(CONFIG_FILE, encoding="utf-8-sig") as f:
            salvo = json.load(f)
        if isinstance(salvo, dict):
            dados.update({k: v for k, v in salvo.items() if k in PADRAO})
    except (OSError, ValueError):
        pass
    return dados


def salvar(conf):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(conf, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_FILE)
    except OSError:
        pass


def definir(chave, valor):
    conf = carregar()
    conf[chave] = valor
    salvar(conf)
    return conf


def tema_salvo():
    conf = carregar()
    tema = conf.get("tema")
    return tema if tema in TEMAS else None


def precisa_escolher():
    return tema_salvo() is None


# ------------------------------------------------------ utilidades de UI

def largura_visivel(texto):
    import re
    return len(re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", texto))


def centralizar(texto, largura):
    vazio = max(0, (largura - largura_visivel(texto)) // 2)
    return " " * vazio + texto


def barra(fracao, celulas, tema=LEGACY, t=0.0):
    """Barra de progresso. Cheia no Infinity vira arco-iris."""
    celulas = max(4, celulas)
    fracao = max(0.0, min(1.0, fracao))
    cheio = int(round(fracao * celulas))
    if tema == INFINITY:
        partes = ["["]
        for i in range(celulas):
            if i < cheio:
                r, g, b = arco_iris(i / float(celulas) + t * 0.3)
                partes.append(rgb(r, g, b) + "█")
            else:
                partes.append(rgb(60, 55, 90) + "░")
        partes.append(RESET + "]")
        return "".join(partes)
    cor = LEGACY_PALETA["brilho"] if cheio else LEGACY_PALETA["fraco"]
    return (cor + "█" * cheio + LEGACY_PALETA["escura"] + "░" * (celulas - cheio)
            + RESET)


SPIN_LEGACY = "|/-\\"
SPIN_INFINITY = "◐◓◑◒"


def spinner(i, tema=LEGACY):
    if tema == INFINITY:
        return SPIN_INFINITY[i % len(SPIN_INFINITY)]
    return SPIN_LEGACY[i % len(SPIN_LEGACY)]


def embaralhar(texto):
    """Efeito de 'decodificando': devolve texto com letras trocadas."""
    alfabeto = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#$%&@"
    return "".join(random.choice(alfabeto) if ch.isalnum() else ch
                   for ch in texto)
