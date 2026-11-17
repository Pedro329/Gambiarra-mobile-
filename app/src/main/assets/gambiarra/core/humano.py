"""Comportamento humano via CDP (Chrome DevTools Protocol).

Sem dependencias: WebSocket na mao, eventos de mouse/teclado reais.

  Human(headless=False)  abre o Chrome com um perfil
  .ir(url)               navega e espera carregar
  .mexer(destino)        move o mouse em curva de bezier, com tremor
  .rolar(px)             scroll suave com pausas
  .digitar(texto)        digitacao com ritmo irregular
  .clicar(seletor)       leva o mouse ate o elemento e clica
  .esperar_turnstile()   aguarda cf_clearance / token
  .cookies()             le os cookies
  .fechar()

As curvas usam bezier cubica com jitter: o Cloudflare olha se o mouse
anda em linha reta perfeita, que nenhuma pessoa faz.
"""
import json
import math
import os
import random
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request

CHROME_PADRAO = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

FLAGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--disable-ipc-flooding-protection",
    # impede o Chrome de congelar a aba: sem isso o React nao monta
    # e o widget do Turnstile nunca aparece
    "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling",
    "--disable-hang-monitor",
    "--disable-prompt-on-repost",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-default-apps",
    "--disable-component-update",
    "--force-device-scale-factor=1",
    "--lang=pt-BR",
    "--accept-lang=pt-BR,pt,en-US,en",
    "--window-size=1280,1000",
    "--start-maximized",
]

# blur nativo: sai do "headless" e passa a contar como tela real
BLUR = ("(function(){const c=document.createElement('canvas');"
        "const g=c.getContext('webgl')||c.getContext('experimental-webgl');"
        "if(!g)return 'sem-webgl';return 'webgl-ok';})()")


def achar_chrome():
    for p in CHROME_PADRAO:
        if os.path.exists(p):
            return p
    raise RuntimeError("Chrome/Edge nao encontrado")


# ------------------------------------------------------------------ websocket

class WS:
    """WebSocket cliente minimo."""

    def __init__(self, url, timeout=25):
        resto = url[5:] if url.startswith("ws://") else url
        host_porta, _, caminho = resto.partition("/")
        host, _, porta = host_porta.partition(":")
        self.s = socket.create_connection((host, int(porta)), timeout=timeout)
        chave = "dGhlIHNhbXBsZSBub25jZQ=="
        self.s.sendall(("GET /%s HTTP/1.1\r\nHost: %s:%s\r\n"
                        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                        "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n"
                        "\r\n" % (caminho, host, porta, chave)).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            d = self.s.recv(4096)
            if not d:
                raise IOError("handshake falhou")
            buf += d

    def enviar(self, texto):
        dados = texto.encode()
        mascara = os.urandom(4)
        cab = bytearray([0x81])
        n = len(dados)
        if n < 126:
            cab.append(0x80 | n)
        elif n < 65536:
            cab.append(0x80 | 126)
            cab += struct.pack(">H", n)
        else:
            cab.append(0x80 | 127)
            cab += struct.pack(">Q", n)
        cab += mascara
        self.s.sendall(bytes(cab) + bytes(b ^ mascara[i % 4]
                                          for i, b in enumerate(dados)))

    def receber(self):
        cab = self.s.recv(2)
        if len(cab) < 2:
            return None
        n = cab[1] & 0x7F
        if n == 126:
            n = struct.unpack(">H", self.s.recv(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self.s.recv(8))[0]
        dados = b""
        while len(dados) < n:
            d = self.s.recv(n - len(dados))
            if not d:
                break
            dados += d
        return dados.decode("utf-8", "replace")

    def fechar(self):
        try:
            self.s.close()
        except Exception:
            pass


# ---------------------------------------------------------------------- human

def _separar_auth(proxy):
    """("host:porta", ("user","pass")) a partir de uma URL de proxy.

    O Chrome nao aceita credenciais em --proxy-server. Sem separar, a URL
    inteira era passada e o Chrome simplesmente ignorava o proxy.
    """
    if not proxy:
        return "", None
    p = proxy.strip()
    auth = None
    if "@" in p:
        esq, dir_ = p.rsplit("@", 1)
        if "://" in esq:
            esq = esq.split("://", 1)[1]
        if ":" in esq:
            user, _, senha = esq.partition(":")
            auth = (user, senha)
        elif esq:
            auth = (esq, "")
        p = dir_
    return p, auth


class Human:

    def __init__(self, porta=9444, headless=False, perfil=None, proxy=None,
                 largura=1366, altura=820):
        self.porta = porta
        self.largura = largura
        self.altura = altura
        self.perfil = perfil or tempfile.mkdtemp(prefix="nrprof_")
        self._novo = perfil is None
        self.proc = None
        self.ws = None
        self._id = 0
        self._url_atual = ""
        self.mx = largura // 2
        self.my = altura // 2
        self.proxy_auth = None

        args = [achar_chrome(), "--remote-debugging-port=%d" % porta,
                "--user-data-dir=" + self.perfil] + FLAGS
        if headless:
            args.append("--headless=new")
        if proxy:
            # --proxy-server NAO aceita "user:pass@host:porta": o Chrome
            # recebia uma URL invalida, ignorava o proxy e saia pelo IP
            # direto — por isso o proxy premium "nao funcionava". Aqui as
            # credenciais sao separadas e o handshake e respondido no CDP.
            servidor, self.proxy_auth = _separar_auth(proxy)
            if servidor:
                args.append("--proxy-server=" + servidor)
        args.append("about:blank")
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)

    # ---------------------------------------------------------------- infra

    def _esperar_devtools(self, timeout=30):
        fim = time.time() + timeout
        while time.time() < fim:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/json/version" % self.porta,
                        timeout=2) as r:
                    return json.loads(r.read().decode())
            except Exception:
                if self.proc and self.proc.poll() is not None:
                    return None
                time.sleep(0.3)
        return None

    def _conectar(self):
        if self.ws:
            return
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/json/list" % self.porta, timeout=6) as r:
            abas = json.loads(r.read().decode())
        alvo = None
        for a in abas:
            if a.get("type") == "page":
                alvo = a
                break
        if not alvo:
            raise RuntimeError("sem aba")
        self.ws = WS(alvo["webSocketDebuggerUrl"])

    # ------------------------------------------------------------ abas

    def _listar_abas(self):
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/json/list" % self.porta, timeout=6) as r:
            abas = json.loads(r.read().decode())
        return [a for a in abas if a.get("type") == "page"]

    def nova_aba(self, url="about:blank", mesma_janela=True):
        """Abre uma aba nova e devolve o alvo.

        Sem `newWindow`, o Target.createTarget abre a aba na MESMA
        janela do Chrome. Com newWindow=true ele faz uma janela nova,
        e o usuario perde a visao das duas abas lado a lado.
        """
        params = {"url": url}
        if not mesma_janela:
            params["newWindow"] = True
        self.cdp("Target.createTarget", params)
        for _ in range(30):
            abas = self._listar_abas()
            for a in abas:
                if url != "about:blank" and url in (a.get("url") or ""):
                    return a
            time.sleep(0.3)
        abas = self._listar_abas()
        return abas[-1] if abas else None

    def janela_da_aba(self, indice):
        """Descobre em qual janela/aba o alvo esta."""
        abas = self._listar_abas()
        if indice < 0 or indice >= len(abas):
            return None
        alvo = abas[indice]
        r = self.cdp("Browser.getWindowForTarget",
                     {"targetId": alvo["id"]})
        return r

    def usar_aba(self, indice):
        """Conecta a uma aba pela posicao (0 = primeira)."""
        abas = self._listar_abas()
        if indice < 0 or indice >= len(abas):
            return False
        if self.ws:
            self.ws.fechar()
        self.ws = WS(abas[indice]["webSocketDebuggerUrl"])
        self._id = 0
        return True

    def abas(self):
        """Lista (indice, titulo, url) das abas abertas."""
        saida = []
        for i, a in enumerate(self._listar_abas()):
            saida.append((i, a.get("title", ""), a.get("url", "")))
        return saida

    def fechar_aba(self, indice):
        abas = self._listar_abas()
        if indice < 0 or indice >= len(abas):
            return False
        self.cdp("Target.closeTarget", {"targetId": abas[indice]["id"]})
        return True

    def cdp(self, metodo, params=None, espera=45):
        """Chama um metodo do CDP e devolve o resultado."""
        self._conectar()
        self._id += 1
        meu = self._id
        self.ws.enviar(json.dumps({"id": meu, "method": metodo,
                                   "params": params or {}}))
        self.ws.s.settimeout(espera)
        fim = time.time() + espera
        while time.time() < fim:
            try:
                msg = self.ws.receber()
            except socket.timeout:
                return None
            if not msg:
                return None
            try:
                d = json.loads(msg)
            except Exception:
                continue
            if d.get("id") == meu:
                if "error" in d:
                    return {"__erro": d["error"]}
                return d.get("result")
        return None

    def js(self, expr, espera=45):
        """Avalia JS e devolve o valor."""
        r = self.cdp("Runtime.evaluate", {
            "expression": expr, "awaitPromise": True, "returnByValue": True,
            "userGesture": True}, espera=espera)
        if not r or "__erro" in r:
            return None
        return r.get("result", {}).get("value")

    # -------------------------------------------------------------- mouse

    def _mover(self, x, y, passos=1):
        self.cdp("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": x, "y": y, "buttons": 0,
            "pointerType": "mouse"})

    def _bezier(self, x0, y0, x1, y1, passos=None):
        """Curva cubica com pontos de controle aleatorios."""
        dist = math.hypot(x1 - x0, y1 - y0)
        if passos is None:
            passos = max(8, min(45, int(dist / 18) + 8))
        # controles puxam para os lados, como a mao faz
        c1x = x0 + (x1 - x0) * random.uniform(0.15, 0.45) + random.uniform(-70, 70)
        c1y = y0 + (y1 - y0) * random.uniform(0.05, 0.35) + random.uniform(-55, 55)
        c2x = x0 + (x1 - x0) * random.uniform(0.55, 0.9) + random.uniform(-70, 70)
        c2y = y0 + (y1 - y0) * random.uniform(0.65, 0.95) + random.uniform(-55, 55)
        pontos = []
        for i in range(passos + 1):
            t = i / passos
            # ease-in-out: comeca e termina devagar
            tt = t * t * (3 - 2 * t)
            u = 1 - tt
            x = (u ** 3 * x0 + 3 * u ** 2 * tt * c1x
                 + 3 * u * tt ** 2 * c2x + tt ** 3 * x1)
            y = (u ** 3 * y0 + 3 * u ** 2 * tt * c1y
                 + 3 * u * tt ** 2 * c2y + tt ** 3 * y1)
            # tremor de mao
            x += random.uniform(-1.4, 1.4)
            y += random.uniform(-1.4, 1.4)
            pontos.append((x, y))
        return pontos

    def mexer(self, x, y, passos=None):
        """Move o mouse em curva humana, com pausas no meio."""
        pontos = self._bezier(self.mx, self.my, x, y, passos)
        for i, (px, py) in enumerate(pontos):
            self._mover(px, py)
            # nem todo passo tem o mesmo tempo: as vezes a mao trava
            atraso = random.uniform(0.004, 0.016)
            if random.random() < 0.06:
                atraso += random.uniform(0.04, 0.12)
            if random.random() < 0.02:
                # micro-correcao: volta um pouco
                self._mover(px + random.uniform(-3, 3),
                            py + random.uniform(-3, 3))
            time.sleep(atraso)
        self.mx, self.my = x, y

    def passear(self, n=None, area=None):
        """Movimentos soltos pela tela, como quem esta lendo."""
        n = n or random.randint(3, 7)
        x0, y0, x1, y1 = area or (40, 80, self.largura - 40, self.altura - 40)
        for _ in range(n):
            self.mexer(random.uniform(x0, x1), random.uniform(y0, y1))
            time.sleep(random.uniform(0.08, 0.5))

    def clicar(self, seletor=None, x=None, y=None):
        """Vai ate o elemento e clica como uma pessoa."""
        if seletor:
            caixa = self.js("""(function(){
              const e=document.querySelector(%s);
              if(!e) return null;
              e.scrollIntoView({block:'center'});
              const r=e.getBoundingClientRect();
              return [r.x+r.width/2, r.y+r.height/2];
            })()""" % json.dumps(seletor))
            if not caixa:
                return False
            x, y = caixa[0], caixa[1]
            time.sleep(random.uniform(0.15, 0.5))
        self.mexer(x, y)
        time.sleep(random.uniform(0.05, 0.18))
        # as vezes erra e corrige
        if random.random() < 0.22:
            self._mover(x + random.uniform(-2.5, 2.5),
                        y + random.uniform(-2.5, 2.5))
            time.sleep(random.uniform(0.03, 0.09))
        for tipo, campos in (
                ("mousePressed", {"button": "left", "clickCount": 1,
                                  "buttons": 1}),
                ("mouseReleased", {"button": "left", "clickCount": 1,
                                   "buttons": 0})):
            corpo = {"type": tipo, "x": x, "y": y, "pointerType": "mouse"}
            corpo.update(campos)
            self.cdp("Input.dispatchMouseEvent", corpo)
            time.sleep(random.uniform(0.05, 0.13))
        return True

    # -------------------------------------------------------------- teclado

    def digitar(self, texto, alvo=None):
        """Digita com ritmo irregular: rapido no meio, lento nas bordas."""
        if alvo:
            self.clicar(alvo)
            time.sleep(random.uniform(0.2, 0.5))
        for i, ch in enumerate(texto):
            self.cdp("Input.dispatchKeyEvent", {"type": "keyDown",
                                                "text": ch})
            self.cdp("Input.dispatchKeyEvent", {"type": "keyUp"})
            base = random.uniform(0.045, 0.16)
            if i == 0:
                base += random.uniform(0.15, 0.4)   # pensa antes
            if random.random() < 0.09:
                base += random.uniform(0.3, 0.9)    # distracao
            if ch in "._-@":
                base += random.uniform(0.05, 0.22)
            time.sleep(base)
            if random.random() < 0.03:
                # corrige: apaga uma letra e digita de novo
                self.cdp("Input.dispatchKeyEvent",
                         {"type": "rawKeyDown", "windowsVirtualKeyCode": 8,
                          "nativeVirtualKeyCode": 8})
                self.cdp("Input.dispatchKeyEvent",
                         {"type": "keyUp", "windowsVirtualKeyCode": 8,
                          "nativeVirtualKeyCode": 8})
                time.sleep(random.uniform(0.1, 0.3))
                self.cdp("Input.dispatchKeyEvent", {"type": "keyDown",
                                                    "text": ch})
                self.cdp("Input.dispatchKeyEvent", {"type": "keyUp"})
                time.sleep(random.uniform(0.06, 0.18))

    # --------------------------------------------------------------- scroll

    def rolar(self, total, pausas=True):
        """Scroll com roda do mouse, em passos irregulares."""
        feito = 0
        sinal = 1 if total > 0 else -1
        alvo = abs(total)
        while feito < alvo:
            passo = random.randint(60, 190)
            if feito + passo > alvo:
                passo = alvo - feito
            self.cdp("Input.dispatchMouseEvent", {
                "type": "mouseWheel", "x": self.mx, "y": self.my,
                "deltaX": 0, "deltaY": passo * sinal * -1,
                "pointerType": "mouse"})
            feito += passo
            time.sleep(random.uniform(0.05, 0.22))
            if pausas and random.random() < 0.25:
                time.sleep(random.uniform(0.4, 1.4))
                if random.random() < 0.4:
                    self.passear(random.randint(1, 3))

    # ------------------------------------------------------------ navegacao

    def ir(self, url, esperar=2.5):
        """Navega com Referer plausivel quando ha historico."""
        self.cdp("Page.enable")
        self.cdp("Page.navigate", {"url": url})
        self._url_atual = url
        time.sleep(esperar)
        for _ in range(45):
            estado = self.js("document.readyState")
            if estado in ("interactive", "complete"):
                break
            time.sleep(0.3)
        return True

    def cookies(self):
        r = self.cdp("Network.getCookies", {})
        if not r:
            return {}
        return {c["name"]: c["value"] for c in r.get("cookies", [])}

    def tem_clearance(self):
        return "cf_clearance" in self.cookies()

    def token_turnstile(self):
        return self.js("(document.querySelector('[name=\"cf-turnstile-response\"]')"
                       "||{}).value") or ""

    def esperar_turnstile(self, segundos=45, log=None):
        """Espera o token do Turnstile aparecer. Devolve o token."""
        fim = time.time() + segundos
        tentou = False
        while time.time() < fim:
            token = self.token_turnstile()
            if token:
                return token
            if not tentou and time.time() > fim - segundos + 12:
                # tenta clicar no checkbox, como uma pessoa faria
                tentou = True
                if log:
                    log("clicando no turnstile")
                self.clicar("input[type=checkbox][aria-label]") or \
                    self.clicar("div[class*=turnstile]")
            self.passear(random.randint(1, 2))
            time.sleep(random.uniform(0.8, 1.8))
        return ""

    def aquecer(self, url, segundos=20):
        """Navega, mexe, rola e fica um tempo: cria historico na sessao."""
        self.ir(url)
        time.sleep(random.uniform(1.5, 3.5))
        self.passear()
        self.rolar(random.choice([150, 260, 380]), pausas=True)
        time.sleep(random.uniform(0.8, 2.0))
        self.rolar(random.choice([-120, -200]), pausas=True)
        self.passear()
        time.sleep(random.uniform(0.5, 1.5))
        return True

    def fechar(self):
        try:
            if self.ws:
                self.ws.fechar()
        except Exception:
            pass
        try:
            if self.proc:
                self.proc.terminate()
                self.proc.wait(timeout=8)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        if self._novo:
            time.sleep(0.4)
            shutil.rmtree(self.perfil, ignore_errors=True)

    # ------------------------------------------------------ janela/aba viva

    def trazer_para_frente(self):
        """Traz a janela do Chrome para frente.

        O Windows bloqueia SetForegroundWindow vindo de processo em
        segundo plano; o truque do Alt libera o lock.
        """
        try:
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32
            u.keybd_event(0x12, 0, 0, 0)      # Alt down
            u.keybd_event(0x12, 0, 2, 0)      # Alt up
            time.sleep(0.05)
            hwnd = u.GetForegroundWindow()
            # acha a janela do nosso chrome
            pid = self.proc.pid if self.proc else 0
            alvo = []

            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                wintypes.LPARAM)
            def cb(h_, _):
                p = wintypes.DWORD()
                u.GetWindowThreadProcessId(h_, ctypes.byref(p))
                if p.value == pid and u.IsWindowVisible(h_):
                    alvo.append(h_)
                return True

            u.EnumWindows(cb, 0)
            if alvo:
                u.ShowWindow(alvo[0], 9)       # SW_RESTORE
                u.SetForegroundWindow(alvo[0])
                u.BringWindowToTop(alvo[0])
                return True
            return False
        except Exception:
            return False

    def manter_viva(self):
        """Garante que a aba nao esteja congelada/oculta."""
        try:
            self.cdp("Page.setWebLifecycleState", {"state": "active"})
        except Exception:
            pass
        try:
            self.cdp("Emulation.setFocusEmulationEnabled", {"enabled": True})
        except Exception:
            pass
        try:
            self.cdp("Emulation.setAutoDarkModeOverride", {"enabled": False})
        except Exception:
            pass

    def esperar_react(self, seletor, limite=50, log=None):
        """Espera o React montar de verdade.

        Detecta pelo proprio componente: espera o seletor aparecer E o
        bundle do Next carregar. Sem isso o Turnstile nunca e criado.
        """
        fim = time.time() + limite
        ultimo = ""
        while time.time() < fim:
            r = self.js("""JSON.stringify({
              alvo: !!document.querySelector(%s),
              ts: typeof window.turnstile,
              ifr: document.querySelectorAll('iframe').length,
              scripts: document.querySelectorAll('script[src]').length})
            """ % json.dumps(seletor))
            if r:
                ultimo = r
                d = json.loads(r)
                if d.get("alvo") and d.get("ts") != "undefined":
                    return True, r
            self.manter_viva()
            time.sleep(0.8)
        return False, ultimo


# ---------------------------------------------------------------- utilidades

def abrir(porta=9444, **kw):
    """Cria o Human e espera o Chrome subir. Devolve o Human."""
    h = Human(porta=porta, **kw)
    if not h._esperar_devtools():
        h.fechar()
        raise RuntimeError("chrome nao subiu")
    h._conectar()
    h.manter_viva()
    h.trazer_para_frente()
    return h
