import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import farmer          # noqa: E402
import farmer_panel    # noqa: E402  (Farm, read_state, KEYS_FILE)

HERE = os.path.dirname(os.path.abspath(__file__))
BANNER_FILE = os.path.join(HERE, "banner.txt")
DISCORD = getattr(farmer, "DISCORD", "https://discord.gg/gambiarra")

RAMP_TOP = (255, 72, 52)
RAMP_BOTTOM = (110, 14, 10)

def ramp(t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(RAMP_TOP[i] + (RAMP_BOTTOM[i] - RAMP_TOP[i]) * t))
                 for i in range(3))

def focus(rows):
    total = max(1, len(rows))
    return [[ramp(i / float(total - 1) if total > 1 else 0.0) for _ in row]
            for i, row in enumerate(rows)]

def load_banner():
    try:
        with open(BANNER_FILE, encoding="utf-8") as f:
            rows = [line.rstrip("\n").rstrip() for line in f]
    except OSError:
        return []
    return [r for r in rows if r.strip()]

def fit_banner(rows, cols):
    widest = max((len(r) for r in rows), default=0)
    if widest <= cols:
        return rows
    return [r[:cols].rstrip() for r in rows]

def paint(rows, colour, cols):
    reset = "\033[0m" if colour else ""
    out = []
    for row, shades in zip(rows, focus(rows)):
        pad = max(0, (cols - len(row)) // 2)
        if not colour:
            out.append((" " * pad) + row)
            continue
        chunks = []
        last = None
        for ch, rgb in zip(row, shades):
            if rgb != last:
                chunks.append(colour(rgb))
                last = rgb
            chunks.append(ch)
        out.append((" " * pad) + "".join(chunks) + reset)
    return out

def bar(done, target, cells=40):
    cells = max(10, cells)
    frac = 0.0 if target <= 0 else max(0.0, min(1.0, done / float(target)))
    filled = int(round(frac * cells))
    return "[" + "|" * filled + " " * (cells - filled) + "]"

def out(text):
    sys.stdout.write(text)
    try:
        sys.stdout.flush()
    except Exception:
        pass

def ask_target(default=50):
    try:
        raw = input("  quantas keys [%d]: " % default).strip()
    except (EOFError, KeyboardInterrupt):
        return 0
    digits = "".join(ch for ch in raw if ch.isdigit())
    return max(1, int(digits)) if digits else default

def probe_existing(store, colour, reset, limit=24):
    entries = [e for e in list(store.items) if e.get("key")]
    if not entries:
        return []
    batch = entries[-limit:]
    results = {}
    lock = threading.Lock()

    def one(entry):
        key = entry["key"]
        probe_key = key if key.startswith("sk-") else "sk-" + key
        status, _ = farmer.probe_api(probe_key, timeout=12)
        with lock:
            results[key] = status == 200

    threads = [threading.Thread(target=one, args=(e,), daemon=True)
               for e in batch]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ruins = [k for k, ok in results.items() if not ok]
    if ruins:
        dead = set(ruins)
        store.items = [e for e in store.items if e.get("key") not in dead]
        store.flush()
        out("  " + colour(ramp(0.6)) + "%d key(s) morta(s) removida(s)" % len(ruins)
            + reset + "\n")
    return [k for k, ok in results.items() if ok]

def main():
    os.system("")
    colour_ok = sys.stdout.isatty()
    colour = (lambda rgb: "\033[38;2;%d;%d;%dm" % rgb) if colour_ok else (lambda rgb: "")
    reset = "\033[0m" if colour_ok else ""
    try:
        cols = os.get_terminal_size().columns
    except OSError:
        cols = 100

    rows = fit_banner(load_banner(), max(40, cols - 2))
    print()
    for line in paint(rows, colour, max(40, cols - 2)):
        print(line)
    print()
    print("  " + colour(ramp(0.15)) + "discord: " + DISCORD + reset)
    print("  " + colour(ramp(0.55)) + "as keys ficam em dados\\keys.json, pode fechar"
          " quando quiser" + reset)
    print()

    target = ask_target()
    if target <= 0:
        return 0

    store = farmer.KeyStore(farmer_panel.KEYS_FILE)
    threads = farmer_panel.read_state()
    print()
    if store.count():
        print("  " + colour(ramp(0.4)) + "testando as keys que ja tenho..." + reset)
        live = probe_existing(store, colour, reset)
        print("  " + colour(ramp(0.3)) + "%d boas, %d no arquivo"
              % (len(live), store.count()) + reset)
        print()

    start = store.count()
    job = farmer_panel.Farm(store, threads, target=target,
                            conf=farmer_panel._ler_conf())
    job.start()

    try:
        while True:
            snap = job.snapshot()
            novas = max(0, snap["total"] - start)
            line = "  %s %3d/%d  +%d novas  proxies %d  %s" % (
                bar(novas, target), novas, target, novas,
                snap["proxies"], (snap.get("last") or "")[:26])
            if snap["refreshing"] and snap["proxies"] == 0:
                line += "  buscando proxies..."
            out("\r" + line + "     ")
            if novas >= target:
                out("\n\n  pronto: %d keys novas, %d no arquivo\n"
                    % (novas, snap["total"]))
                break
            time.sleep(0.4)
    except KeyboardInterrupt:
        out("\n\n  parado: %d keys novas\n" % (max(0, store.count() - start)))
    finally:
        job.halt()
    print("  arquivo: " + farmer_panel.KEYS_FILE)
    print()
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
