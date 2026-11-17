"""Valida proxies pelo unico criterio que importa:

o widget do Cloudflare APARECE na pagina de sign-up?

Proxy ruim -> o Turnstile nao renderiza (nenhum iframe/frame), e o
captcha que o usuario precisa clicar nunca existe. Testar por HTTP
nao revela isso (a pagina volta 200 do mesmo jeito).

Exporta:
    validar(proxy)          -> True se o captcha aparece
    achar_bons(quantos)     -> lista de proxies aprovados no criterio
"""
import time

import humano

URL = "https://routerplex.com/sign-up"

# checagem no DOM: o Turnstile renderizado tem frame do Cloudflare
# e/ou o container .cf-turnstile com tamanho real
EXPR_CAPTCHA = """
(function() {
  const frames = [...document.querySelectorAll(
    'iframe[src*="challenges.cloudflare"], iframe[title*="loudflare"],' +
    ' iframe[title*="ecaptcha"], div.cf-turnstile iframe, #cf-chl-widget')];
  const div = document.querySelector('div.cf-turnstile, .cf-turnstile');
  const visivel = frames.some(f => {
    const r = f.getBoundingClientRect();
    return r.width > 10 && r.height > 10;
  });
  const turnstileObj = typeof window.turnstile;
  // o script do cloudflare carregou?
  const scriptCf = [...document.querySelectorAll('script[src]')]
    .some(s => /challenges\\.cloudflare\\.com/.test(s.src));
  // desafio de pagina inteira (bloqueio)
  const bloqueado = /Just a moment|_cf_chl_opt|Sorry, you have been blocked/
    .test(document.documentElement.innerHTML);
  return JSON.stringify({
    frames: frames.length, visivel: visivel,
    turnstile: turnstileObj, script_cf: scriptCf, bloqueado: bloqueado,
    form: !!document.querySelector('button[type=submit]'),
    url: location.href
  });
})()
"""


def validar(proxy, porta=9700, espera=22, log=None):
    """Abre o Chrome com o proxy e ve se o captcha renderiza."""
    h = None
    try:
        h = humano.abrir(porta=porta, perfil=None, proxy=proxy)
        h.ir(URL, esperar=3.0)
        fim = time.time() + espera
        while time.time() < fim:
            r = h.js(EXPR_CAPTCHA)
            if not r:
                time.sleep(1.0)
                continue
            import json as _j
            d = _j.loads(r)
            if d.get("bloqueado"):
                if log:
                    log("bloqueado pelo cloudflare")
                return False
            if d.get("visivel"):
                if log:
                    log("CAPTCHA OK (frames=%d turnstile=%s)"
                        % (d["frames"], d["turnstile"]))
                return True
            time.sleep(1.2)
        if log:
            log("captcha NAO renderizou")
        return False
    except Exception as e:
        if log:
            log("erro: %s" % str(e)[:50])
        return False
    finally:
        if h:
            try:
                h.fechar()
            except Exception:
                pass


def achar_bons(quantos=1, maximo_tentativas=12, candidatos=None):
    """Testa proxies ate achar `quantos` em que o captcha aparece."""
    import proxies_duplos

    if candidatos is None:
        print("  coletando candidatos (precisa abrir nos dois sites)...")
        candidatos = proxies_duplos.bons(maximo_tentativas)
    if not candidatos:
        return []

    aprovados = []
    for i, p in enumerate(candidatos[:maximo_tentativas], 1):
        url = "http://" + p
        print("  [%d] testando %s" % (i, p))
        ok = validar(url, porta=9700 + i,
                     log=lambda m: print("       " + m))
        if ok:
            aprovados.append(p)
            print("       >>> APROVADO")
            if len(aprovados) >= quantos:
                break
        else:
            print("       >>> reprovado")
    return aprovados


if __name__ == "__main__":
    import sys
    q = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    r = achar_bons(q)
    print()
    print("APROVADOS (%d):" % len(r))
    for p in r:
        print("  ", p)
