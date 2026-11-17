"""Tela de CONFIG.

Subtelas:
  tema        LEGACY / INFINITE
  navegador   detecta os instalados e deixa trocar
  proxy       automatico / aleatorio / rotativo / sem proxy
  threads     quantas no farm
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import menu_principal as mp
import navegadores
import temas
import tela_mail as _tela_mail

ESC = "\x1b["


def _p(tema):
    return temas.paleta(tema)


def _cabecalho(titulo, tema, largura, t):
    p = _p(tema)
    if tema == temas.INFINITY:
        return [mp._centro(temas.rolar_arco(titulo, t, brilho=1.0), largura - 2)]
    return [mp._centro(p["brilho"] + temas.BOLD + titulo + temas.RESET,
                       largura - 2)]


def _caixa(corpo, tema, largura, t):
    if tema == temas.INFINITY:
        return mp.moldura_infinity(corpo, largura, t)
    return mp.moldura_legacy(corpo, largura)


def _marca(sel, tema, t, ativo=None):
    """Marcador da esquerda. Se `ativo` for dado, e um radio button."""
    p = _p(tema)
    if ativo is not None:
        if tema == temas.INFINITY:
            if ativo:
                return temas.rolar_arco("◉ ", t)
            return p["fraco"] + "○ " + temas.RESET
        return (p["destaque"] + "● " + temas.RESET) if ativo \
            else (p["fraco"] + "○ " + temas.RESET)
    if sel:
        if tema == temas.INFINITY:
            return temas.rolar_arco("▸ ", t)
        return p["destaque"] + "▸ " + temas.RESET
    return "  "


def _linha_opcao(texto, sel, tema, t, ativo=None, extra=""):
    p = _p(tema)
    marca = _marca(sel, tema, t, ativo)
    if sel:
        if tema == temas.INFINITY:
            fundo = temas.rgb(80, 60, 180, fundo=True)
            corpo = fundo + temas.BOLD + " " + texto + temas.RESET
        else:
            corpo = p["fundo_destaque"] + temas.BOLD + " " + texto + temas.RESET
    else:
        cor = p["texto2"] if ativo else p["texto2"]
        corpo = temas.BOLD + " " + cor + texto + temas.RESET
    if extra:
        corpo += "  " + p["fraco"] + extra + temas.RESET
    return "  " + marca + corpo


def _rodape(tema, largura, t, dica="setas mover   enter escolher   esc voltar"):
    p = _p(tema)
    if tema == temas.INFINITY:
        return " " + temas.pintar_arco(dica, t * 0.2, brilho=0.72)
    return " " + p["fraco"] + dica + temas.RESET


def _montar(corpo, tema, largura, t, cols):
    caixa = _caixa(corpo, tema, largura, t)
    saida = [""]
    for l in caixa:
        saida.append(mp._centro(l, cols))
    return saida


def _loop(render, tema):
    """Roda um loop de tela com animacao ate a acao pedir para sair."""
    mp.drenar()
    sys.stdout.write(ESC + "?25l")
    try:
        while True:
            cols, rows = mp.tamanho()
            mp.desenhar(render(cols, rows), cols, rows)
            tecla = mp.le_tecla(0.09)
            if tecla is None:
                continue
            resultado = yield_tecla(render, tecla)
            if resultado is not None:
                return resultado
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h")
        sys.stdout.flush()


def yield_tecla(render, tecla):
    """Placeholder trocado pelo _loop_real; mantido por compatibilidade."""
    return None


class Subtela:

    def __init__(self, conf):
        self.conf = dict(conf)
        self.tema = conf.get("tema") or temas.LEGACY
        self.t0 = time.time()

    def agora(self):
        return time.time() - self.t0

    def salvar(self):
        temas.salvar(self.conf)


# ------------------------------------------------------------------ tema

def tela_tema(conf, cols, rows):
    st = Subtela(conf)
    opcoes = [temas.LEGACY, temas.INFINITY]
    escolhido = opcoes.index(st.tema) if st.tema in opcoes else 0
    mp.drenar()

    def render(c, r):
        t = st.agora()
        largura = max(50, min(c - 1, 92))
        corpo = [""]
        corpo.extend(_cabecalho("CONFIG  /  TEMA", st.tema, largura, t))
        corpo.append("")
        corpo.append("  " + _p(st.tema)["fraco"]
                     + "escolha a aparencia. nada muda no funcionamento."
                     + temas.RESET)
        corpo.append("")
        for i, nome in enumerate(opcoes):
            ativo = (i == escolhido)
            desc = ("vermelho, classico, loading simples"
                    if nome == temas.LEGACY
                    else "arco-iris animado, loading elaborado")
            corpo.append(_linha_opcao(temas.NOMES[nome], i == escolhido,
                                      st.tema, t, ativo, desc))
        corpo.append("")
        corpo.append(_rodape(st.tema, largura, t))
        return _montar(corpo, st.tema, largura, t, c)

    sys.stdout.write(ESC + "?25l")
    try:
        while True:
            c, r = mp.tamanho()
            mp.desenhar(render(c, r), c, r)
            tecla = mp.le_tecla(0.09)
            if tecla is None:
                continue
            if tecla in ("cima", "k"):
                escolhido = (escolhido - 1) % len(opcoes)
            elif tecla in ("baixo", "j"):
                escolhido = (escolhido + 1) % len(opcoes)
            elif tecla in ("1", "2"):
                escolhido = int(tecla) - 1
                tecla = "enter"
            elif tecla in ("esc", "backspace"):
                return
            if tecla == "enter":
                st.conf["tema"] = opcoes[escolhido]
                st.salvar()
                return opcoes[escolhido]
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h")
        sys.stdout.flush()


# ------------------------------------------------------------- navegador

def tela_navegador(conf, cols, rows):
    st = Subtela(conf)
    mp.drenar()

    detectando = {"feito": False, "lista": [], "t0": time.time()}
    escolhido = 0
    rolando = 0
    MAX_VISIVEL = 8

    def detectar():
        detectando["lista"] = navegadores.detectar()
        atual = st.conf.get("navegador")
        detectando["lista"].insert(0, {"tipo": "auto", "caminho": None,
                                       "nome": "Automatico (melhor do sistema)"})
        for i, a in enumerate(detectando["lista"]):
            if a["caminho"] and atual and a["caminho"].lower() == atual.lower():
                detectando["escolhido"] = i
        detectando["feito"] = True

    def render(c, r):
        t = st.agora()
        largura = max(50, min(c - 1, 92))
        corpo = [""]
        corpo.extend(_cabecalho("CONFIG  /  NAVEGADOR", st.tema, largura, t))
        corpo.append("")

        if not detectando["feito"]:
            det = time.time() - detectando["t0"]
            spin = temas.spinner(int(det * 10), st.tema)
            corpo.append("  " + _p(st.tema)["texto"]
                         + "  %s  procurando navegadores no seu pc..." % spin
                         + temas.RESET)
            corpo.append("")
            for _ in range(MAX_VISIVEL):
                corpo.append("")
            corpo.append(_rodape(st.tema, largura, t, "aguarde"))
            return _montar(corpo, st.tema, largura, t, c)

        lista = detectando["lista"]
        corpo.append("  " + _p(st.tema)["fraco"]
                     + "%d encontrado(s). o farm usa o escolhido."
                     % (len(lista) - 1) + temas.RESET)
        corpo.append("")
        ini = rolando
        fim = min(len(lista), ini + MAX_VISIVEL)
        for i in range(ini, fim):
            item = lista[i]
            ativo = (i == escolhido)
            marca_radio = (st.conf.get("navegador") == item["caminho"]
                           if item["caminho"] else not st.conf.get("navegador"))
            extra = ""
            if item["caminho"]:
                extra = item["caminho"]
                if len(extra) > 42:
                    extra = "…" + extra[-41:]
            corpo.append(_linha_opcao(item["nome"], ativo, st.tema, t,
                                      marca_radio, extra))
        for _ in range(MAX_VISIVEL - (fim - ini)):
            corpo.append("")
        corpo.append("")
        corpo.append(_rodape(st.tema, largura, t))
        return _montar(corpo, st.tema, largura, t, c)

    sys.stdout.write(ESC + "?25l")
    try:
        while True:
            if not detectando["feito"] and time.time() - detectando["t0"] > 0.7:
                detectar()
                escolhido = detectando.get("escolhido", 0)
                _ajustar_rolagem = None
            c, r = mp.tamanho()
            mp.desenhar(render(c, r), c, r)
            tecla = mp.le_tecla(0.09)
            if not detectando["feito"]:
                continue
            if tecla is None:
                continue
            total = len(detectando["lista"])
            if tecla in ("cima", "k"):
                escolhido = (escolhido - 1) % total
            elif tecla in ("baixo", "j"):
                escolhido = (escolhido + 1) % total
            elif tecla in ("esc", "backspace"):
                return
            elif tecla == "enter":
                item = detectando["lista"][escolhido]
                st.conf["navegador"] = item["caminho"]
                st.salvar()
                return item["caminho"]
            # mantem o escolhido visivel
            if escolhido < rolando:
                rolando = escolhido
            elif escolhido >= rolando + MAX_VISIVEL:
                rolando = escolhido - MAX_VISIVEL + 1
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h")
        sys.stdout.flush()


# ----------------------------------------------------------------- proxy

def _contar_proxies():
    """Quantas proxies estao no cache (leitura rapida, sem testar)."""
    try:
        import proxies
        total = len(proxies.load())
    except Exception:
        total = 0
    return total


def tela_proxy(conf, cols, rows):
    st = Subtela(conf)
    mp.drenar()
    opcoes = ["auto", "gerador", "random", "rotativa", "nenhum"]
    atual = st.conf.get("proxy_modo", "auto")
    escolhido = opcoes.index(atual) if atual in opcoes else 0
    editando = False
    buffer = st.conf.get("proxy_url", "")
    erro = ""
    total_cache = _contar_proxies()

    def render(c, r):
        t = st.agora()
        largura = max(50, min(c - 1, 96))
        corpo = [""]
        corpo.extend(_cabecalho("CONFIG  /  PROXY", st.tema, largura, t))
        corpo.append("")
        corpo.append("  " + _p(st.tema)["fraco"]
                     + "como o farm sai para a internet" + temas.RESET)
        corpo.append("")
        for i, modo in enumerate(opcoes):
            corpo.append(_linha_opcao(navegadores.ROTULO_MODO[modo],
                                      i == escolhido, st.tema, t,
                                      i == escolhido))
        corpo.append("")
        p = _p(st.tema)
        if total_cache:
            corpo.append("  " + p["ok"] + "█ " + p["texto2"]
                         + "%d proxies no cache (validadas antes de usar)"
                         % total_cache + temas.RESET)
        else:
            corpo.append("  " + p["alerta"] + "░ " + p["fraco"]
                         + "nenhuma proxy ainda: serao coletadas no farm"
                         + temas.RESET)
        corpo.append("")

        if editando:
            cursor = "_" if int(time.time() * 2) % 2 == 0 else " "
            txt = buffer[-58:] if len(buffer) > 58 else buffer
            corpo.append("  " + p["texto2"] + "URL do proxy rotativo:" + temas.RESET)
            corpo.append("  " + p["primaria"] + "  " + txt + cursor + temas.RESET)
            corpo.append("  " + p["fraco"]
                         + "ex: http://user:pass@host:porta   ctrl+v cola   "
                           "enter confirma   esc cancela"
                         + temas.RESET)
            if erro:
                corpo.append("  " + p["erro"] + "! " + erro + temas.RESET)
            else:
                corpo.append("")
        else:
            url = st.conf.get("proxy_url") or ""
            if url:
                corpo.append("  " + _p(st.tema)["fraco"] + "salvo: "
                             + _p(st.tema)["texto2"]
                             + navegadores._esconder(url) + temas.RESET)
                if opcoes[escolhido] == "rotativa":
                    corpo.append("  " + _p(st.tema)["fraco"]
                                 + "enter abre as opcoes de editar   "
                                   "e edita direto" + temas.RESET)
            corpo.append("")
            corpo.append(_rodape(st.tema, largura, t))
        return _montar(corpo, st.tema, largura, t, c)

    sys.stdout.write(ESC + "?25l")
    try:
        while True:
            c, r = mp.tamanho()
            mp.desenhar(render(c, r), c, r)
            # Dentro da edicao a leitura tem de ser SEMPRE le_texto.
            # Antes havia mp.le_tecla(0.09) aqui e outro le_texto logo
            # abaixo: cada volta do laco consumia DUAS teclas e descartava
            # uma. Ao colar a URL, isso comia metade dos caracteres —
            # "http://user:pass@host:porta" virava "ht:/..." na tela.
            tecla = mp.le_texto(0.09) if editando else mp.le_tecla(0.09)
            if tecla is None:
                continue

            if editando:
                if tecla == "esc":
                    editando = False
                    erro = ""
                    buffer = st.conf.get("proxy_url", "")
                elif tecla == "colar":
                    # Ctrl+V / botao direito: le a area de transferencia
                    # inteira de uma vez. Antes esta tecla era descartada
                    # em silencio e o usuario achava que a tela travou.
                    colado = mp.colar_area()
                    if colado:
                        colado = colado.strip().replace("\r", "").replace("\n", "")
                        buffer = (colado if not buffer else buffer + colado)
                        ok_chk, _ = navegadores.validar_url(buffer)
                        erro = "" if ok_chk else "confira a URL colada"
                elif tecla == "enter":
                    ok, msg = navegadores.validar_url(buffer) if buffer else (True, "ok")
                    if not ok:
                        # NAO limpa o erro: antes a linha "erro = ''"
                        # rodava a cada tecla e a mensagem nunca aparecia
                        erro = msg
                    else:
                        st.conf["proxy_url"] = buffer.strip()
                        st.conf["proxy_modo"] = "rotativa"
                        st.salvar()
                        editando = False
                        erro = ""
                        return st.conf["proxy_modo"]
                elif tecla == "backspace":
                    buffer = buffer[:-1]
                    erro = ""
                elif len(tecla) == 1:
                    buffer += tecla
                    erro = ""
                continue

            if tecla in ("cima", "k"):
                escolhido = (escolhido - 1) % len(opcoes)
            elif tecla in ("baixo", "j"):
                escolhido = (escolhido + 1) % len(opcoes)
            elif tecla == "1" and len(opcoes) > 0:
                escolhido = 0
                tecla = "enter"
            elif tecla in ("2", "3", "4"):
                escolhido = int(tecla) - 1
                tecla = "enter"
            elif tecla == "e" and opcoes[escolhido] == "rotativa":
                # atalho: editar a URL ja salva, mesmo com "rotativa" escolhido
                editando = True
                buffer = st.conf.get("proxy_url", "")
                erro = ""
                continue
            elif tecla in ("esc", "backspace"):
                return
            elif tecla == "enter":
                modo = opcoes[escolhido]
                if modo == "rotativa":
                    if not st.conf.get("proxy_url"):
                        # primeira vez: abre a edicao vazia
                        editando = True
                        buffer = ""
                        continue
                    # ja existe URL salva: pergunta entre usar e editar.
                    # Antes o enter so saia da tela, e a URL ficava presa
                    # sem nenhum jeito de corrigir depois de salva.
                    acao = _menu_editar_proxy(st)
                    if acao == "editar":
                        editando = True
                        buffer = st.conf.get("proxy_url", "")
                        erro = ""
                        continue
                    if acao == "apagar":
                        st.conf["proxy_url"] = ""
                        st.salvar()
                        return "auto"
                    if acao is None:
                        continue
                st.conf["proxy_modo"] = modo
                st.salvar()
                return modo
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h")
        sys.stdout.flush()


def _menu_editar_proxy(st):
    """Menu do proxy rotativo JA salvo.

    Devolve "usar", "editar", "apagar" ou None (voltou sem escolher).
    Existe porque, depois de salva, a URL so aparecia como texto e nao
    havia como corrigir sem apagar o config na mao.
    """
    url = st.conf.get("proxy_url") or ""
    opcoes = [
        ("usar", "Usar este proxy"),
        ("editar", "Editar a URL"),
        ("apagar", "Apagar a URL"),
    ]
    escolhido = 0
    mp.drenar()

    def render(c, r):
        t = st.agora()
        largura = max(50, min(c - 1, 96))
        p = _p(st.tema)
        corpo = [""]
        corpo.extend(_cabecalho("CONFIG  /  PROXY  /  ROTATIVO", st.tema,
                                largura, t))
        corpo.append("")
        corpo.append("  " + p["fraco"] + "URL salva:" + temas.RESET)
        corpo.append("  " + p["texto2"] + navegadores._esconder(url)
                     + temas.RESET)
        corpo.append("")
        for i, (_, rotulo) in enumerate(opcoes):
            corpo.append(_linha_opcao(rotulo, i == escolhido, st.tema, t,
                                      i == escolhido))
        corpo.append("")
        corpo.append(_rodape(st.tema, largura, t))
        return _montar(corpo, st.tema, largura, t, c)

    sys.stdout.write(ESC + "?25l")
    try:
        while True:
            c, r = mp.tamanho()
            mp.desenhar(render(c, r), c, r)
            tecla = mp.le_tecla(0.09)
            if tecla is None:
                continue
            if tecla in ("cima", "k"):
                escolhido = (escolhido - 1) % len(opcoes)
            elif tecla in ("baixo", "j"):
                escolhido = (escolhido + 1) % len(opcoes)
            elif tecla in ("1", "2", "3"):
                escolhido = int(tecla) - 1
                return opcoes[escolhido][0]
            elif tecla in ("esc", "backspace"):
                return None
            elif tecla == "enter":
                return opcoes[escolhido][0]
            elif tecla == "e":
                return "editar"
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h")
        sys.stdout.flush()


# --------------------------------------------------------------- threads
def tela_threads(conf, cols, rows):
    st = Subtela(conf)
    mp.drenar()
    valor = int(st.conf.get("threads") or 12)

    def render(c, r):
        t = st.agora()
        largura = max(50, min(c - 1, 80))
        p = _p(st.tema)
        corpo = [""]
        corpo.extend(_cabecalho("CONFIG  /  THREADS", st.tema, largura, t))
        corpo.append("")
        corpo.append("  " + p["fraco"]
                     + "quantas contas o farm tenta ao mesmo tempo" + temas.RESET)
        corpo.append("")
        barra = temas.barra(min(1.0, valor / 32.0), 30, st.tema, t)
        corpo.append("  " + p["texto"] + "  " + str(valor).rjust(2) + "  "
                     + temas.RESET + barra)
        corpo.append("")
        time.sleep(0)
        dica = ("mais threads = mais rapido, mas mais chance de bloqueio"
                if valor > 16 else "valor seguro")
        corpo.append("  " + p["fraco"] + dica + temas.RESET)
        corpo.append("")
        corpo.append(_rodape(st.tema, largura, t,
                             "esquerda/direita ajusta   enter confirma   esc volta"))
        return _montar(corpo, st.tema, largura, t, c)

    sys.stdout.write(ESC + "?25l")
    try:
        while True:
            c, r = mp.tamanho()
            mp.desenhar(render(c, r), c, r)
            tecla = mp.le_tecla(0.09)
            if tecla is None:
                continue
            if tecla in ("esq", "a"):
                valor = max(1, valor - 1)
            elif tecla in ("dir", "d"):
                valor = min(32, valor + 1)
            elif tecla in ("cima", "k"):
                valor = min(32, valor + 4)
            elif tecla in ("baixo", "j"):
                valor = max(1, valor - 4)
            elif tecla in ("esc", "backspace"):
                return
            elif tecla == "enter":
                st.conf["threads"] = valor
                st.salvar()
                try:
                    import farmer_panel
                    farmer_panel.write_state(valor)
                except Exception:
                    pass
                return valor
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h")
        sys.stdout.flush()


# ------------------------------------------------------------- provider

def tela_provider(conf, cols=None, rows=None):
    """Escolhe o provider ativo entre fixos e customs. Devolve o nome."""
    tema = conf.get("tema") or temas.LEGACY
    try:
        import providers
        lista = providers.catalogo()
        atual = providers.nome_atual()
    except Exception:
        return None
    if not lista:
        return None
    opcoes = []
    for p in lista:
        marca = "  [ativo]" if p["nome"] == atual else ""
        extra = "custom" if p.get("custom") else p.get("nota", "")
        opcoes.append("%-14s  %s%s" % (p["titulo"], extra, marca))
    escolhido = 0
    for i, p in enumerate(lista):
        if p["nome"] == atual:
            escolhido = i
            break
    mp.drenar()
    sys.stdout.write(ESC + "?25l")
    try:
        while True:
            c, r = mp.tamanho()
            t = time.time()
            largura = max(50, min(c - 1, 96))
            p_ = _p(tema)
            corpo = [""]
            corpo.extend(_cabecalho("CONFIG  /  PROVIDER", tema, largura, t))
            corpo.append("")
            corpo.append("  " + p_["fraco"]
                         + "para onde o gateway manda as requisicoes"
                         + temas.RESET)
            corpo.append("")
            for i, texto in enumerate(opcoes):
                corpo.append(_linha_opcao(texto, i == escolhido, tema, t,
                                          lista[i]["nome"] == atual))
            corpo.append("")
            sel = lista[escolhido]
            corpo.append("  " + p_["texto2"] + "base url  " + temas.RESET
                         + p_["texto"] + sel["base"] + temas.RESET)
            corpo.append("")
            corpo.append(_rodape(tema, largura, t))
            corpo.append("  " + p_["fraco"]
                         + "custom = sua base url com rotacao de keys"
                         + temas.RESET)
            mp.desenhar(_montar(corpo, tema, largura, t, c), c, r)
            tecla = mp.le_tecla(0.09)
            if tecla is None:
                continue
            if tecla in ("cima", "k"):
                escolhido = (escolhido - 1) % len(lista)
            elif tecla in ("baixo", "j"):
                escolhido = (escolhido + 1) % len(lista)
            elif tecla in ("esc", "backspace"):
                return None
            elif tecla == "enter":
                nome = lista[escolhido]["nome"]
                if providers.definir(nome):
                    return lista[escolhido]["titulo"]
                return None
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h")
        sys.stdout.flush()


# ---------------------------------------------------------------- menu

def _nome_provider():
    """Rotulo do provider ativo."""
    try:
        import providers
        return providers.rotulo()
    except Exception:
        return "-"


def _resumo_custom():
    """Selo do Custom: quantos cadastrados, quantas keys no ativo."""
    try:
        import custom_provider
        import providers
        lista = custom_provider.carregar()
        if not lista:
            return "nenhum (toque para adicionar base url)"
        nome = providers.nome_atual()
        if nome.startswith("custom:"):
            p = custom_provider.por_nome(nome)
            if p:
                return "ativo: %s (%d keys)" % (p["titulo"], len(p["keys"]))
        total = sum(len(p["keys"]) for p in lista)
        return "%d cadastrado(s), %d keys" % (len(lista), total)
    except Exception:
        return "-"


def _resumo_mail(conf):
    """Selo do MAIL: qual provedor o farm usa, e se ele esta pronto."""
    try:
        ids = {"gmailnator": "Gmailnator"}
        try:
            import tempmail
            for p in tempmail.PROVEDORES:
                ids[p["id"]] = p["nome"]
        except Exception:
            pass
        escolhido = conf.get("mail_farm") or "gmailnator"
        nome = ids.get(escolhido, escolhido)
        if escolhido == "gmailnator":
            if not (conf.get("mail_gmailnator_key") or "").strip():
                return "falta a chave"
        ligados = conf.get("mail_ligados")
        if isinstance(ligados, list) and escolhido not in ligados:
            return "%s (desligado)" % nome
        return nome
    except Exception:
        return "-"


def abrir(conf, cols=None, rows=None):
    """Menu do CONFIG. Devolve o config atualizado."""
    conf = dict(conf)
    tema = conf.get("tema") or temas.LEGACY
    itens = ["provider", "custom", "tema", "navegador", "proxy", "mail",
             "threads"]
    rotulos = [
        ("Provider", lambda c: _nome_provider()),
        ("Custom Provider", lambda c: _resumo_custom()),
        ("Tema", lambda c: temas.NOMES.get(c.get("tema"), "-")),
        ("Navegador", lambda c: navegadores.rotulo(c.get("navegador"))),
        ("Proxy", lambda c: navegadores.descrever(c)),
        ("Mail", lambda c: _resumo_mail(c)),
        ("Threads", lambda c: str(c.get("threads") or 12)),
    ]
    escolhido = 0
    t0 = time.time()
    aviso = ""
    aviso_ate = 0.0
    mp.drenar()

    def render(c, r):
        t = time.time() - t0
        largura = max(50, min(c - 1, 92))
        p = _p(conf.get("tema") or tema)
        corpo = [""]
        corpo.extend(_cabecalho("CONFIG", conf.get("tema") or tema, largura, t))
        corpo.append("")
        for i, (nome, valor_fn) in enumerate(rotulos):
            ativo = (i == escolhido)
            marca = _marca(ativo, conf.get("tema") or tema, t)
            if ativo:
                if (conf.get("tema") or tema) == temas.INFINITY:
                    fundo = temas.rgb(80, 60, 180, fundo=True)
                    corpo.append("  " + marca + fundo + temas.BOLD
                                 + " " + nome.ljust(16) + temas.RESET + " "
                                 + p["texto"] + valor_fn(conf) + temas.RESET)
                else:
                    corpo.append("  " + marca + p["fundo_destaque"] + temas.BOLD
                                 + " " + nome.ljust(16) + temas.RESET + " "
                                 + p["texto"] + valor_fn(conf) + temas.RESET)
            else:
                corpo.append("  " + marca + temas.BOLD + " " + p["texto2"]
                             + nome.ljust(16) + temas.RESET + " "
                             + p["fraco"] + valor_fn(conf) + temas.RESET)
        corpo.append("")
        corpo.append(mp.divisor(largura, conf.get("tema") or tema, t))
        corpo.append(_rodape(conf.get("tema") or tema, largura, t))
        return _montar(corpo, conf.get("tema") or tema, largura, t, c)

    sys.stdout.write(ESC + "?25l")
    try:
        while True:
            c, r = mp.tamanho()
            mp.desenhar(render(c, r), c, r)
            tecla = mp.le_tecla(0.09)
            if tecla is None:
                continue
            if tecla in ("cima", "k"):
                escolhido = (escolhido - 1) % len(itens)
            elif tecla in ("baixo", "j"):
                escolhido = (escolhido + 1) % len(itens)
            elif tecla in ("1", "2", "3", "4", "5", "6", "7"):
                escolhido = min(int(tecla) - 1, len(itens) - 1)
                tecla = "enter"
            elif tecla in ("esc", "backspace"):
                return conf
            if tecla == "enter":
                alvo = itens[escolhido]
                if alvo == "custom":
                    import tela_custom
                    tela_custom.tela_custom(conf, c, r)
                    conf = temas.carregar()
                elif alvo == "provider":
                    novo = tela_provider(conf, c, r)
                    if novo:
                        aviso = "provider: %s - reinicie o app" % novo
                    else:
                        try:
                            import providers
                            aviso = "%s  (%s)" % (providers.rotulo(),
                                                  providers.atual()["base"])
                        except Exception as exc:
                            aviso = "provider: %s" % str(exc)[:40]
                    aviso_ate = time.time() + 8
                elif alvo == "tema":
                    novo = tela_tema(conf, c, r)
                    if novo:
                        conf["tema"] = novo
                elif alvo == "navegador":
                    tela_navegador(conf, c, r)
                    conf = temas.carregar()
                elif alvo == "proxy":
                    tela_proxy(conf, c, r)
                    conf = temas.carregar()
                elif alvo == "mail":
                    _tela_mail.tela_mail(conf, c, r)
                    conf = temas.carregar()
                elif alvo == "threads":
                    tela_threads(conf, c, r)
                    conf = temas.carregar()
                t0 = time.time() - 0.0
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h")
        sys.stdout.flush()
