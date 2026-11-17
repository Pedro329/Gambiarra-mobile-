"""CONFIG > MAIL.

Uma lista so, sem mensagens de status na tela:

    Gmailnator          chave         ATIVO
    mail.tm             sem chave       OFF
    Guerrilla Mail      sem chave       OFF
    temp-mail.io        sem chave       OFF
    Maildrop            sem chave       OFF

  enter   no Gmailnator abre a chave; nos outros nao faz nada
  espaco  liga / desliga
  f       escolhe qual provedor o farm usa

Quem le a caixa e o backend (tempmail.py / gmailnator.py). A tela nao
mostra conteudo de e-mail nenhum.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import menu_principal as mp
import temas
import tempmail

ESC = "\x1b["

GMAILNATOR = "gmailnator"


# ---------------------------------------------------------------- helpers

def _p(tema):
    return temas.paleta(tema)


def _cabecalho(titulo, tema, largura, t):
    p = _p(tema)
    if tema == temas.INFINITY:
        return [mp._centro(temas.rolar_arco(titulo, t, brilho=1.0),
                           largura - 2)]
    return [mp._centro(p["brilho"] + temas.BOLD + titulo + temas.RESET,
                       largura - 2)]


def _caixa(corpo, tema, largura, t):
    if tema == temas.INFINITY:
        return mp.moldura_infinity(corpo, largura, t)
    return mp.moldura_legacy(corpo, largura)


def _montar(corpo, tema, largura, t, cols):
    saida = [""]
    for linha in _caixa(corpo, tema, largura, t):
        saida.append(mp._centro(linha, cols))
    return saida


def _ljust_visivel(texto, largura):
    """ljust que ignora sequencias ANSI."""
    import re
    limpo = re.sub(r"\x1b\[[0-9;]*m", "", texto)
    falta = largura - len(limpo)
    return texto + (" " * falta if falta > 0 else "")


def _rodape(tema, dica):
    if tema == temas.INFINITY:
        return " " + temas.pintar_arco(dica, 0.2, brilho=0.72)
    return " " + _p(tema)["fraco"] + dica + temas.RESET


def _mascara(chave):
    """Chave mascarada, sempre com a mesma largura (24)."""
    if not chave:
        return "sem chave"
    if len(chave) <= 10:
        return ("********").ljust(24)
    return (chave[:5] + "*" * 13 + chave[-4:])[:24].ljust(24)


class Subtela:

    def __init__(self, conf):
        self.conf = conf
        self.tema = conf.get("tema") or temas.LEGACY
        self.t0 = time.time()

    def agora(self):
        return time.time() - self.t0

    def salvar(self):
        temas.salvar(self.conf)


# ------------------------------------------------------------ tela da chave

def _tela_chave(conf, cols, rows):
    """Colocar / editar a chave do Gmailnator. Sem mostrar a chave inteira."""
    st = Subtela(conf)
    mp.drenar()
    novo = None
    msg = ""
    msg_ate = 0.0

    def atual():
        return (st.conf.get("mail_gmailnator_key") or "").strip()

    def opcoes():
        return ([("editar", "editar api key")] if atual()
                else [("colocar", "colocar api key")]) + [("voltar", "voltar")]

    escolhido = 0
    sys.stdout.write(ESC + "?25l")
    try:
        while True:
            c, r = mp.tamanho()
            t = st.agora()
            largura = max(52, min(c - 1, 84))
            p = _p(st.tema)
            k = atual()
            corpo = [""]
            corpo.extend(_cabecalho("CONFIG  /  MAIL  /  GMAILNATOR",
                                    st.tema, largura, t))
            corpo.append("")
            if novo is not None:
                corpo.append("  " + p["brilho"] + temas.BOLD
                             + "cole a chave do RapidAPI" + temas.RESET)
                corpo.append("")
                corpo.append("  " + p["texto"] + _mascara(novo[:40])
                             + p["destaque"] + "_" + temas.RESET)
                corpo.append("")
                corpo.append("  " + p["fraco"]
                             + "ctrl+v cola   enter salva   esc cancela"
                             + temas.RESET)
            else:
                corpo.append("  " + p["fraco"] + "api key   " + temas.RESET
                             + (p["texto"] if k else p["alerta"])
                             + _mascara(k) + temas.RESET)
                corpo.append("")
                ops = opcoes()
                escolhido = min(escolhido, len(ops) - 1)
                for i, (_, rotulo) in enumerate(ops):
                    marca = "▸ " if i == escolhido else "  "
                    if i == escolhido and st.tema == temas.INFINITY:
                        marca = temas.rolar_arco("▸ ", t)
                    elif i == escolhido:
                        marca = p["destaque"] + "▸ " + temas.RESET
                    corpo.append("  " + marca + temas.BOLD + p["texto2"]
                                 + rotulo + temas.RESET)
            if msg and time.time() < msg_ate:
                corpo.append("")
                corpo.append("  " + p["destaque"] + msg + temas.RESET)
            corpo.append("")
            corpo.append(_rodape(st.tema, "enter escolhe   esc volta"
                                 if novo is None
                                 else "enter salva   esc cancela"))
            mp.desenhar(_montar(corpo, st.tema, largura, t, c), c, r)

            tecla = mp.le_tecla(0.09)
            if tecla is None:
                continue

            if novo is not None:
                if tecla == "enter":
                    if len(novo.strip()) > 10:
                        st.conf["mail_gmailnator_key"] = novo.strip()
                        st.salvar()
                        msg = "salvo"
                        msg_ate = time.time() + 2.5
                        novo = None
                    else:
                        msg = "curta demais"
                        msg_ate = time.time() + 2.5
                elif tecla in ("esc", "backspace"):
                    novo = None
                elif tecla == "colar":
                    novo += mp.colar_area() or ""
                elif len(tecla) > 1 and tecla.isprintable():
                    if len(novo) + len(tecla) <= 120:
                        novo += tecla
                elif len(tecla) == 1:
                    if len(novo) < 120:
                        novo += tecla
                continue

            ops = opcoes()
            if tecla in ("cima", "k"):
                escolhido = (escolhido - 1) % len(ops)
            elif tecla in ("baixo", "j"):
                escolhido = (escolhido + 1) % len(ops)
            elif tecla in ("esc", "backspace"):
                return
            elif tecla in ("1", "2", "3"):
                idx = int(tecla) - 1
                if idx < len(ops):
                    escolhido = idx
                    tecla = "enter"
                else:
                    continue
            if tecla == "enter":
                acao = ops[escolhido][0]
                if acao == "voltar":
                    return
                novo = ""
                continue
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h")
        sys.stdout.flush()


# ------------------------------------------------------------- estado

def lista():
    """Todos os provedores, Gmailnator primeiro."""
    itens = [(GMAILNATOR, "Gmailnator", True)]
    for p_ in tempmail.PROVEDORES:
        itens.append((p_["id"], p_["nome"], False))
    return itens


def ligados(conf):
    ids = [i[0] for i in lista()]
    salvo = conf.get("mail_ligados")
    if isinstance(salvo, list):
        return {i: (i in salvo) for i in ids}
    return {i: (i == GMAILNATOR) for i in ids}


def _tem_chave(conf):
    return bool((conf.get("mail_gmailnator_key") or "").strip())


def _selo(conf, pid):
    """ATIVO / OFF. Fica a direita da lista."""
    if pid == GMAILNATOR and not _tem_chave(conf):
        return "OFF", "alerta"
    vivo = ligados(conf).get(pid, False)
    return ("ATIVO" if vivo else "OFF"), ("destaque" if vivo else "fraco")


# ------------------------------------------------------------- tela mail

def tela_mail(conf, cols, rows):
    st = Subtela(conf)
    mp.drenar()
    itens = lista()
    escolhido = 0
    modo = None          # None = lista, "farm" = escolhendo o do farm
    farm_escolha = 0
    msg = ""
    msg_ate = 0.0

    def farm_atual():
        return st.conf.get("mail_farm") or GMAILNATOR

    def render(c, r):
        t = st.agora()
        largura = max(54, min(c - 1, 84))
        p = _p(st.tema)
        corpo = [""]
        corpo.extend(_cabecalho("CONFIG  /  MAIL", st.tema, largura, t))
        corpo.append("")

        if modo == "farm":
            corpo.append("  " + p["brilho"] + temas.BOLD
                         + "qual provedor o farm usa" + temas.RESET)
            corpo.append("")
            for i, (pid, nome, precisa) in enumerate(itens):
                if pid == GMAILNATOR and not _tem_chave(st.conf):
                    continue
                ativo = farm_atual() == pid
                sel = i == farm_escolha
                marca = ("◉ " if ativo else "○ ") if st.tema == temas.INFINITY \
                    else (p["destaque"] + "● " + temas.RESET if ativo
                          else p["fraco"] + "○ " + temas.RESET)
                if sel:
                    marca = (temas.rolar_arco("▸ ", t)
                             if st.tema == temas.INFINITY
                             else p["destaque"] + "▸ " + temas.RESET)
                corpo.append("  " + marca + temas.BOLD + p["texto2"]
                             + nome + temas.RESET)
        else:
            lg = ligados(st.conf)
            chave_ok = _tem_chave(st.conf)
            for i, (pid, nome, precisa) in enumerate(itens):
                sel = i == escolhido
                marca = ("▸ " if sel else "  ")
                if sel:
                    marca = (temas.rolar_arco("▸ ", t) if st.tema ==
                             temas.INFINITY else p["destaque"] + "▸ " + temas.RESET)
                # coluna do detalhe:
                #   Gmailnator  -> a chave mascarada, ou "falta a chave"
                #   os gratuitos -> "sem chave" nao faz sentido, eles nao usam
                #                   chave: mostra que estao prontos
                if pid == GMAILNATOR:
                    if chave_ok:
                        detalhe = _mascara(st.conf.get("mail_gmailnator_key")
                                           or "")
                        cor_det = p["fraco"]
                    else:
                        detalhe = "falta a chave"
                        cor_det = p["alerta"]
                else:
                    detalhe = "pronto"
                    cor_det = p["fraco"]
                esquerda = (temas.BOLD + p["texto2"] + nome.ljust(17)
                            + temas.RESET + " " + cor_det
                            + detalhe.ljust(24) + temas.RESET)
                # coluna do status, colada a direita
                vivo = lg.get(pid, False)
                if pid == GMAILNATOR and not chave_ok:
                    vivo = False
                selo = ("ATIVO" if vivo else "OFF").ljust(6)
                cor_selo = p["destaque"] if vivo else p["fraco"]
                if sel:
                    esquerda = (temas.rgb(80, 60, 180, fundo=True)
                                if st.tema == temas.INFINITY
                                else p["fundo_destaque"]) + esquerda
                corpo.append("  " + marca + esquerda + cor_selo
                             + temas.BOLD + selo + temas.RESET)
            corpo.append("")
            f = farm_atual()
            nome_f = next((n for i_, n, _ in itens if i_ == f), "-")
            corpo.append("  " + p["fraco"] + "farm usa   " + temas.RESET
                         + p["brilho"] + nome_f + temas.RESET)

        if msg and time.time() < msg_ate:
            corpo.append("")
            corpo.append("  " + p["destaque"] + msg + temas.RESET)
        corpo.append("")
        if modo == "farm":
            corpo.append(_rodape(st.tema,
                                 "setas escolhe   enter confirma   esc volta"))
        else:
            corpo.append(_rodape(st.tema,
                                 "espaco liga/desliga   enter muda a chave"
                                 "   f escolhe o farm   esc volta"))
        return _montar(corpo, st.tema, largura, t, c)

    sys.stdout.write(ESC + "?25l")
    try:
        while True:
            c, r = mp.tamanho()
            mp.desenhar(render(c, r), c, r)
            tecla = mp.le_tecla(0.09)
            if tecla is None:
                continue

            if modo == "farm":
                validos = [i for i, (pid, _, _) in enumerate(itens)
                           if pid != GMAILNATOR or _tem_chave(st.conf)]
                if not validos:
                    modo = None
                    continue
                if tecla in ("cima", "k"):
                    pos = validos.index(farm_escolha) if farm_escolha in validos else 0
                    farm_escolha = validos[(pos - 1) % len(validos)]
                elif tecla in ("baixo", "j"):
                    pos = validos.index(farm_escolha) if farm_escolha in validos else 0
                    farm_escolha = validos[(pos + 1) % len(validos)]
                elif tecla in ("esc", "backspace"):
                    modo = None
                elif tecla == "enter":
                    pid = itens[farm_escolha][0]
                    st.conf["mail_farm"] = pid
                    st.salvar()
                    msg = "farm usa %s" % itens[farm_escolha][1]
                    msg_ate = time.time() + 3
                    modo = None
                continue

            if tecla in ("cima", "k"):
                escolhido = (escolhido - 1) % len(itens)
            elif tecla in ("baixo", "j"):
                escolhido = (escolhido + 1) % len(itens)
            elif tecla in ("esc", "backspace"):
                return
            elif tecla == "f":
                modo = "farm"
                farm_escolha = next((i for i, (pid, _, _) in enumerate(itens)
                                     if pid == farm_atual()), 0)
            elif tecla == "espaco":
                pid = itens[escolhido][0]
                if pid == GMAILNATOR and not _tem_chave(st.conf):
                    msg = "coloque a chave primeiro"
                    msg_ate = time.time() + 3
                    continue
                lg = ligados(st.conf)
                lg[pid] = not lg.get(pid, False)
                st.conf["mail_ligados"] = [k for k, v in lg.items() if v]
                st.salvar()
            elif tecla == "enter":
                if itens[escolhido][0] == GMAILNATOR:
                    _tela_chave(st.conf, c, r)
                    st.conf = dict(st.conf)
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h")
        sys.stdout.flush()
