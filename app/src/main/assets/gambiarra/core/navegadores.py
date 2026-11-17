"""Detecta navegadores instalados e gerencia os modos de proxy.

Nada aqui altera o farm: so entrega caminho de executavel e a URL de proxy
que o farmer ja sabe usar.
"""
import os
import platform
import random
import shutil

SISTEMA = platform.system().lower()


def _candidatos():
    """(nome, caminho, rotulo) de navegadores que costumam existir."""
    if SISTEMA == "windows":
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        la = os.environ.get("LOCALAPPDATA", "")
        return [
            ("Chrome", os.path.join(pf, r"Google\Chrome\Application\chrome.exe"), "Google Chrome"),
            ("Chrome", os.path.join(pf86, r"Google\Chrome\Application\chrome.exe"), "Google Chrome (x86)"),
            ("Chrome", os.path.join(la, r"Google\Chrome\Application\chrome.exe"), "Google Chrome (usuario)"),
            ("Edge", os.path.join(pf86, r"Microsoft\Edge\Application\msedge.exe"), "Microsoft Edge"),
            ("Edge", os.path.join(pf, r"Microsoft\Edge\Application\msedge.exe"), "Microsoft Edge (x64)"),
            ("Brave", os.path.join(pf, r"BraveSoftware\Brave-Browser\Application\brave.exe"), "Brave"),
            ("Brave", os.path.join(la, r"BraveSoftware\Brave-Browser\Application\brave.exe"), "Brave (usuario)"),
            ("Opera", os.path.join(la, r"Programs\Opera\opera.exe"), "Opera"),
            ("Opera", os.path.join(pf, r"Opera\opera.exe"), "Opera (sistema)"),
            ("Vivaldi", os.path.join(la, r"Vivaldi\Application\vivaldi.exe"), "Vivaldi"),
            ("Vivaldi", os.path.join(pf, r"Vivaldi\Application\vivaldi.exe"), "Vivaldi (sistema)"),
            ("Firefox", os.path.join(pf, r"Mozilla Firefox\firefox.exe"), "Mozilla Firefox"),
            ("Firefox", os.path.join(pf86, r"Mozilla Firefox\firefox.exe"), "Mozilla Firefox (x86)"),
        ]
    if SISTEMA == "darwin":
        return [
            ("Chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "Google Chrome"),
            ("Edge", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "Microsoft Edge"),
            ("Brave", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser", "Brave"),
            ("Firefox", "/Applications/Firefox.app/Contents/MacOS/firefox", "Mozilla Firefox"),
            ("Opera", "/Applications/Opera.app/Contents/MacOS/Opera", "Opera"),
            ("Vivaldi", "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi", "Vivaldi"),
        ]
    return [
        ("Chrome", "/usr/bin/google-chrome", "Google Chrome"),
        ("Chrome", "/usr/bin/google-chrome-stable", "Google Chrome (stable)"),
        ("Chromium", "/usr/bin/chromium", "Chromium"),
        ("Chromium", "/usr/bin/chromium-browser", "Chromium"),
        ("Edge", "/usr/bin/microsoft-edge", "Microsoft Edge"),
        ("Brave", "/usr/bin/brave-browser", "Brave"),
        ("Firefox", "/usr/bin/firefox", "Mozilla Firefox"),
    ]


def detectar():
    """Lista de dicts {tipo, caminho, nome}. Sem duplicatas do mesmo tipo."""
    vistos = set()
    achados = []
    for tipo, caminho, rotulo in _candidatos():
        chave = (tipo, rotulo)
        if chave in vistos:
            continue
        if os.path.exists(caminho):
            vistos.add(chave)
            achados.append({"tipo": tipo, "caminho": caminho, "nome": rotulo})
            continue
        if "/" not in caminho.split("\\")[0] and SISTEMA != "windows":
            real = shutil.which(os.path.basename(caminho))
            if real:
                vistos.add(chave)
                achados.append({"tipo": tipo, "caminho": real, "nome": rotulo})
    # no PATH, busca por nome
    if SISTEMA == "windows":
        for exe, tipo, rotulo in (
            ("chrome.exe", "Chrome", "Google Chrome (PATH)"),
            ("msedge.exe", "Edge", "Microsoft Edge (PATH)"),
            ("brave.exe", "Brave", "Brave (PATH)"),
        ):
            real = shutil.which(exe)
            if real and not any(a["tipo"] == tipo for a in achados):
                achados.append({"tipo": tipo, "caminho": real, "nome": rotulo})
    return achados


def escolhido(conf=None):
    """Navegador que o farm vai usar, ou None para o padrao do sistema."""
    if conf is None:
        import temas
        conf = temas.carregar()
    caminho = conf.get("navegador")
    if caminho and os.path.exists(caminho):
        return caminho
    achados = detectar()
    preferidos = [a for a in achados if a["tipo"] in ("Chrome", "Chromium",
                                                     "Edge", "Brave")]
    if preferidos:
        return preferidos[0]["caminho"]
    return achados[0]["caminho"] if achados else None


def rotulo(caminho, achados=None):
    if not caminho:
        return "automatico (do sistema)"
    for a in (achados if achados is not None else detectar()):
        if a["caminho"].lower() == caminho.lower():
            return a["nome"]
    return os.path.basename(caminho)


# ------------------------------------------------------------------ proxy

MODOS = ("auto", "gerador", "random", "rotativa", "nenhum")

ROTULO_MODO = {
    "auto": "Automatico (proxies free coletados)",
    "gerador": "Gerador Proxy [BETA] (ProxyScrape http + socks4)",
    "random": "Proxy aleatorio (free, um por conta)",
    "rotativa": "Proxy rotativo / premium (sua URL)",
    "nenhum": "Sem proxy (conexao direta - seu IP)",
}


def descrever(conf):
    modo = conf.get("proxy_modo", "auto")
    if modo == "rotativa":
        url = conf.get("proxy_url") or ""
        if not url:
            return "rotativo (sem URL configurada)"
        return "rotativo: " + _esconder(url)
    if modo == "nenhum":
        return "direto (sem proxy)"
    return ROTULO_MODO.get(modo, modo)


def _esconder(url):
    if "@" in url:
        antes, depois = url.split("@", 1)
        return antes.split("://")[0] + "://***@" + depois
    return url


def url_rotativa(conf):
    return (conf.get("proxy_url") or "").strip()


def proxy_para(conf, pool=None):
    """Devolve a URL de proxy a usar, ou None (o farmer aceita None)."""
    modo = conf.get("proxy_modo", "auto")
    if modo == "nenhum":
        return None
    if modo == "rotativa":
        return url_rotativa(conf) or None
    if modo in ("auto", "random"):
        if pool is not None:
            try:
                return pool.take()
            except Exception:
                return None
        return None
    return None


def validar_url(url):
    """Confere o formato de uma URL de proxy."""
    if not url:
        return False, "vazia"
    u = url.strip()
    if not u:
        return False, "vazia"
    if "://" not in u:
        return False, "falta o esquema (http:// ou socks5://)"
    esquema = u.split("://", 1)[0].lower()
    if esquema not in ("http", "https", "socks4", "socks5", "socks5h"):
        return False, "esquema desconhecido: " + esquema
    resto = u.split("://", 1)[1]
    if not resto or " " in resto:
        return False, "endereco incompleto"
    if ":" not in resto.split("@")[-1]:
        return False, "falta a porta (ex: 127.0.0.1:8080)"
    return True, "ok"
