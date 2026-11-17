"""Remove o anuncio do Emailnator (Google Funding Choices).

O modal "Support Emailnator" e o dialogo `fc-*` do Funding Choices.
Testado: `remove()` direto no `.fc-monetization-dialog-container` limpa.
Nao ha verificacao no servidor.

Exporta:
    destravar(h)           remove o dialogo e libera a pagina
    tem_modal(h)           True se o anuncio ainda bloqueia
    garantir_limpo(h)      insiste ate limpar
"""
import time

# seletores na ordem que funciona (testado)
ALVOS = [
    ".fc-monetization-dialog-container",
    ".fc-dialog-overlay",
    ".fc-dialog-container",
    ".fc-consent-root",
    ".fc-monetization-dialog-message-container",
]

EXPR = """
(function() {
  let n = 0;
  const alvos = %s;
  for (const sel of alvos) {
    for (const el of document.querySelectorAll(sel)) {
      try { el.remove(); n++; } catch (e) {}
    }
  }
  // qualquer elemento fc- que sobre
  for (const el of document.querySelectorAll('[class^=fc-]')) {
    if (/dialog|overlay|consent|monetiz/i.test(el.className.toString())) {
      try { el.remove(); n++; } catch (e) {}
    }
  }
  // devolve scroll e cliques
  document.documentElement.style.overflow = '';
  document.documentElement.style.setProperty('overflow', '', 'important');
  document.body.style.overflow = '';
  document.body.style.setProperty('overflow', '', 'important');
  document.body.style.pointerEvents = '';
  document.body.style.setProperty('pointer-events', 'auto', 'important');
  return n;
})()
""" % str(ALVOS).replace("'", '"')


def tem_modal(h):
    """True se o anuncio ainda esta bloqueando."""
    r = h.js("""(function(){
      if (document.querySelector('.fc-monetization-dialog-container')) return true;
      if (document.querySelector('.fc-dialog-overlay')) return true;
      const t = document.body ? (document.body.innerText || '') : '';
      return t.includes('Support Emailnator') || t.includes('Watch a short ad');
    })()""")
    return bool(r)


def destravar(h):
    """Remove o dialogo. Devolve quantos elementos sairam."""
    try:
        return h.js(EXPR) or 0
    except Exception:
        return 0


def garantir_limpo(h, segundos=20, log=None):
    """Insiste ate o modal nao voltar mais."""
    fim = time.time() + segundos
    total = 0
    while time.time() < fim:
        if not tem_modal(h):
            return True
        n = destravar(h)
        total += n
        if log and n:
            log("modal removido (%d elementos)" % n)
        time.sleep(0.6)
    ok = not tem_modal(h)
    if log and total:
        log("total removido: %d" % total)
    return ok
