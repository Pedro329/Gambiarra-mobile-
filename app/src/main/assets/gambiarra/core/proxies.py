import json
import os
import queue
import random
import socket
import ssl
import struct
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))

SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
    "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/http.txt",
    "https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
    "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",
    "https://raw.githubusercontent.com/mertguvencli/http-proxy-list/main/proxy-list/data.txt",
    "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
    "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt",
    "https://raw.githubusercontent.com/mahdibland/ShadowsocksAggregator/master/Eternity.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/prxchk/proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
    "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt",
    "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt",
    "https://raw.githubusercontent.com/B4RC0DE-TM/proxy-list/main/HTTP.txt",
    "https://raw.githubusercontent.com/saisuiu/Lionkings-Http-Proxys-Proxies/main/cnfree.txt",
    "https://raw.githubusercontent.com/aslisk/proxyhttps/main/https.txt",
    "https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/https.txt",
    "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt",
    "https://raw.githubusercontent.com/FalconForceTeam/SOAPHound/main/proxies.txt",
    "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/http/http.txt",
    "https://raw.githubusercontent.com/yemixzy/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/themiralay/Proxy-List-World/master/data.txt",
    "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/http.txt",
    "https://raw.githubusercontent.com/ObcbO/getproxy/master/http.txt",
    "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/http_proxies.txt",
    "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/http.txt",
    "https://raw.githubusercontent.com/CobaltFusionCE/scanner/main/proxies.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_anonymous/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
]
CHECK_HOST = "nightrouter.ai"
CHECK_PATH = "/bff/user/register"
CHECK_PLAIN = "example.com"
CHECK_PLAIN_PATH = "/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
CACHE = os.path.join(HERE, "proxies_good.json")
TARGET_BATCH = 6

def _fetch(url, timeout=15):
    import urllib.request
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return ""

def collect(limit=6000):
    """All lists at once. Thirty-nine sources in series takes minutes; in
    parallel the scrape is done in a couple of seconds."""
    bodies = []
    lock = threading.Lock()

    def grab(url):
        body = _fetch(url, timeout=12)
        if body:
            with lock:
                bodies.append(body)

    threads = [threading.Thread(target=grab, args=(url,), daemon=True)
               for url in SOURCES]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    seen = set()
    out = []
    for body in bodies:
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            if "://" in line:
                line = line.split("://", 1)[1]
            line = line.split()[0]
            if line.count(":") != 1:
                continue
            host, _, port = line.partition(":")
            if not port.isdigit() or not 0 < int(port) < 65536:
                continue
            parts = host.split(".")
            if len(parts) != 4 or not all(p.isdigit() for p in parts):
                continue
            if any(int(p) > 255 for p in parts):
                continue
            if line not in seen:
                seen.add(line)
                out.append(line)
            if len(out) >= limit:
                return out
    return out

def _tunnel(proxy, target_host, port=443, timeout=8):
    host, _, pport = proxy.partition(":")
    try:
        raw = socket.create_connection((host, int(pport)), timeout=timeout)
    except Exception:
        return None
    try:
        raw.sendall(("CONNECT %s:%d HTTP/1.1\r\nHost: %s:%d\r\n\r\n"
                     % (target_host, port, target_host, port)).encode())
        head = raw.recv(200)
        if b" 200" not in head.split(b"\r\n", 1)[0]:
            return None
        ctx = ssl.create_default_context()
        tls = ctx.wrap_socket(raw, server_hostname=target_host)
        return tls
    except Exception:
        try:
            raw.close()
        except OSError:
            pass
        return None

def _http_via(proxy, target_host, path, timeout=8):
    host, _, port = proxy.partition(":")
    try:
        s = socket.create_connection((host, int(port)), timeout=timeout)
    except Exception:
        return b""
    try:
        s.sendall(("GET http://%s%s HTTP/1.0\r\nHost: %s\r\n"
                   "User-Agent: %s\r\nConnection: close\r\n\r\n"
                   % (target_host, path, target_host, UA)).encode())
        chunks = []
        while True:
            data = s.recv(4096)
            if not data:
                break
            chunks.append(data)
            if len(b"".join(chunks)) > 200:
                return b"".join(chunks)
        return b"".join(chunks)
    except Exception:
        return b""
    finally:
        try:
            s.close()
        except OSError:
            pass

def check(proxy, timeout=6, fast=False):
    t0 = time.time()
    try:
        raw = _http_via(proxy, CHECK_PLAIN, CHECK_PLAIN_PATH, timeout=timeout)
    except Exception:
        raw = b""
    if not raw.startswith(b"HTTP/"):
        return None
    tls = _tunnel(proxy, CHECK_HOST, timeout=timeout)
    if tls is None:
        return None
    try:
        tls.close()
    except OSError:
        pass
    if fast:
        return proxy, time.time() - t0

    t1 = time.time()
    try:
        s = _tunnel(proxy, CHECK_HOST, timeout=timeout)
        if s is None:
            return None
        s.sendall(("GET /register HTTP/1.1\r\nHost: %s\r\n%s"
                   "Connection: close\r\n\r\n" % (CHECK_HOST, BASE_HEADERS)).encode())
        data = b""
        while len(data) < 2048:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        s.close()
    except Exception:
        return None
    if not data.startswith(b"HTTP/") or b" 200" not in data[:20]:
        return None
    if b"<html" not in data.lower() and b"<!doctype" not in data.lower():
        return None
    return proxy, time.time() - t1

BASE_HEADERS = ("User-Agent: %s\r\nAccept: text/html,application/xhtml+xml\r\n"
                "Accept-Language: en-US,en;q=0.9\r\n" % UA)

def test_pool(candidates, workers=200, time_budget=20, fast=False):
    """Run every candidate through check() in parallel and keep the winners,
    slowest last. Workers default high because each check is mostly waiting."""
    found = []
    lock = threading.Lock()
    q = queue.Queue()
    for item in candidates:
        q.put(item)
    deadline = time.time() + time_budget

    def worker():
        while True:
            try:
                proxy = q.get_nowait()
            except queue.Empty:
                return
            if time.time() > deadline:
                return
            try:
                hit = check(proxy, fast=fast)
            except Exception:
                hit = None
            if hit:
                with lock:
                    found.append(hit)

    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(min(workers, max(1, len(candidates))))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    found.sort(key=lambda pair: pair[1])
    return found

def supreme(candidates, workers=400, phases=((3, True), (7, False))):
    """Two passes: a cheap reachability sweep to cut the pool, then a real
    request through the survivor set. Returns only proxies that actually
    served nightrouter.ai."""
    alive = []
    for timeout, fast in phases:
        if not alive:
            pool_in = candidates
        else:
            pool_in = [p for p, _ in alive]
        if not pool_in:
            break
        alive = []
        lock = threading.Lock()
        q = queue.Queue()
        for item in pool_in:
            q.put(item)

        def worker():
            while True:
                try:
                    proxy = q.get_nowait()
                except queue.Empty:
                    return
                try:
                    hit = check(proxy, timeout=timeout, fast=fast)
                except Exception:
                    hit = None
                if hit:
                    with lock:
                        alive.append(hit)

        threads = [threading.Thread(target=worker, daemon=True)
                   for _ in range(min(workers, max(1, len(pool_in))))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        alive.sort(key=lambda pair: pair[1])
        if fast and len(alive) > 400:
            alive = alive[:400]
    return alive

def save(good):
    try:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump({"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "proxies": [{"proxy": p, "ms": round(ms * 1000)}
                                   for p, ms in good[:60]]}, f, indent=1)
    except OSError:
        pass

def load():
    try:
        with open(CACHE, encoding="utf-8") as f:
            data = json.load(f)
        return [(row["proxy"], row.get("ms", 999) / 1000.0)
                for row in data.get("proxies", []) if row.get("proxy")]
    except (OSError, ValueError, KeyError, TypeError):
        return []

# Ports that home routers and misconfigured boxes leave open to the world.
# This is what makes the project independent of public lists: if the lists are
# empty or rate-limited, we go find our own.
COMMON_PORTS = [80, 81, 1080, 3128, 4444, 5000, 5555, 6588, 8000, 8001,
                8080, 8081, 8082, 8085, 8118, 8888, 9000, 9050, 9090,
                9999, 10809, 10000, 18080, 4145, 3129, 3127, 8089, 8111]

def _public_prefixes(budget=200):
    """IPv4 /24 blocks worth sweeping. Random internet space is almost all
    dead, so weight the sweep toward hosting and consumer ranges that
    actually carry open proxies."""
    import random as _r
    # hosting / VPS / residential ranges where open proxies show up most
    seeds = [
        (5, None), (31, None), (37, None), (45, None), (46, None), (51, None),
        (62, None), (77, None), (78, None), (79, None), (80, None), (81, None),
        (82, None), (84, None), (85, None), (86, None), (87, None), (88, None),
        (89, None), (91, None), (93, None), (94, None), (95, None), (103, None),
        (104, None), (109, None), (141, None), (146, None), (149, None),
        (151, None), (156, None), (157, None), (158, None), (159, None),
        (160, None), (161, None), (162, None), (163, None), (164, None),
        (165, None), (166, None), (167, None), (168, None), (169, None),
        (170, None), (171, None), (175, None), (176, None), (177, None),
        (178, None), (179, None), (180, None), (181, None), (182, None),
        (183, None), (184, None), (185, None), (186, None), (187, None),
        (188, None), (189, None), (190, None), (191, None), (192, None),
        (193, None), (194, None), (195, None), (196, None), (197, None),
        (200, None), (201, None), (202, None), (203, None), (210, None),
        (211, None), (212, None), (213, None), (217, None), (218, None),
        (219, None), (220, None), (221, None), (222, None), (223, None),
    ]
    out = []
    for _ in range(budget):
        a, _ignore = _r.choice(seeds)
        b = _r.randint(0, 255)
        c = _r.randint(0, 255)
        prefix = "%d.%d.%d." % (a, b, c)
        if not _private(prefix + "1"):
            out.append(prefix)
    return out

def _private(ip):
    """True for addresses that can never be a public proxy: loopback, RFC1918,
    link-local, CGNAT and the like."""
    try:
        parts = [int(p) for p in ip.split(".")]
    except ValueError:
        return True
    if len(parts) != 4 or any(p > 255 for p in parts):
        return True
    a, b = parts[0], parts[1]
    if a in (0, 10, 127):
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 192 and b == 168:
        return True
    if a == 169 and b == 254:
        return True
    if a == 100 and 64 <= b <= 127:
        return True
    if a >= 224:
        return True
    return False

def generate(want=400, workers=300, timeout=1.6, budget_seconds=25):
    """Home-made proxy finder: probe random public hosts on the usual proxy
    ports and keep whoever answers like a real proxy. This is our own supply,
    so a busy public list no longer stops the farm."""
    import random as _r
    found = []
    lock = threading.Lock()
    deadline = time.time() + budget_seconds
    prefixes = _public_prefixes()
    stop = threading.Event()

    def probe():
        while not stop.is_set():
            if time.time() > deadline:
                return
            with lock:
                if len(found) >= want:
                    stop.set()
                    return
            host = _r.choice(prefixes) + str(_r.randint(1, 254))
            if _private(host):
                continue
            port = _r.choice(COMMON_PORTS)
            candidate = "%s:%d" % (host, port)
            try:
                sock = socket.create_connection((host, port), timeout=timeout)
            except Exception:
                continue
            try:
                sock.settimeout(timeout)
                sock.sendall(("CONNECT %s:443 HTTP/1.1\r\n"
                              "Host: %s:443\r\n"
                              "User-Agent: %s\r\n\r\n"
                              % (CHECK_HOST, CHECK_HOST, UA)).encode())
                head = sock.recv(256)
            except Exception:
                head = b""
            finally:
                try:
                    sock.close()
                except OSError:
                    pass
            # Only a proxy answers CONNECT with 200 and then speaks TLS. Plain
            # web servers bounce or answer 400/404 on port 80, so requiring
            # 200 here keeps the sweep honest.
            first = head.split(b"\r\n", 1)[0]
            if not first.startswith(b"HTTP/1."):
                continue
            if b" 200" not in first:
                continue
            if b"proxy" in head.lower() or b"html" in head.lower():
                # a proxy error page is not a tunnel
                continue
            with lock:
                if candidate not in found:
                    found.append(candidate)

    threads = [threading.Thread(target=probe, daemon=True)
               for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return found

def top_up(target=40, rounds=6, per_round=1200):
    """Keep growing the saved pool instead of doing one big sweep. Public
    lists are shared by everyone, so the only way to stay supplied is to keep
    retrying in the background and keep whatever answers."""
    total = 0
    known = {p for p, _ in load()}
    for i in range(rounds):
        try:
            pool_in = collect()
        except Exception:
            pool_in = []
        try:
            pool_in = pool_in + generate(want=per_round, budget_seconds=20)
        except Exception:
            pass
        random.shuffle(pool_in)
        good = supreme(pool_in[:per_round])
        if good:
            merged = list(load())
            have = {p for p, _ in merged}
            added = 0
            for proxy, ms in good:
                if proxy not in have:
                    merged.append((proxy, ms))
                    have.add(proxy)
                    added += 1
            merged.sort(key=lambda pair: pair[1])
            save(merged[:400])
            total += added
        if len(known) + total >= target and i >= 1:
            break
    return total

def refresh(target=TARGET_BATCH, pages=2, min_ms=4000, sample=2500):
    saved = load()
    if len(saved) >= target:
        # already have enough from earlier rounds
        return [(p, ms) for p, ms in saved[:target]]
    candidates = collect()
    if len(candidates) < target * 20:
        candidates = list(candidates) + generate(want=max(80, target * 8))
    random.shuffle(candidates)
    if sample and len(candidates) > sample:
        candidates = candidates[:sample]
    good = supreme(candidates)
    fast = [pair for pair in good if pair[1] * 1000 <= min_ms]
    good = fast or good
    good.sort(key=lambda pair: pair[1])
    merged = list(good)
    have = {p for p, _ in merged}
    for proxy, ms in saved:
        if proxy not in have:
            merged.append((proxy, ms))
            have.add(proxy)
    merged.sort(key=lambda pair: pair[1])
    if merged:
        save(merged[:400])
    return merged[:target] if len(merged) > target else merged

def vivo(proxy, timeout=6):
    """Teste rapido: a proxy realmente encaminha trafego HTTPS?

    Confere que o CONNECT abre E que a resposta chega. Usado antes de
    gastar uma conta em cima de uma proxy morta (o cache envelhece).
    """
    if not proxy:
        return False
    if "://" in proxy:
        proxy = proxy.split("://", 1)[1]
    if "@" in proxy:
        proxy = proxy.rpartition("@")[2]
    s = _tunnel(proxy, "api.ipify.org", port=443, timeout=timeout)
    if s is None:
        return False
    try:
        s.sendall(("GET / HTTP/1.1\r\nHost: api.ipify.org\r\n"
                   "User-Agent: %s\r\nConnection: close\r\n\r\n" % UA).encode())
        dado = s.recv(64)
        return dado.startswith(b"HTTP/")
    except Exception:
        return False
    finally:
        try:
            s.close()
        except OSError:
            pass


def vivos(lista, timeout=6, workers=40):
    """Filtra em paralelo, mantendo a ordem original das que respondem."""
    if not lista:
        return []
    bons = []
    trava = threading.Lock()
    fila = queue.Queue()
    for p in lista:
        fila.put(p)

    def operario():
        while True:
            try:
                p = fila.get_nowait()
            except queue.Empty:
                return
            try:
                if vivo(p, timeout=timeout):
                    with trava:
                        bons.append(p)
            except Exception:
                pass

    threads = [threading.Thread(target=operario, daemon=True)
               for _ in range(min(workers, len(lista)))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ordem = {p: i for i, p in enumerate(lista)}
    bons.sort(key=lambda p: ordem.get(p, 1 << 30))
    return bons


def ip_atual(proxy=None, timeout=10):
    """IP publico visto saindo por esta proxy (ou direto, se proxy=None)."""
    import urllib.request
    handlers = []
    if proxy:
        p = proxy if "://" in proxy else "http://" + proxy
        handlers.append(urllib.request.ProxyHandler({"http": p, "https": p}))
    op = urllib.request.build_opener(*handlers)
    with op.open("https://api.ipify.org", timeout=timeout) as r:
        return r.read().decode("utf-8", "replace").strip()


def batch(target=TARGET_BATCH, allow_cache=True):
    good = refresh(target)
    if good:
        return [p for p, _ in good]
    if allow_cache:
        return [p for p, _ in load()[:target]]
    return []


def prontas(target=TARGET_BATCH, revalidar=True, timeout=6):
    """Proxies prontas para uso: pega o lote e valida ao vivo.

    O cache guarda proxies que ja morreram; validar aqui evita queimar
    contas em cima delas. Se sobrarem poucas, coleta mais uma rodada.
    """
    lista = batch(target=max(target * 2, 10))
    if not lista:
        return []
    if revalidar:
        lista = vivos(lista, timeout=timeout)
    if len(lista) < target:
        try:
            extra = [p for p, _ in refresh(target=target * 2)]
        except Exception:
            extra = []
        novos = [p for p in extra if p not in set(lista)]
        if novos:
            lista += vivos(novos, timeout=timeout)
    return lista[:max(target, 4)]

def pool():
    state = {"items": [], "at": 0.0}

    def next_proxy():
        now = time.time()
        if not state["items"] or now - state["at"] > 90:
            state["items"] = batch()
            state["at"] = now
        if not state["items"]:
            return None
        return state["items"].pop(0)

    return next_proxy

if __name__ == "__main__":
    started = time.time()
    result = refresh(target=8)
    for proxy, ms in result:
        print("%-22s %5.0f ms" % (proxy, ms * 1000))
    print("%d proxies bons em %.1fs" % (len(result), time.time() - started))
