"""Gambiarra verdadeira: emailnator pelo navegador.

Sem API, sem cota, sem chave. Abre o site numa aba e clica no que
o usuario descreveu:

  toggles: +Gmail ON, .Gmail ON, GoogleMail OFF (fake), Domain OFF
  botao:   "Go !" quando o endereco for @gmail.com
  botao:   "Generate New" quando nao for
  inbox:   "Reload" ate aparecer o e-mail da RouterPlex
  depois:  clica na mensagem e le o link de verificacao

Funcoes:
  abrir_emailnator(h, indice_aba)   abre a aba e deixa os toggles certos
  gerar_gmail(h)                    devolve um @gmail.com ou None
  ler_routerplex(h, segundos)       espera o e-mail e devolve o link
"""
import json
import random
import time

import antianuncio

URL = "https://www.emailnator.com/"
SEL_EMAIL = "span.mf-mono"
SEL_GO = "button.mf-btn-go"
SEL_GEN = "button.mf-btn-ghost"

# toggles: texto exato do chip
TOGGLES = {"Domain": False, "+Gmail": True, ".Gmail": True,
           "GoogleMail": False}


def _js(h, expr, espera=30):
    return h.js(expr, espera=espera)


def _aba_ativa(h, indice):
    """Troca a aba ativa pela posicao (0 = primeira)."""
    return _js(h, """(function(){
      const els = [...document.querySelectorAll('.mf-toggles .mf-chip')];
      return els.length;
    })()""")


def _chip(h, rotulo):
    """Devolve true se o chip esta ligado."""
    r = _js(h, """(function(){
      const chip = [...document.querySelectorAll('.mf-toggles .mf-chip')]
        .find(c => (c.innerText||'').trim() === %s);
      if (!chip) return 'sem chip';
      return chip.getAttribute('aria-pressed') === 'true';
    })()""" % json.dumps(rotulo))
    return r


def _clicar_chip(h, rotulo, estado):
    """Clica no chip ate ficar no estado desejado.

    O chip fica abaixo da dobra (y~824 numa janela de 820): precisa
    rolar ate ele, senao o clique do mouse cai fora da viewport.
    """
    for _ in range(4):
        atual = _chip(h, rotulo)
        if atual == "sem chip":
            return False
        if atual == estado:
            return True
        caixa = _js(h, """(function(){
          const chip = [...document.querySelectorAll('.mf-toggles .mf-chip')]
            .find(c => (c.innerText||'').trim() === %s);
          if (!chip) return null;
          chip.scrollIntoView({block:'center'});
          const r = chip.getBoundingClientRect();
          return [r.x+r.width/2, r.y+r.height/2, r.top, r.bottom,
                  window.innerHeight];
        })()""" % json.dumps(rotulo))
        if not caixa:
            return False
        x, y, topo, base, altura = caixa[:5]
        # confirma que esta dentro da janela
        if topo < 0 or base > altura:
            time.sleep(0.4)
            caixa = _js(h, """(function(){
              const chip = [...document.querySelectorAll('.mf-toggles .mf-chip')]
                .find(c => (c.innerText||'').trim() === %s);
              if (!chip) return null;
              chip.scrollIntoView({block:'center'});
              const r = chip.getBoundingClientRect();
              return [r.x+r.width/2, r.y+r.height/2];
            })()""" % json.dumps(rotulo))
            if not caixa:
                return False
            x, y = caixa[0], caixa[1]
        time.sleep(random.uniform(0.1, 0.25))
        h.clicar(x=x, y=y)
        time.sleep(random.uniform(0.45, 0.85))
    return _chip(h, rotulo) == estado


def email_atual(h):
    """Le o endereco mostrado em destaque."""
    return _js(h, """(function(){
      const e = document.querySelector(%s);
      return e ? e.innerText.trim() : '';
    })()""" % json.dumps(SEL_EMAIL))


def abrir_emailnator(h, configurar=False):
    """Navega para o emailnator e tira o anuncio.

    Os chips de toggle sao ignorados: nao mudam de estado de jeito
    nenhum. Quem garante o Gmail e o filtro em gerar_gmail().
    """
    h.ir(URL, esperar=3.0)
    for _ in range(40):
        if _js(h, "!!document.querySelector('.mf-toggles')"):
            break
        time.sleep(0.6)
    time.sleep(random.uniform(0.8, 1.6))

    # o anuncio cobre a tela: sem isso nenhum clique passa
    antianuncio.garantir_limpo(h, segundos=6)

    # espera o primeiro endereco sair do "Generating..." (~8s)
    _esperar_endereco(h, segundos=30)
    return True


def _clicar_botao(h, seletor):
    caixa = _js(h, """(function(){
      const b = document.querySelector(%s);
      if (!b) return null;
      b.scrollIntoView({block:'center'});
      const r = b.getBoundingClientRect();
      return [r.x+r.width/2, r.y+r.height/2];
    })()""" % json.dumps(seletor))
    if not caixa:
        return False
    h.mexer(caixa[0], caixa[1])
    time.sleep(random.uniform(0.04, 0.12))
    h.clicar(x=caixa[0], y=caixa[1])
    return True


def _gerando(h):
    """True enquanto o site mostra 'Generating...'."""
    e = email_atual(h)
    return (not e) or ("@" not in e) or ("generating" in e.lower())


def _esperar_endereco(h, segundos=30):
    """Espera o 'Generating...' virar um endereco.

    NUNCA clicar enquanto gera: clicar em Generate New durante o
    Generating trava o site num loop que nao termina.
    """
    fim = time.time() + segundos
    while time.time() < fim:
        e = email_atual(h)
        if e and "@" in e and "generating" not in e.lower():
            return e
        time.sleep(0.5)
    return email_atual(h)


def gerar_gmail(h, maximo=30, log=None):
    """Gira Generate New ate sair um @gmail.com de verdade.

    Regra de ouro: so clica quando o endereco ja apareceu. Clicar
    durante o 'Generating...' trava o site.
    """
    for i in range(maximo):
        # espera a geracao acabar (nunca clica durante)
        email = _esperar_endereco(h, segundos=30)
        if email and email.endswith("@gmail.com"):
            if log:
                log("GMAIL na tentativa %d: %s" % (i + 1, email))
            return email
        if email and "@" in email:
            if log:
                log("tentativa %d: %s (descartado)" % (i + 1, email))
        else:
            if log:
                log("tentativa %d: travado sem endereco" % (i + 1))
            # trava: recarrega a pagina para desbloquear
            h.ir(URL, esperar=2.5)
            time.sleep(1.0)
            continue
        if antianuncio.tem_modal(h):
            antianuncio.destravar(h)
        _clicar_botao(h, SEL_GEN)
        # deixa o Generating comecar antes de esperar de novo
        time.sleep(1.0)
    return None


def confirmar_go(h):
    """Clica no 'Go !' para abrir a caixa do endereco."""
    _clicar_botao(h, SEL_GO)
    time.sleep(random.uniform(1.2, 2.2))


def _mensagens(h):
    """Lista as mensagens visiveis na caixa."""
    r = _js(h, """JSON.stringify([...document.querySelectorAll('.mf-msg-row')]
      .map(row => {
        const a = row.querySelector('a.mf-msg-link');
        const de = row.querySelector('.mf-msg-from');
        const as = row.querySelector('.mf-msg-subject');
        return {
          href: a ? a.getAttribute('href') : null,
          de: de ? de.innerText.trim() : '',
          assunto: as ? as.innerText.trim() : '',
          travada: !!row.querySelector('.mf-msg-locked')
        };
      }))""")
    try:
        return json.loads(r) if r else []
    except Exception:
        return []


def reload(h):
    """Aperta o botao Reload do painel (limpando o anuncio antes)."""
    if antianuncio.tem_modal(h):
        antianuncio.destravar(h)
    return _clicar_botao(h, "button.mf-panel-btn")


def limpar(h):
    """Devolve o HTML inteiro da pagina (para achar o link)."""
    return _js(h, "document.documentElement.innerHTML") or ""


def esperar_routerplex(h, segundos=90, log=None):
    """Espera o e-mail de verificacao da RouterPlex.

    Volta o link de verificacao, ou None.
    """
    fim = time.time() + segundos
    visto = set()
    while time.time() < fim:
        for m in _mensagens(h):
            if m["travada"]:
                continue
            chave = (m["de"] + "|" + m["assunto"]).lower()
            if chave in visto:
                continue
            de = m["de"].lower()
            as_ = m["assunto"].lower()
            if "routerplex" in de and "verify" in as_:
                visto.add(chave)
                if log:
                    log("e-mail da RouterPlex: %s" % m["assunto"])
                link = _abrir_e_ler(h, m["href"], log=log)
                if link:
                    return link
        reload(h)
        time.sleep(3.0)
    return None


def _abrir_e_ler(h, href, log=None):
    """Abre a mensagem e tira o link de verificacao."""
    if not href:
        return None
    url = href if href.startswith("http") else "https://www.emailnator.com" + href
    h.ir(url, esperar=2.5)
    time.sleep(random.uniform(0.8, 1.4))
    if antianuncio.tem_modal(h):
        antianuncio.destravar(h)
        time.sleep(0.4)
    html = limpar(h)
    i = html.find("/verify?token=")
    if i < 0:
        # pode estar como link relativo
        i = html.find("verify?token=")
        if i < 0:
            if log:
                log("sem link de verificacao nesta mensagem")
            return None
    # volta ate a aspa/href
    ini = html.rfind("http", 0, i)
    if ini < 0 or i - ini > 200:
        ini = i
    fim = i
    while fim < len(html) and html[fim] not in '"\'> ':
        fim += 1
    trecho = html[ini:fim]
    if trecho.startswith("http"):
        return trecho
    return "https://routerplex.com/" + trecho.lstrip("/")
