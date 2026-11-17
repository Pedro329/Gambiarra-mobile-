import json
import os
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(BASE_DIR, "dados")

def _first_writable(paths, name):
    """Prefer the project's own dados folder so nothing is left beside the
    extracted zip. Fall back to the old layout only to pick up existing keys."""
    for path in paths:
        if os.path.exists(path):
            return path
    target = paths[0]
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
    except OSError:
        pass
    return target

BASE_FILE = _first_writable([os.path.join(DATA_DIR, "base_keys.json"),
                             os.path.join(ROOT, "base_keys.json")],
                            "base_keys.json")
FARM_FILE = _first_writable([os.path.join(DATA_DIR, "keys.json"),
                             os.path.join(ROOT, "keys.json")],
                            "keys.json")
STATE_FILE = os.path.join(DATA_DIR, "rotation.json")
RETRY_AFTER = 15 * 60
_lock = threading.Lock()
_cache = {"base": [], "farm": [], "at": 0.0}

def _read_keys(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    items = data.get("keys") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if isinstance(it, str):
            out.append(it.strip())
        elif isinstance(it, dict) and isinstance(it.get("key"), str):
            out.append(it["key"].strip())
    return [k for k in out if k]

def _custom_keys():
    """Keys do provider ativo quando ele NAO usa o Farm.

    Dois casos:
      custom:<id>  -> keys do Custom Provider
      bike4mind    -> provider fixo com keys proprias (aba custom)

    O custom roda na MESMA fila de rotacao: ele so troca de onde as keys
    vem, sem mudar cooldown, marca de morta ou troca de modelo.
    """
    try:
        import providers
        nome = providers.nome_atual()
        if nome.startswith("custom:"):
            import custom_provider
            return custom_provider.keys_do_ativo()
        if providers.atual().get("na_custom"):
            import provider_fixos
            return provider_fixos.keys_de(nome)
        return []
    except Exception:
        return []


def reload(force=False):
    with _lock:
        # o cache de 2s vale SO para o mesmo provider. Se a pessoa trocou
        # de provider no CONFIG, o cache antigo devolveria as keys do
        # anterior e o router seguiria no NightRouter.
        try:
            import providers
            atual = providers.nome_atual()
        except Exception:
            atual = ""
        validade = 2.0 if atual == _cache.get("provider") else 0.0
        if not force and time.time() - _cache["at"] < validade:
            return _cache["base"], _cache["farm"]
        _cache["provider"] = atual
        custom = _custom_keys()
        # ATENCAO: `if custom:` era O BUG de "as vezes vai pro NightRouter".
        # Keys mortas todas removidas -> lista vazia -> falsy -> caia no
        # else e carregava o keys.json do Night (6 keys) e mandava requests
        # para api.nightrouter.ai mesmo com provider custom escolhido.
        # Aqui decide pelo PROVIDER, nunca pelo tamanho da lista.
        # Vale igual para os fixos com keys proprias (Bike4Mind).
        proprio = False
        try:
            import providers
            proprio = (providers.nome_atual().startswith("custom:")
                       or bool(providers.atual().get("na_custom")))
        except Exception:
            proprio = False
        if proprio:
            # provider com keys proprias: entram como "base".
            # Vazio de proposito: melhor "sem keys" do que usar as do Night.
            _cache["base"] = custom
            _cache["farm"] = []
        else:
            _cache["base"] = _read_keys(BASE_FILE)
            _cache["farm"] = _read_keys(FARM_FILE)
        _cache["at"] = time.time()
        return _cache["base"], _cache["farm"]


def sources():
    base, farm = reload(force=True)
    try:
        import providers
        nome = providers.nome_atual()
        if nome.startswith("custom:") or providers.atual().get("na_custom"):
            p = providers.atual()
            rotulo = "(custom)" if nome.startswith("custom:") else "(fixo)"
            rows = [(p["titulo"] + " " + rotulo, base)]
            return rows
    except Exception:
        pass
    rows = [("base (night)", base), ("farm (gambiarra)", farm)]
    rows.sort(key=lambda r: len(r[1]), reverse=True)
    return rows

def rotation(skip=(), limit=None, retry_dead=False):
    base, farm = reload()
    dead = {} if retry_dead else _load_dead()
    now = time.time()
    base = [k for k in base if k not in skip]
    farm = [k for k in farm if k not in skip]
    base_ok = [k for k in base if not _is_dead(k, dead, now)]
    base_bad = [k for k in base if _is_dead(k, dead, now)]
    farm_ok = [k for k in farm if not _is_dead(k, dead, now)]
    farm_bad = [k for k in farm if _is_dead(k, dead, now)]
    out = []
    a, b = 0, 0
    while a < len(base_ok) or b < len(farm_ok):
        if a < len(base_ok):
            out.append(base_ok[a])
            a += 1
        if b < len(farm_ok):
            out.append(farm_ok[b])
            b += 1
    out.extend(base_bad)
    out.extend(farm_bad)
    if limit:
        out = out[:limit]
    return out

def mark_dead(key):
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {"dead": {}}
    data.setdefault("dead", {})[key] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    except OSError:
        pass
    _cache["at"] = 0.0

def mark_live(key):
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    if data.get("dead", {}).pop(key, None) is not None:
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
        except OSError:
            pass
        _cache["at"] = 0.0

def _is_dead(key, dead, now):
    stamp = dead.get(key)
    if not stamp:
        return False
    try:
        at = time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M:%S"))
    except (TypeError, ValueError):
        return False
    return now - at < RETRY_AFTER

def _load_dead():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f).get("dead", {}) or {}
    except (OSError, ValueError):
        return {}

def counts():
    base, farm = reload()
    dead = _load_dead()
    now = time.time()
    return {"base": len(base), "farm": len(farm),
            "base_dead": sum(1 for k in base if _is_dead(k, dead, now)),
            "farm_dead": sum(1 for k in farm if _is_dead(k, dead, now))}

if __name__ == "__main__":
    for name, keys in sources():
        print("%-20s %d keys" % (name, len(keys)))
    order = rotation()
    print("rotacao: %d keys na fila" % len(order))
    for k in order[:4]:
        print("  ", k[:16])
