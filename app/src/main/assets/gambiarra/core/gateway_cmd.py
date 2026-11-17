import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import farmer_panel   # noqa: E402  (read_state lives there)
import grpool         # noqa: E402
import grserver       # noqa: E402
import farm_cmd       # noqa: E402  (banner + gradient, same look)

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(BASE_DIR, "dados")
KEYS = os.path.join(DATA_DIR, "keys.json")
LEGACY_KEYS = os.path.join(ROOT, "keys.json")
LOCAL_KEYS = os.path.join(BASE_DIR, "keys.json")
LOCAL_KEY_FILE = os.path.join(BASE_DIR, "gambiarra_key.txt")
BASE_URL = "http://127.0.0.1:%d/v1" % grserver.PORT
UNCENSORED = os.path.join(HERE, "uncensured.md")

def local_key():
    try:
        with open(LOCAL_KEY_FILE, encoding="utf-8-sig") as f:
            value = f.read().strip()
        value = value.lstrip("\ufeff").strip()
        if value:
            return value
    except OSError:
        pass
    value = "gambiarraapi-local"
    try:
        with open(LOCAL_KEY_FILE, "w", encoding="utf-8", newline="\n") as f:
            f.write(value)
    except OSError:
        pass
    return value

def rotation_keys():
    try:
        import keyring
        order = keyring.rotation()
        if order:
            return order, keyring.sources()
    except Exception:
        pass
    keys, path = load_keys()
    return keys, [("keys.json", keys)]

def load_keys():
    for path in (KEYS, LEGACY_KEYS, LOCAL_KEYS):
        if os.path.exists(path):
            try:
                keys = __import__("farmer").KeyStore(path).keys()
            except Exception:
                keys = []
            if keys:
                return keys, path
    return [], KEYS

def load_models():
    import models as model_catalog
    try:
        keys = rotation_keys()[0]
        return model_catalog.all_free(keys[0] if keys else None)
    except Exception:
        try:
            import models as model_catalog
            return list(model_catalog.DEFAULTS)
        except Exception:
            return []

def ask_uncensored():
    try:
        raw = input("  modelos uncensored? (pode bugar) [s/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return raw in ("s", "sim", "y", "yes", "1")

def load_context():
    for path in (UNCENSORED, os.path.join(BASE_DIR, "uncensured.md")):
        try:
            with open(path, "rb") as f:
                data = f.read().decode("utf-8", "replace").strip()
            if data:
                return data
        except OSError:
            continue
    return ""

def main():
    os.system("")
    colour = sys.stdout.isatty()
    paint = (lambda rgb: "\033[38;2;%d;%d;%dm" % rgb) if colour else (lambda rgb: "")
    reset = "\033[0m" if colour else ""
    try:
        cols = os.get_terminal_size().columns
    except OSError:
        cols = 100

    rows = farm_cmd.fit_banner(farm_cmd.load_banner(), max(40, cols - 2))
    print()
    for line in farm_cmd.paint(rows, paint, max(40, cols - 2)):
        print(line)
    print()
    print("  " + paint(farm_cmd.ramp(0.15)) + "discord: " + farm_cmd.DISCORD
          + reset)
    print()

    uncensored = ask_uncensored()
    context = load_context() if uncensored else ""

    keys, sources = rotation_keys()
    models = load_models()
    grpool.load_keys(keys)
    grserver.State.keys = keys
    grserver.State.local_key = local_key()
    grserver.State.selected = models[0] if models else None
    grserver.State.routing = True
    grserver.State.model_map = {m: m for m in models}
    grserver.State.system_context = {m: context for m in models} if context else {}
    grserver.State.global_context = context or None
    grpool.ROUTER.routes = {m: grpool.build_chain(models, m) for m in models}

    if not keys:
        print("  " + paint(farm_cmd.ramp(0.6))
              + "nenhuma key: rode o Farm Key no menu primeiro" + reset)

    try:
        srv = grserver.build()
    except OSError as exc:
        print("  " + paint((255, 40, 30))
              + "porta %d ocupada (%s)" % (grserver.PORT, exc) + reset)
        print("  " + paint((255, 190, 60))
              + "feche a outra janela do gateway ou use: set GR_PORT=8081"
              + reset)
        print()
        try:
            input("  aperte Enter para sair...")
        except (EOFError, KeyboardInterrupt):
            pass
        return 3

    import threading
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def warm():
        """Find out which models actually have a channel before the first
        real request needs one."""
        try:
            pool_keys, _ = load_keys()
            if not pool_keys:
                return
            grpool.scan_alive(models, pool_keys)
        except Exception:
            pass

    threading.Thread(target=warm, daemon=True).start()

    print()
    print("  " + paint(farm_cmd.ramp(0.25)) + "ONLINE  " + BASE_URL + reset)
    print("  " + paint(farm_cmd.ramp(0.4)) + "API key: " + local_key() + reset)
    print("  " + paint(farm_cmd.ramp(0.5)) + "modelo : "
          + (models[0] if models else "-") + reset)
    for name, group in sources:
        print("  " + paint(farm_cmd.ramp(0.55)) + "%-18s %3d keys"
              % (name, len(group)) + reset)
    print("  " + paint(farm_cmd.ramp(0.6)) + "%d modelos  router ON  rotacao ON"
          % len(models) + reset)
    if context:
        print("  " + paint(farm_cmd.ramp(0.45)) + "uncensored ON" + reset)
    else:
        print("  " + paint(farm_cmd.ramp(0.7)) + "uncensored OFF" + reset)
    print()
    print("  " + paint(farm_cmd.ramp(0.75)) + "Ctrl+C fecha" + reset)
    print()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        grserver.State.system_context = {}
        grserver.State.global_context = None
        grserver.State.routing = False
        srv.shutdown()
    print("  gateway encerrado, contexto limpo")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
