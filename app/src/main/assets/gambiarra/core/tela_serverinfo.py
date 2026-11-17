"""ServerInfo - tudo sobre o servidor local numa tela so.

Mostra o que o cliente precisa colar no opencode / deepseek harness /
qualquer app compativel com OpenAI:

  * base url completa (com a porta realmente escolhida)
  * a api key local (gambiarraapi) que ele deve usar
  * quantas keys estao carregadas, vivas e em cooldown
  * quais modelos estao expostos e qual rota cada um segue
  * uptime, total de requisicoes e tokens contabilizados

Nao sobe nem derruba nada: so le o estado que o servidor ja mantem.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import temas

BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RESET = "\x1b[0m"

KEY_FILE = os.path.join(HERE, "..", "gambiarra_key.txt")


# ------------------------------------------------------------------ dados
def _porta():
    try:
        import grserver
        return grserver.PORT
    except Exception:
        return int(os.environ.get("GR_PORT", "8080"))


def _base_url():
    return "http://127.0.0.1:%d/v1" % _porta()


def api_key_local():
    """A key que o cliente deve mandar. Le do arquivo, nunca inventa."""
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    except OSError:
        pass
    try:
        import grserver
        if getattr(grserver.State, "local_key", None):
            return grserver.State.local_key
    except Exception:
        pass
    return "gambiarraapi"


def _contagem_keys():
    """(total, utilizaveis, mortas, em cooldown) do pool do servidor."""
    try:
        import grpool
        return grpool.POOL.resumo()
    except Exception:
        return 0, 0, 0, 0


def _detalhe_keys():
    """Linhas por key: indice, estado e cooldown restante."""
    try:
        import grpool
        rows, _ = grpool.POOL.describe(limit=12)
        return rows
    except Exception:
        return []


def _modelos():
    """Modelos expostos publicamente, na ordem do free_models.json."""
    caminho = os.path.join(HERE, "..", "free_models.json")
    try:
        with open(caminho, encoding="utf-8") as f:
            nomes = json.load(f)
    except (OSError, ValueError):
        return []
    return [n for n in nomes if isinstance(n, str)]


def _rotas():
    """Quantos vizinhos cada modelo exposto tem na cadeia de fallback."""
    try:
        import grpool
        saida = {}
        for nome in _modelos():
            base = nome.replace("-free", "")
            saida[nome] = len(grpool.ROUTER.chain("gambiarraapi/" + base))
        return saida
    except Exception:
        return {}


def _uso():
    """(requisicoes, tokens_entrada, tokens_saida, uptime)."""
    try:
        import grserver
        st = grserver.State
        return (int(getattr(st, "requests", 0) or 0),
                int(getattr(st, "tokens_in", 0) or 0),
                int(getattr(st, "tokens_out", 0) or 0),
                int(time.time() - st.started))
    except Exception:
        return 0, 0, 0, 0


def _servidor_no_ar():
    try:
        import grserver
        return bool(grserver.State.routing)
    except Exception:
        return False


def _navegador(conf):
    try:
        import navegadores
        return navegadores.descrever(conf)
    except Exception:
        return str(conf.get("proxy_modo", "-"))


# ------------------------------------------------------------------- tela
def _so_texto(s):
    """Largura visivel, ignorando sequencias ANSI."""
    import re
    return len(re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", s))


def _cortar(s, largura):
    """Corta preservando as cores (fecha com RESET no fim)."""
    import re
    if _so_texto(s) <= largura:
        return s
    saida, visiveis, i = [], 0, 0
    while i < len(s) and visiveis < largura:
        m = re.match(r"\x1b\[[0-9;?]*[A-Za-z]", s[i:])
        if m:
            saida.append(m.group(0))
            i += len(m.group(0))
            continue
        saida.append(s[i])
        i += 1
        visiveis += 1
    return "".join(saida) + RESET


def _linha(rotulo, valor, tema, largura):
    p = temas.paleta(tema)
    rot = "  " + p["fraco"] + ("%-14s" % rotulo) + RESET
    return _cortar(rot + p["texto2"] + str(valor) + RESET, largura)


def _bloco(titulo, tema, largura, t=0.0):
    p = temas.paleta(tema)
    if tema == temas.INFINITY:
        nome = temas.rolar_arco(titulo, t, brilho=0.9)
    else:
        nome = p["brilho"] + BOLD + titulo + RESET
    resto = max(0, largura - 4 - len(titulo))
    if tema == temas.INFINITY:
        risco = temas.rolar_arco("─" * resto, t, brilho=0.55)
    else:
        risco = p["linha"] + "─" * resto + RESET
    return "  " + nome + " " + risco


def _enxuto(conf, tema, largura, t, row_limite=None):
    """Versao compacta: cabe em qualquer janela e mantem o essencial.

    2 linhas de conexao (url + key), 1 de uso, 2 de chaves e 3 de modelos
    em duas colunas. Se row_limite for pequeno, vai cortando o menos
    importante de baixo para cima (ambiente primeiro).
    """
    p = temas.paleta(tema)
    req, tin, tout, up = _uso()
    total, uteis, mortas, frias = _contagem_keys()
    modelos = _modelos()
    rotas = _rotas()
    no_ar = _servidor_no_ar()

    corpo = []

    # ---- conexao ----
    est = (p["ok"] + "█ online" + RESET) if no_ar \
        else (p["alerta"] + "░ parado" + RESET)
    corpo.append(_bloco("conexao", tema, largura, t))
    corpo.append(_cortar(
        "  " + p["fraco"] + "servidor " + RESET + est
        + p["fraco"] + "    uptime " + RESET + p["texto"] + _tempo(up) + RESET
        + p["fraco"] + "    provider " + RESET + p["texto2"] + "gambiarraapi"
        + RESET, largura))
    corpo.append(_cortar(
        "  " + p["fraco"] + "base url " + RESET + p["brilho"] + BOLD
        + _base_url() + RESET, largura))
    corpo.append(_cortar(
        "  " + p["fraco"] + "api key  " + RESET + p["brilho"] + BOLD
        + api_key_local() + RESET, largura))

    # ---- uso ----
    total_tok = tin + tout
    corpo.append(_bloco("uso", tema, largura, t))
    corpo.append(_cortar(
        "  " + p["fraco"] + "requisicoes " + RESET + p["texto"] + str(req) + RESET
        + p["fraco"] + "    tokens " + RESET
        + p["texto"] + "%d in / %d out / %d" % (tin, tout, total_tok) + RESET
        + p["fraco"] + "    media " + RESET
        + p["texto"] + str((total_tok // req) if req else 0) + RESET,
        largura))

    # ---- chaves ----
    corpo.append(_bloco("chaves", tema, largura, t))
    if not total:
        corpo.append(_cortar("  " + p["alerta"] + "nenhuma key: rode o Farm Key"
                             + RESET, largura))
    else:
        corpo.append(_cortar(
            "  " + p["fraco"] + "carregadas " + RESET + p["texto"] + str(total)
            + RESET + p["fraco"] + "    utilizaveis " + RESET + p["ok"]
            + str(uteis) + RESET
            + p["fraco"] + "    cooldown " + RESET
            + (p["alerta"] + str(frias) + RESET if frias
               else p["fraco"] + "0" + RESET),
            largura))

    # ---- modelos em duas colunas ----
    if modelos:
        corpo.append(_bloco("modelos (%d)" % len(modelos), tema, largura, t))
        if largura >= 70 and len(modelos) > 3:
            metade = (len(modelos) + 1) // 2
            col = (largura - 4) // 2
            for i in range(metade):
                a = modelos[i]
                b_ = modelos[i + metade] if i + metade < len(modelos) else ""
                txt = "  " + p["texto2"] + a + RESET
                vis = temas.largura_visivel(a) + 2
                if b_:
                    txt += " " * max(2, col - vis) + p["texto2"] + b_ + RESET
                corpo.append(_cortar(txt, largura))
        else:
            for nome in modelos:
                corpo.append(_cortar("  " + p["texto2"] + nome + RESET,
                                     largura))

    # ---- ambiente (1 linha) ----
    corpo.append(_cortar(
        "  " + p["fraco"] + "navegador " + RESET + p["texto"]
        + str(_navegador(conf)) + RESET
        + p["fraco"] + "    threads " + RESET + p["texto"]
        + str(conf.get("threads", "-")) + RESET,
        largura))

    return corpo


def conteudo(conf, tema, largura, t=0.0):
    """Linhas da tela, ja pintadas conforme o tema."""
    p = temas.paleta(tema)
    no_ar = _servidor_no_ar()
    req, tin, tout, up = _uso()
    modelos = _modelos()
    rotas = _rotas()

    saida = []
    saida.append(_bloco("conexao", tema, largura, t))

    if no_ar:
        estado = p["ok"] + "█ online" + RESET
    else:
        estado = p["alerta"] + "░ parado" + RESET
    saida.append(_linha("servidor", estado, tema, largura))
    saida.append(_linha("base url", _base_url(), tema, largura))
    saida.append(_linha("api key", api_key_local(), tema, largura))
    saida.append(_linha("provider", "gambiarraapi", tema, largura))
    saida.append(_linha("uptime", _tempo(up), tema, largura))
    saida.append("")

    saida.append(_bloco("uso", tema, largura, t))
    total_tok = tin + tout
    media = (total_tok // req) if req else 0
    # tudo numa linha: a tela precisa de espaco para os modelos
    linha_uso = ("  " + p["fraco"] + "requisicoes " + RESET
                 + p["texto"] + str(req) + RESET
                 + p["fraco"] + "    tokens " + RESET
                 + p["texto"] + "%d in / %d out / %d total" % (tin, tout, total_tok)
                 + RESET
                 + p["fraco"] + "    media/chamada " + RESET
                 + p["texto"] + ("%d" % media) + RESET)
    saida.append(_cortar(linha_uso, largura))
    saida.append("")

    saida.append(_bloco("chaves", tema, largura, t))
    total, uteis, mortas, frias = _contagem_keys()
    saida.append(_linha("carregadas", total, tema, largura))
    saida.append(_linha("utilizaveis",
                        p["ok"] + str(uteis) + RESET, tema, largura))
    if mortas:
        saida.append(_linha("mortas",
                            p["erro"] + str(mortas) + RESET, tema, largura))
    saida.append(_linha("em cooldown",
                        (p["alerta"] + str(frias) + RESET) if frias
                        else (p["fraco"] + "0" + RESET), tema, largura))
    if not total:
        saida.append(_linha("aviso",
                            p["alerta"] + "rode o Farm Key" + RESET,
                            tema, largura))
    else:
        # estado de cada key, curto: #0 ok, #1 espera 12s, #2 morta
        marcas = []
        for indice, estado, espera, _tok in _detalhe_keys():
            if estado == "dead":
                marcas.append(p["erro"] + "#%d morta" % indice + RESET)
            elif espera > 0:
                marcas.append(p["alerta"] + "#%d %ds" % (indice, espera)
                              + RESET)
            elif estado == "live":
                marcas.append(p["ok"] + "#%d ok" % indice + RESET)
            else:
                marcas.append(p["fraco"] + "#%d nova" % indice + RESET)
        if marcas:
            saida.append(_cortar("  " + p["fraco"] + "estado "
                                 + RESET + "  ".join(marcas), largura))
    saida.append("")

    saida.append(_bloco("modelos expostos (%d)" % len(modelos),
                        tema, largura, t))
    # duas colunas: 6 modelos cabem em 3 linhas em vez de 6
    if modelos and largura >= 76 and len(modelos) > 3:
        metade = (len(modelos) + 1) // 2
        col = (largura - 4) // 2
        for i in range(metade):
            esq = modelos[i]
            dirr = modelos[i + metade] if i + metade < len(modelos) else ""
            n = rotas.get(esq)
            e1 = (p["texto2"] + esq + RESET
                  + ((p["fraco"] + " %dr" % n + RESET) if n else ""))
            e2 = ""
            if dirr:
                n2 = rotas.get(dirr)
                e2 = (p["texto2"] + dirr + RESET
                      + ((p["fraco"] + " %dr" % n2 + RESET) if n2 else ""))
            vis = temas.largura_visivel(esq) + (3 if n else 0)
            saida.append(_cortar("  " + e1 + " " * max(2, col - vis) + e2,
                                 largura))
    else:
        for nome in modelos:
            n = rotas.get(nome)
            extra = (p["fraco"] + "  %d rotas" % n + RESET) if n else ""
            saida.append(_cortar("  " + p["texto2"] + nome + RESET + extra,
                                 largura))
    if not modelos:
        saida.append(_linha("", p["fraco"] + "nenhum" + RESET, tema, largura))
    saida.append("")

    saida.append(_bloco("ambiente", tema, largura, t))
    # navegador + threads na mesma linha quando couber, para sobrar
    # espaco para os modelos e a lista de copia
    nav = str(_navegador(conf))
    thr = conf.get("threads", "-")
    jb = bool(conf.get("jailbreak"))
    jb_txt = (p["ok"] + "ON" + RESET) if jb else (p["fraco"] + "OFF" + RESET)
    tm = temas.NOMES.get(conf.get("tema"), "-")
    if largura >= 90:
        linha = ("  " + p["fraco"] + "navegador " + RESET
                 + p["texto"] + nav + RESET
                 + p["fraco"] + "    threads " + RESET
                 + p["texto"] + str(thr) + RESET
                 + p["fraco"] + "    jailbreak " + RESET + jb_txt
                 + p["fraco"] + "    tema " + RESET
                 + p["texto2"] + tm + RESET)
        saida.append(_cortar(linha, largura))
    else:
        saida.append(_linha("navegador", nav, tema, largura))
        saida.append(_linha("threads", thr, tema, largura))
        saida.append(_linha("jailbreak", jb_txt, tema, largura))
        saida.append(_linha("tema", tm, tema, largura))

    return saida


def _tempo(seg):
    seg = int(seg)
    if seg < 60:
        return "%ds" % seg
    if seg < 3600:
        return "%dm %ds" % (seg // 60, seg % 60)
    return "%dh %dm" % (seg // 3600, (seg % 3600) // 60)


# -------------------------------------------------------------- interacao
def _opcoes_copia():
    """Lista ordenada do que da para copiar. A tecla e o indice (1..4),
    mas tambem da para navegar com as setas e confirmar com Enter."""
    url = _base_url()
    key = api_key_local()
    return [
        ("base url", url),
        ("api key", key),
        ("url + key (.env)", "OPENAI_BASE_URL=%s\nOPENAI_API_KEY=%s"
         % (url, key)),
        ("modelo pronto (curl)",
         'curl %s/chat/completions -H "Authorization: Bearer %s" '
         '-H "Content-Type: application/json" -d '
         '\'{"model":"gpt-6-astra-free","messages":'
         '[{"role":"user","content":"oi"}]}\'' % (url, key)),
    ]


def _acoes_copia(tema, escolhido, largura, msg=""):
    """Linhas da lista de copia, com o item escolhido em destaque."""
    p = temas.paleta(tema)
    saida = []
    opcoes = _opcoes_copia()
    for i, (rotulo, texto) in enumerate(opcoes):
        num = "%d" % (i + 1)
        if i == escolhido:
            # destaque: fundo claro e texto escuro (contraste garantido)
            marca = p["destaque"] + BOLD + ">" + RESET
            linha = (p["destaque"] + BOLD + " %s  %-20s %s"
                     % (num, rotulo, _amostra(texto)) + RESET)
            linha = (temas.rgb(255, 255, 255) + temas.rgb(30, 30, 45, fundo=True)
                     + linha + RESET)
            linha = marca + linha
        else:
            linha = ("  " + p["fraco"] + "%s " % num + RESET
                     + p["texto2"] + "%-20s " % rotulo + RESET
                     + p["fraco"] + _amostra(texto) + RESET)
        saida.append(_cortar(linha, largura))
    return saida


def _amostra(texto):
    """Primeira linha do conteudo, curta, para o usuario ver o que vai copiar."""
    primeiro = texto.split("\n")[0]
    if len(primeiro) > 44:
        primeiro = primeiro[:43] + "…"
    return primeiro


def abrir(app, cols, rows):
    """Tela de copia. Setas navegam, enter copia, 1-4 copiam direto."""
    import menu_principal as mp

    tema = app.tema
    conf = app.conf
    t0 = time.time()
    msg = ""
    msg_ate = 0.0
    escolhido = 0
    opcoes = _opcoes_copia()

    while True:
        t = time.time() - t0
        largura = max(60, cols - 6)
        # ---- monta o quadro de cima para baixo, cabendo SEMPRE ----
        # O console real pode exibir menos linhas que o rows reportado,
        # entao a tela e curta de proposito: o essencial (conexao, uso,
        # chaves, modelos, copiar) vem primeiro e a dica fecha embaixo.
        linhas = _enxuto(conf, tema, largura, t, row_limite=rows)

        quadro = []
        if tema == temas.INFINITY:
            nome = temas.rolar_arco("SERVERINFO", t, brilho=1.0)
        else:
            p = temas.paleta(tema)
            nome = p["brilho"] + BOLD + "SERVERINFO" + RESET
        quadro.append(mp._centro(nome, largura))
        quadro.append(mp.divisor(largura, tema, t))
        quadro.extend(linhas)

        p = temas.paleta(tema)
        quadro.append(_bloco("copiar", tema, largura, t))
        quadro.extend(_acoes_copia(tema, escolhido, largura))

        # mensagem de confirmacao logo abaixo da lista (sempre visivel)
        if msg and time.time() < msg_ate:
            quadro.append(mp._centro(p["ok"] + BOLD + msg + RESET, largura))
        else:
            quadro.append("")
            msg = ""

        dica = (p["fraco"] + "setas escolher   enter copiar   "
                "1-4 direto   esc voltar" + RESET)
        quadro.append(mp.divisor(largura, tema, t))
        quadro.append(mp._centro(dica, largura))

        mp.desenhar(quadro, cols, rows)

        tecla = mp.le_tecla(timeout=0.4)
        if tecla is None:
            continue

        if tecla in ("esc", "q"):
            return
        if tecla in ("cima", "k"):
            escolhido = (escolhido - 1) % len(opcoes)
            continue
        if tecla in ("baixo", "j"):
            escolhido = (escolhido + 1) % len(opcoes)
            continue

        alvo = None
        if tecla in ("enter", "espaco"):
            alvo = escolhido
        elif tecla in ("1", "2", "3", "4"):
            alvo = min(int(tecla) - 1, len(opcoes) - 1)
            escolhido = alvo
        elif tecla == "c":
            alvo = 2                     # url + key
            escolhido = alvo

        if alvo is not None:
            rotulo, texto = opcoes[alvo]
            ok = _copiar(texto)
            msg = ("copiado: " + rotulo) if ok else ("falhou: " + rotulo)
            msg_ate = time.time() + 4.0


def _copiar(texto):
    """Copia para a area de transferencia em qualquer sistema.

    No Windows tenta primeiro a API nativa (ctypes): ela funciona mesmo
    sem o `clip.exe` no PATH e devolve True/False confiavel. O `clip` fica
    como plano B.
    """
    if os.name == "nt":
        if _copiar_win32(texto):
            return True
        try:
            import subprocess
            p = subprocess.Popen(["clip"], stdin=subprocess.PIPE,
                                 shell=True)
            p.communicate(texto.encode("utf-16-le"))
            return p.returncode == 0
        except Exception:
            pass
        return False

    try:
        import subprocess
        if sys.platform == "darwin":
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            p.communicate(texto.encode("utf-8"))
            return p.returncode == 0
        import shutil
        for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"],
                    ["xsel", "--clipboard", "--input"]):
            if shutil.which(cmd[0]):
                p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                p.communicate(texto.encode("utf-8"))
                return p.returncode == 0
    except Exception:
        pass
    return False


def _copiar_win32(texto):
    """Area de transferencia pela API do Windows (sem depender do clip).

    OpenClipboard devolve "Access is denied" quando outro programa esta
    com o clipboard aberto por um instante (comum: navegador, Explorer,
    PowerShell). Isso e transitorio: tentamos algumas vezes.
    """
    for tentativa in range(12):
        if _copiar_win32_uma(texto):
            return True
        time.sleep(0.04 * (tentativa + 1))
    return False


def _copiar_win32_uma(texto):
    try:
        import ctypes

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        u = ctypes.windll.user32
        k = ctypes.windll.kernel32
        # assinaturas explicitas: sem isso o ctypes trunca handles em 64 bits
        u.OpenClipboard.argtypes = [ctypes.c_void_p]
        u.OpenClipboard.restype = ctypes.c_int
        u.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        u.SetClipboardData.restype = ctypes.c_void_p
        k.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        k.GlobalAlloc.restype = ctypes.c_void_p
        k.GlobalLock.argtypes = [ctypes.c_void_p]
        k.GlobalLock.restype = ctypes.c_void_p
        k.GlobalUnlock.argtypes = [ctypes.c_void_p]
        k.GlobalFree.argtypes = [ctypes.c_void_p]

        if not u.OpenClipboard(None):
            return False
        try:
            u.EmptyClipboard()
            dados = (texto + "\0").encode("utf-16-le")
            handle = k.GlobalAlloc(GMEM_MOVEABLE, len(dados))
            if not handle:
                return False
            ponteiro = k.GlobalLock(handle)
            if not ponteiro:
                k.GlobalFree(handle)
                return False
            try:
                ctypes.memmove(ponteiro, dados, len(dados))
            finally:
                k.GlobalUnlock(handle)
            # depois do SetClipboardData o buffer pertence ao sistema
            if not u.SetClipboardData(CF_UNICODETEXT, handle):
                k.GlobalFree(handle)
                return False
            return True
        finally:
            u.CloseClipboard()
    except Exception:
        return False


