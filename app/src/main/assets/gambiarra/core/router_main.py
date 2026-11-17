import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import farmer
import grpool
import grserver
import models as model_catalog
import tui

BASE_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(BASE_DIR, "dados")
UNCENSORED_MD = os.path.join(HERE, "uncensured.md")
SESSION = os.path.join(DATA_DIR, "session.json")
LOCAL_KEYS = os.path.join(BASE_DIR, "keys.json")
FARM_KEYS = os.path.join(DATA_DIR, "keys.json")
LOCAL_KEY_FILE = os.path.join(BASE_DIR, "gambiarra_key.txt")
ORDER_FILE = os.path.join(BASE_DIR, "model_order.json")
BASE_URL = "http://127.0.0.1:%d/v1" % grserver.PORT
UNLIMITED = "gambiarraapi/modelo-unlimited"
BANNER = [
    "   ____    _    __  __ ____ ___    _    ____  ____       _",
    "  / ___|  / \\  |  \\/  | __ )_ _|  / \\  |  _ \\|  _ \\     / \\",
    " | |  _  / _ \\ | |\\/| |  _ \\| |  / _ \\ | |_) | |_) |   / _ \\",
    " | |_| |/ ___ \\| |  | | |_) | | / ___ \\|  _ <|  _ <   / ___ \\",
    "  \\____/_/   \\_\\_|  |_|____/___/_/   \\_\\_| \\_\\_| \\_\\/_/   \\_\\",
]

def local_key():
    try:
        with open(LOCAL_KEY_FILE, encoding="utf-8") as f:
            value = f.read().strip()
        if value:
            return value
    except OSError:
        pass
    value = "gambiarraapi-local"
    try:
        with open(LOCAL_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(value + "\n")
    except OSError:
        pass
    return value

def load_session():
    try:
        with open(SESSION, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}

def load_keys():
    """Keys do provider ativo.

    Se o provider usa keys proprias (Custom Provider ou fixo na aba
    custom, como o Bike4Mind), carrega as keys DELE (menos as contas ja
    marcadas como sem saldo). Antes isto lia sempre o keys.json do
    Farm/NightRouter, entao mesmo com outro provider configurado o router
    subia com as keys do NightRouter e mandava para la.
    """
    try:
        import providers
        nome = providers.nome_atual()
        proprio = (nome.startswith("custom:")
                   or bool((providers.atual() or {}).get("na_custom")))
        if proprio:
            import custom_modo
            curto = nome.replace("custom:", "")
            rotulo = nome if nome.startswith("custom:") else curto
            vivas = custom_modo.keys_vivas(curto)
            if vivas:
                return vivas, rotulo
            if nome.startswith("custom:"):
                import custom_provider
                prov = custom_provider.por_nome(curto)
                if prov and prov.get("keys"):
                    return list(prov["keys"]), rotulo
            # NAO cai no keys.json do Night: melhor "sem keys" do que
            # mandar requisicao para o provider errado.
            return [], rotulo
    except Exception:
        pass
    for path in (FARM_KEYS, LOCAL_KEYS):
        if os.path.exists(path):
            try:
                keys = farmer.KeyStore(path).keys()
            except Exception:
                keys = []
            if keys:
                return keys, path
    return [], FARM_KEYS

def canonical(models):
    out = []
    for m in models:
        m = m[:-5] if m.endswith("-free") else m + "-free"
        if m not in out:
            out.append(m)
    return out

class App:
    def __init__(self):
        self.term = tui.Term()
        self.shown = None
        self.session = load_session()
        self.keys, self.keys_path = load_keys()
        self.models = []
        self.cursor = 0
        self.scroll = 0
        self.selected = None
        self.routing = True
        self.uncensored = False
        self.local_key = local_key()
        self.server = None
        self.server_error = ""
        self.note = ""
        self.note_at = 0.0
        self.filtering = False
        self.filter = ""

    def load(self):
        key = self.session.get("key")
        self.models = canonical(model_catalog.all_free(key))
        # rele as keys SEMPRE: o provider pode ter mudado desde o __init__
        # (troca no CONFIG, custom adicionado/removido, conta que ficou
        # sem saldo). Antes so trocava `if novas or not self.keys`, entao
        # ao sair do NightRouter para outro provider as keys do Night
        # continuavam carregadas e o router seguia batendo em
        # api.nightrouter.ai mesmo com outro provider escolhido.
        self.keys, self.keys_path = load_keys()
        grpool.POOL.load(self.keys)
        self.selected = self.models[0] if self.models else None
        self.apply()

    def apply(self):
        grserver.State.keys = self.keys
        grserver.State.selected = self.selected
        grserver.State.routing = self.routing
        grserver.State.model_map = {m: m for m in self.models}
        # A cadeia de fallback tem de alcancar TODO o catalogo, nao so os
        # modelos que expomos. Sem isso o TPM do gpt-6-astra nao teria para
        # onde ir: a cadeia fechava nos 6 publicos e o arquivo era reescrito
        # com eles.
        anterior = {}
        try:
            with open(ORDER_FILE, encoding="utf-8") as f:
                lido = json.load(f)
            if isinstance(lido, dict):
                anterior = lido
        except (OSError, ValueError):
            pass

        universo = list(self.models)
        for nome in anterior:
            if nome not in universo:
                universo.append(nome)

        order = {m: grpool.build_chain(universo, m) for m in self.models}
        grpool.ROUTER.routes = order

        # grava as cadeias novas e preserva as entradas que nao expomos
        salvar = {}
        for nome, cadeia in anterior.items():
            if nome not in order:
                salvar[nome] = cadeia
        salvar.update(order)
        try:
            with open(ORDER_FILE, "w", encoding="utf-8") as f:
                json.dump(salvar, f, indent=1)
        except OSError:
            pass

    def start_server(self):
        try:
            self.server = grserver.build()
        except OSError as exc:
            self.server_error = str(exc)
            return False
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return True

    def shout(self, text):
        self.note = text
        self.note_at = time.time()

    def visible(self):
        if not self.filter:
            return list(range(len(self.models)))
        needle = self.filter.lower()
        return [i for i, m in enumerate(self.models) if needle in m.lower()]

    def move(self, delta):
        vis = self.visible()
        if not vis:
            return
        try:
            pos = vis.index(self.cursor)
        except ValueError:
            pos = 0
        self.cursor = vis[(pos + delta) % len(vis)]

    def toggle_uncensored(self):
        self.uncensored = not self.uncensored
        if not self.uncensored:
            grserver.State.system_context = {}
            self.shout("uncensored OFF")
            return
        try:
            with open(UNCENSORED_MD, encoding="utf-8", errors="replace") as f:
                base = f.read()
        except OSError:
            self.uncensored = False
            self.shout("uncensured.md nao encontrado")
            return
        context = {}
        for m in self.models:
            context[m] = base
        for m in model_catalog.uncensored_models():
            if m not in self.models:
                self.models.append(m)
            context[m] = base
        grserver.State.model_map = {m: m for m in self.models}
        grserver.State.system_context = context
        self.apply()
        self.shout("uncensored ON - contexto injetado em %d modelos" % len(context))

    def on_switch(self, model):
        self.shout("trocado para %s" % model)

    def render(self):
        cols_px, rows_px = self.term.size()
        cols, inner = tui.layout(cols_px, rows_px)
        online = self.server is not None
        lines = [tui.box_top(cols, "GAMBIARRA ROUTER", tui.ORANGE_DK),
                 tui.pair(tui.ORANGE + tui.BOLD + "GAMBIARRA ROUTER" + tui.RESET,
                          tui.DIM + farmer.DISCORD + tui.RESET, inner),
                 tui.box_sep(inner),
                 tui.pair(tui.GRAY + "Base URL  " + tui.RESET + tui.WHITE + BASE_URL
                          + tui.RESET,
                          (tui.GREEN + "ONLINE" + tui.RESET) if online
                          else (tui.RED + "OFFLINE" + tui.RESET), inner),
                 tui.pair(tui.GRAY + "API Key   " + tui.RESET + tui.WHITE
                          + self.local_key + tui.RESET,
                          tui.DIM + "%d keys" % len(self.keys) + tui.RESET, inner),
                 tui.pair(tui.GRAY + "Router    " + tui.RESET
                          + (tui.ORANGE + tui.BOLD + "ON" + tui.RESET if self.routing
                             else tui.DIM + "OFF" + tui.RESET)
                          + tui.DIM + "   (se a key estourar, troca de modelo)"
                          + tui.RESET,
                          tui.GRAY + "Uncens " + tui.RESET
                          + (tui.ORANGE + "ON" + tui.RESET if self.uncensored
                             else tui.DIM + "OFF" + tui.RESET), inner),
                 tui.box_sep(inner)]
        title = "MODELOS FREE"
        right = tui.DIM + "%d modelos" % len(self.models) + tui.RESET
        if self.filtering:
            right = (tui.BG_ORANGE + " filtro: " + self.filter
                     + tui.GLYPHS.cursor + " " + tui.RESET)
        lines.append(tui.pair(tui.DIM + title + tui.RESET, right, inner))
        reserved = 6
        height = max(3, rows_px - 1 - len(lines) - reserved)
        vis = self.visible()
        if vis:
            try:
                pos = vis.index(self.cursor)
            except ValueError:
                pos = 0
                self.cursor = vis[0]
            if pos < self.scroll:
                self.scroll = pos
            if pos >= self.scroll + height:
                self.scroll = pos - height + 1
        shown = vis[self.scroll:self.scroll + height] if vis else []
        for i in shown:
            label = self.models[i]
            active = label == self.selected
            here = i == self.cursor
            mark = tui.ORANGE + ">" + tui.RESET if here else " "
            if active and here:
                paint = tui.BG_ORANGE
            elif active:
                paint = tui.ORANGE
            elif here:
                paint = tui.WHITE + tui.BOLD
            else:
                paint = tui.GRAY
            tag = tui.GREEN + "ativo" + tui.RESET if active else ""
            lines.append(tui.pair(mark + " " + paint + label + tui.RESET, tag, inner))
        if not vis:
            lines.append(tui.box_row(tui.RED + "nenhum modelo bate com o filtro"
                                     + tui.RESET, inner))
        if vis:
            pos = vis.index(self.cursor) + 1 if self.cursor in vis else 0
            hidden = len(self.models) - len(shown)
            tail = (tui.DIM + "mostrando %d-%d de %d   cursor %d"
                    % (self.scroll + 1, self.scroll + len(shown), len(vis), pos)
                    + tui.RESET if hidden > 0 else
                    tui.DIM + "cursor %d de %d" % (pos, len(vis)) + tui.RESET)
        else:
            tail = ""
        while len(lines) < rows_px - reserved:
            lines.append(tui.box_row("", inner))
        lines.append(tui.pair(tui.DIM + "   " + tui.RESET, tail, inner))
        lines.append(tui.box_sep(inner))
        lines.append(tui.pair(
            tui.GRAY + "Modelo " + tui.RESET + tui.WHITE
            + (self.selected or "-") + tui.RESET,
            tui.DIM + "alvo de " + tui.RESET + tui.ORANGE + UNLIMITED
            + tui.RESET, inner))
        keys = (tui.WHITE + "setas" + tui.RESET + tui.DIM + " mover  " + tui.RESET
                + tui.WHITE + "ENTER" + tui.RESET + tui.DIM + " usar  " + tui.RESET
                + tui.WHITE + "/" + tui.RESET + tui.DIM + " buscar  " + tui.RESET
                + tui.WHITE + "R" + tui.RESET + tui.DIM + " router  " + tui.RESET
                + tui.WHITE + "U" + tui.RESET + tui.DIM + " uncensored  " + tui.RESET
                + tui.WHITE + "I" + tui.RESET + tui.DIM + " keys  " + tui.RESET
                + tui.WHITE + "Q" + tui.RESET + tui.DIM + " sair" + tui.RESET)
        lines.append(tui.box_row(keys, inner, pad=1))
        lines.append(tui.box_bottom(inner, tui.ORANGE_DK))
        note = ""
        if self.note and time.time() - self.note_at < 5:
            note = self.note
        elif not self.keys:
            note = "sem keys: rode o Farm Key no menu"
        lines.append(tui.ORANGE + "  " + note[: max(10, cols - 4)] + tui.RESET)
        while len(lines) < rows_px - 1:
            lines.append("")
        return tui.screen(lines[: rows_px - 1], cols_px)

    def keys_screen(self):
        cols_px, rows_px = self.term.size()
        cols, inner = tui.layout(cols_px, rows_px)
        entries = grpool.POOL.describe(limit=16)
        lines = [tui.box_top(cols, "KEYS", tui.ORANGE_DK),
                 tui.pair(tui.DIM + "arquivo" + tui.RESET,
                          tui.WHITE + self.keys_path + tui.RESET, inner),
                 tui.pair(tui.DIM + "total " + tui.RESET + tui.WHITE
                          + str(len(self.keys)) + tui.RESET,
                          tui.GREEN + "live %d" % grpool.POOL.live_count()
                          + tui.RESET, inner),
                 tui.box_sep(inner)]
        for idx, state, cooldown, token in entries:
            color = (tui.GREEN if state == "live"
                     else tui.RED if state == "bad" else tui.GRAY)
            lines.append(tui.pair(
                tui.DIM + "#%-3d" % idx + tui.RESET + " " + color + "%-8s" % state
                + tui.RESET + tui.DIM + " %5.1fs" % cooldown + tui.RESET,
                tui.GRAY + token + tui.RESET, inner))
        if not entries:
            lines.append(tui.box_row(tui.DIM + "nenhuma key carregada" + tui.RESET,
                                     inner))
        lines.append(tui.box_sep(inner))
        lines.append(tui.box_row(tui.DIM + "live = o upstream aceitou essa key"
                                 + tui.RESET, inner))
        lines.append(tui.box_bottom(inner, tui.ORANGE_DK))
        while len(lines) < rows_px - 2:
            lines.append("")
        self.term.write(tui.full_frame(tui.screen(lines[: rows_px - 1], cols_px)))
        self.term.flush()
        self.term.read_key_blocking()
        self.paint(force=True)

    def paint(self, force=False):
        rows = self.render()
        body = [tui.strip(r) for r in rows]
        if not force and body == self.shown:
            return
        self.shown = body
        self.term.write(tui.full_frame(rows) if force else tui.frame(rows))
        self.term.flush()

    def run(self):
        grpool.ON_SWITCH = self.on_switch
        self.term.enter()
        try:
            self.paint(force=True)
            while True:
                key = self.term.read_key_blocking()
                if self.filtering:
                    if key == tui.KEY_ENTER:
                        self.filtering = False
                        self.scroll = 0
                        vis = self.visible()
                        if vis:
                            self.cursor = vis[0]
                    elif key == tui.KEY_ESC:
                        self.filtering = False
                        self.filter = ""
                    elif key == tui.KEY_BACKSPACE:
                        self.filter = self.filter[:-1]
                    elif isinstance(key, str) and len(key) == 1 and key.isprintable():
                        self.filter += key
                    self.paint()
                    continue
                if key == tui.KEY_UP:
                    self.move(-1)
                elif key == tui.KEY_DOWN:
                    self.move(1)
                elif key == tui.KEY_ENTER:
                    if self.models:
                        self.selected = self.models[self.cursor]
                        self.apply()
                        self.shout("modelo ativo: " + self.selected)
                elif key == "/":
                    self.filtering = True
                    self.filter = ""
                elif key in ("r", "R"):
                    self.routing = not self.routing
                    self.apply()
                    self.shout("router " + ("ON" if self.routing else "OFF"))
                elif key in ("u", "U"):
                    try:
                        self.toggle_uncensored()
                    except Exception as exc:
                        self.uncensored = False
                        self.shout("erro no uncensored: %s" % exc)
                elif key in ("i", "I"):
                    self.keys_screen()
                elif key in ("q", "Q"):
                    break
                self.paint()
        finally:
            self.term.leave()

def main():
    print("\033[38;5;208m")
    for line in BANNER:
        print(line)
    print("\033[0m")
    print("   GAMBIARRA ROUTER - discord: " + farmer.DISCORD)
    print()
    if not sys.stdout.isatty():
        return headless()
    app = App()
    print("   carregando modelos free...")
    app.load()
    print("   keys: %d    modelos: %d" % (len(app.keys), len(app.models)))
    if not app.start_server():
        print("   [!] porta %d ocupada: %s" % (grserver.PORT, app.server_error))
        print("       feche o outro programa ou use set GR_PORT=8081")
        return 3
    print("   gateway no ar: " + BASE_URL)
    time.sleep(0.4)
    app.run()
    if app.server:
        app.server.shutdown()
    print()
    print("   gateway encerrado. discord: " + farmer.DISCORD)
    return 0

def headless():
    app = App()
    app.load()
    if not app.start_server():
        print("   [!] porta %d ocupada" % grserver.PORT)
        return 3
    print("   gateway headless em " + BASE_URL)
    try:
        while True:
            time.sleep(30)
    except KeyboardInterrupt:
        pass
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
