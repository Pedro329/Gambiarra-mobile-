"""Tela do Farm Key.

Fluxo: pede a quantidade, TESTA as keys que ja existem (remove as mortas),
depois gera as novas mostrando progresso ao vivo.

Nada aqui reimplementa o farm: usa farmer.Coletor, que ja existe e funciona.
"""
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import menu_principal as mp
import navegadores
import temas

ESC = "\x1b["


def _p(tema):
    return temas.paleta(tema)


def _cab(titulo, tema, largura, t):
    if tema == temas.INFINITY:
        return [mp._centro(temas.rolar_arco(titulo, t, brilho=1.0), largura - 2)]
    p = _p(tema)
    return [mp._centro(p["brilho"] + temas.BOLD + titulo + temas.RESET,
                       largura - 2)]


def _caixa(corpo, tema, largura, t):
    if tema == temas.INFINITY:
        return mp.moldura_infinity(corpo, largura, t)
    return mp.moldura_legacy(corpo, largura)


def _mostrar(corpo, tema, largura, t, cols):
    caixa = _caixa(corpo, tema, largura, t)
    saida = [""]
    for l in caixa:
        saida.append(mp._centro(l, cols))
    return saida


def _rodape(tema, largura, t, dica):
    p = _p(tema)
    if tema == temas.INFINITY:
        return " " + temas.pintar_arco(dica, t * 0.2, brilho=0.72)
    return " " + p["fraco"] + dica + temas.RESET


# ---------------------------------------------------------------- pedir qtd

def _pedir_quantidade(app, cols, rows):
    tema = app.tema
    buffer = "5"
    mp.drenar()
    sys.stdout.write(ESC + "?25l")
    try:
        while True:
            c, r = mp.tamanho()
            t = time.time() - app.t0
            largura = max(50, min(c - 1, 84))
            p = _p(tema)
            corpo = [""]
            corpo.extend(_cab("FARM KEY", tema, largura, t))
            corpo.append("")
            corpo.append("  " + p["texto"] + temas.BOLD
                         + "quantas keys voce quer gerar?" + temas.RESET)
            corpo.append("")
            cursor = "_" if int(time.time() * 2) % 2 == 0 else " "
            destaque = (temas.rgb(80, 60, 180, fundo=True)
                        if tema == temas.INFINITY
                        else p["fundo_destaque"])
            corpo.append("  " + destaque + temas.BOLD
                         + "   " + (buffer or "0") + cursor + "   "
                         + temas.RESET)
            corpo.append("")
            corpo.append("  " + p["fraco"]
                         + "digite o numero, enter confirma, esc volta"
                         + temas.RESET)
            corpo.append("")
            corpo.append(_rodape(tema, largura, t, "enter comeca   esc volta"))
            mp.desenhar(_mostrar(corpo, tema, largura, t, c), c, r)

            tecla = mp.le_tecla(0.1)
            if tecla is None:
                continue
            if tecla in ("esc", "backspace") and not buffer:
                return None
            if tecla == "esc":
                return None
            if tecla == "backspace":
                buffer = buffer[:-1]
            elif tecla == "enter":
                if buffer and int(buffer) > 0:
                    return min(999, int(buffer))
                return None
            elif len(tecla) == 1 and tecla.isdigit():
                if len(buffer) < 4:
                    buffer = (buffer + tecla).lstrip("0") or ""
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h")
        sys.stdout.flush()


# ------------------------------------------------------------------- farm

class Trabalho:

    def __init__(self, quantas, conf):
        self.quantas = quantas
        self.conf = conf
        self.parar = False
        self.estado = "iniciando"
        self.feitas = 0
        self.falhas = 0
        self.testadas = 0
        self.mortas = 0
        self.total_keys = 0
        self.log = []
        self.ultima = ""
        self.t0 = time.time()
        self.trava = threading.Lock()
        self.thread = threading.Thread(target=self._rodar, daemon=True)

    def anotar(self, texto, tipo="info"):
        with self.trava:
            self.log.append((tipo, texto))
            del self.log[:-9]

    def _rodar(self):
        try:
            import farmer
            import farmer_panel
        except Exception as exc:
            self.estado = "erro"
            self.anotar("nao consegui carregar o farmer: %s" % str(exc)[:60], "erro")
            return

        try:
            store = farmer.KeyStore(farmer_panel.KEYS_FILE)
            self.total_keys = store.count()
        except Exception as exc:
            self.estado = "erro"
            self.anotar("keys.json ilegivel: %s" % str(exc)[:60], "erro")
            return

        # 1. testa as que ja existem
        existentes = [e for e in getattr(store, "items", [])
                      if isinstance(e, dict) and e.get("key")]
        if existentes:
            self.estado = "testando"
            self.anotar("testando %d key(s) que ja tenho..." % len(existentes))
            mortas = []
            for i, entry in enumerate(existentes):
                if self.parar:
                    break
                chave = entry.get("key")
                try:
                    st, _ = farmer.probe_api(chave, timeout=12)
                except Exception:
                    st = 0
                with self.trava:
                    self.testadas += 1
                if st != 200:
                    mortas.append(chave)
            if mortas:
                ruins = set(mortas)
                try:
                    store.items = [e for e in store.items
                                   if e.get("key") not in ruins]
                    store.flush()
                except Exception:
                    pass
                with self.trava:
                    self.mortas = len(mortas)
                self.anotar("%d key(s) morta(s) removida(s)" % len(mortas), "erro")
                self.total_keys = store.count()
            else:
                self.anotar("todas as %d keys respondem" % len(existentes), "ok")

        if self.parar:
            self.estado = "parado"
            return

        # 2. gera as novas
        self.estado = "gerando"
        self.t0 = time.time()

        # ---- prepara as proxies conforme o modo escolhido ----
        modo = self.conf.get("proxy_modo", "auto")
        pool = self._montar_pool(modo)
        if modo == "nenhum":
            self.anotar("sem proxy: conexao direta (sujeito a 429)")
        elif not pool:
            self.anotar("nenhuma proxy funcional: seguindo direto", "erro")
        else:
            self.anotar("%d proxies prontas (modo %s)" % (len(pool), modo), "ok")

        proxies_usadas = set()
        for n in range(1, self.quantas + 1):
            if self.parar:
                break
            self.ultima = "conta %d de %d" % (n, self.quantas)

            record = None
            err = ""
            # ate 3 tentativas, trocando de proxy a cada 429/limite
            for tent in range(1, 4):
                if self.parar:
                    break
                proxy = self._pegar_proxy(modo, pool, proxies_usadas)
                try:
                    record, err = farmer.harvest_one(n, proxy=proxy)
                except Exception as exc:
                    record, err = None, str(exc)[:80]
                if record and record.get("key"):
                    break
                # 429 / limite / conexao ruim -> troca de proxy e tenta de novo
                baixo = (err or "").lower()
                limite = ("429" in baixo or "too many" in baixo
                          or "too many requests" in baixo)
                proxy_ruim = ("conexao" in baixo or "proxy" in baixo
                              or "timeout" in baixo or "urlopen" in baixo)
                if pool and proxy and (limite or proxy_ruim) and tent < 3:
                    if proxy_ruim:
                        # descarta a proxy morta para nao perder outra conta
                        try:
                            pool.remove(proxy)
                        except ValueError:
                            pass
                        self.anotar("proxy morta, descartada (%d restam)"
                                    % len(pool), "erro")
                    else:
                        self.anotar("limite no proxy %s, trocando..."
                                    % proxy[:24], "erro")
                    time.sleep(1.5)
                    continue
                break

            if record and record.get("key"):
                try:
                    store.add(record)
                except Exception:
                    pass
                with self.trava:
                    self.feitas += 1
                via = (" via " + record.get("proxy", "")[:20]
                       if record.get("proxy") else " direto")
                self.anotar("%s  %s...%s" % (record.get("user", "?"),
                                             record["key"][:18], via), "ok")
            else:
                with self.trava:
                    self.falhas += 1
                self.anotar("falhou: %s" % (err or "sem resposta"), "erro")
            try:
                self.total_keys = store.count()
            except Exception:
                pass

        self.estado = "pronto" if not self.parar else "parado"

    # ---------------------------------------------------------------- proxy
    def _montar_pool(self, modo):
        """Coleta e valida proxies conforme o modo.

        auto     -> lista pronta do cache; se vazia, coleta agora
        random   -> mesma coisa (a escolha ja e aleatoria por conta)
        rotativa -> usa a URL que o usuario configurou
        nenhum   -> nada
        """
        if modo == "nenhum":
            return []
        if modo == "rotativa":
            url = (self.conf.get("proxy_url") or "").strip()
            return [url] if url else []
        try:
            import proxies
        except Exception:
            return []
        self.anotar("coletando e validando proxies...")
        try:
            lista = proxies.prontas(target=8)
        except Exception:
            lista = []
        if not lista:
            try:
                lista = [p for p, _ in proxies.load()]
            except Exception:
                lista = []
            self.anotar("nenhuma proxy validou: usando o cache", "erro")
        if modo == "random":
            import random as _r
            _r.shuffle(lista)
        return lista

    def _pegar_proxy(self, modo, pool, usadas):
        """Escolhe a proxy da vez. Evita repetir enquanto houver opcao."""
        if modo == "nenhum" or not pool:
            return None
        if modo == "rotativa":
            return pool[0]
        livres = [p for p in pool if p not in usadas]
        if not livres:
            usadas.clear()
            livres = list(pool)
        escolhida = livres[0]
        usadas.add(escolhida)
        return escolhida

    def iniciar(self):
        self.thread.start()

    def instantaneo(self):
        with self.trava:
            return {
                "estado": self.estado,
                "feitas": self.feitas,
                "falhas": self.falhas,
                "testadas": self.testadas,
                "mortas": self.mortas,
                "total": self.total_keys,
                "log": list(self.log),
                "ultima": self.ultima,
                "segundos": time.time() - self.t0,
            }


def _tela_progresso(app, trabalho, cols, rows):
    tema = app.tema
    mp.drenar()
    sys.stdout.write(ESC + "?25l")
    try:
        while True:
            c, r = mp.tamanho()
            t = time.time() - app.t0
            largura = max(50, min(c - 1, 96))
            p = _p(tema)
            snap = trabalho.instantaneo()

            corpo = [""]
            corpo.extend(_cab("FARM KEY", tema, largura, t))
            corpo.append("")

            if snap["estado"] == "testando":
                frac = (snap["testadas"] / float(max(1, snap["testadas"] + 3)))
                corpo.append("  " + p["texto"] + "testando keys existentes"
                             + temas.RESET)
                corpo.append("")
                corpo.append("  " + temas.barra(0.5, 40, tema, t) + "  "
                             + p["texto2"] + "%d testada(s)" % snap["testadas"]
                             + temas.RESET)
            else:
                frac = (snap["feitas"] + snap["falhas"]) / float(max(1, trabalho.quantas))
                corpo.append("  " + temas.barra(frac, 42, tema, t) + "   "
                             + p["texto"] + "%d/%d" % (snap["feitas"], trabalho.quantas)
                             + temas.RESET)
                corpo.append("")
                ok_txt = p["ok"] + "%d ok" % snap["feitas"] + temas.RESET
                er_txt = (p["erro"] + "%d falha(s)" % snap["falhas"] + temas.RESET)
                corpo.append("  " + ok_txt + p["fraco"] + "   " + temas.RESET
                             + er_txt + p["fraco"] + "   total "
                             + str(snap["total"]) + temas.RESET)
                if snap["mortas"]:
                    corpo.append("  " + p["alerta"]
                                 + "%d key(s) morta(s) removida(s)" % snap["mortas"]
                                 + temas.RESET)

            corpo.append("")
            if snap["ultima"] and snap["estado"] == "gerando":
                spin = temas.spinner(int(t * 10), tema)
                corpo.append("  " + p["brilho"] + spin + temas.RESET + " "
                             + p["texto2"] + snap["ultima"] + temas.RESET)
            else:
                corpo.append("")

            corpo.append("")
            for tipo, texto in snap["log"][-5:]:
                cor = {"ok": p["ok"], "erro": p["erro"]}.get(tipo, p["fraco"])
                sim = {"ok": "+", "erro": "x"}.get(tipo, ".")
                corpo.append("  " + cor + sim + " " + temas.RESET
                             + p["fraco"] + texto[:74] + temas.RESET)
            for _ in range(5 - min(5, len(snap["log"]))):
                corpo.append("")
            corpo.append("")
            if snap["estado"] in ("pronto", "parado", "erro"):
                corpo.append(_rodape(tema, largura, t, "enter ou esc para voltar"))
            else:
                corpo.append(_rodape(tema, largura, t,
                                     "esc interrompe (o que ja saiu fica salvo)"))
            mp.desenhar(_mostrar(corpo, tema, largura, t, c), c, r)

            tecla = mp.le_tecla(0.12)
            if tecla is None:
                continue
            if tecla == "esc":
                trabalho.parar = True
                if snap["estado"] in ("pronto", "parado", "erro"):
                    return snap
                continue
            if tecla == "enter" and snap["estado"] in ("pronto", "parado", "erro"):
                return snap
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h")
        sys.stdout.flush()


def abrir(app, cols=None, rows=None):
    """Fluxo completo do Farm Key."""
    quantas = _pedir_quantidade(app, cols, rows)
    if not quantas:
        return
    conf = temas.carregar()
    trabalho = Trabalho(quantas, conf)
    trabalho.iniciar()
    snap = _tela_progresso(app, trabalho, cols, rows)
    trabalho.parar = True
    try:
        trabalho.thread.join(3)
    except Exception:
        pass
    if snap:
        app.aviso("%d nova(s), %d no total" % (snap["feitas"], snap["total"]), 5)
