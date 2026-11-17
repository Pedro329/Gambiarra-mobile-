import json
import os
import re
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "free_models.json")
ORDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "model_order.json")

DEFAULTS = [
    "claude-fable-5", "claude-fable-5-1", "claude-opus-5", "claude-opus-5-codex",
    "claude-sonnet-5", "deepseek-v4-flash", "deepseek-v4.1-flash",
    "gemini-3.6-flash", "gemini-3.8-flash", "gemini-4-argon", "glm-5.1",
    "glm-5.3", "glm-5.3-flash", "kimi-k3", "kimi-k3.1-pro-free", "minimax-m3-free",
]

def _get(url, timeout=20):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "text/html,application/xhtml+xml,application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception:
        return 0, ""

def from_models_page():
    for path in ("/models?tab=free", "/models"):
        status, body = _get("https://nightrouter.ai" + path)
        if status == 200:
            found = sorted(set(re.findall(r'data-model="([^"]+)"', body)))
            found = [m.strip() for m in found if m.strip()]
            if found:
                return [_alias(m) for m in found]
    return []

def _alias(name):
    """The page lists deepseek-v4-flash while the API also answers to
    deepseek-v4-flash-free. Keep whichever the account is allowed to use."""
    return name

def uncensored_models():
    status, body = _get("https://nightrouter.ai/models?tab=uncensored")
    if status != 200:
        return []
    found = []
    for mid in re.findall(r'data-model="([^"]+)"', body):
        mid = mid[:-5] if mid.endswith("-free") else mid
        if "ncensored" in mid and mid not in found:
            found.append(mid)
    return found

def from_api(api_key):
    if not api_key:
        return []
    req = urllib.request.Request("https://api.nightrouter.ai/v1/models")
    req.add_header("Authorization", "Bearer " + api_key)
    req.add_header("User-Agent", UA)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return []
    items = data.get("data") if isinstance(data, dict) else None
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        mid = it.get("id")
        if not isinstance(mid, str) or not mid.strip():
            continue
        mid = mid.strip()
        # a model is free when the catalogue says so, either by the -free
        # suffix or by a zero price on the entry itself
        price = it.get("pricing") or {}
        zero = is_free_price(price)
        if zero or "-free" in mid or it.get("free") is True:
            out.append(mid)
    return sorted(set(out))

def is_free_price(price):
    if not isinstance(price, dict):
        return False
    values = [v for v in price.values() if isinstance(v, (int, float, str))]
    if not values:
        return False
    for v in values:
        try:
            if float(v) != 0:
                return False
        except (TypeError, ValueError):
            continue
    return True

def cache_read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [m for m in json.load(f) if isinstance(m, str)]
    except (OSError, ValueError):
        return []

def cache_write(path, models):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(models, f, indent=1)
    except OSError:
        pass

def all_free(api_key=None):
    """Modelos do provider ativo.

    Se o provider for um Custom Provider, a lista vem da base url dele,
    respeitando o modo:
        free  -> so os gratuitos
        saldo -> todos
    Caso contrario, mantem exatamente o comportamento do NightRouter.
    """
    custom = _custom_ativo(api_key)
    if custom is not None:
        return custom
    api = from_api(api_key)
    page = from_models_page()
    models = merge_free(page, api)
    if models:
        cache_write(CACHE, models)
        write_order(models)
        return models
    models = cache_read(CACHE)
    if models:
        return models
    models = list(DEFAULTS)
    write_order(models)
    return models


def _custom_ativo(api_key=None):
    """Lista do provider ativo (custom ou fixo com keys proprias).

    Devolve None (e nao []) so quando o ativo e o NightRouter, para o
    chamador seguir o caminho normal dele.
    """
    try:
        import providers
        prov_cat = providers.atual() or {}
        eh_custom = providers.nome_atual().startswith("custom:")
        na_custom = bool(prov_cat.get("na_custom"))
        if not eh_custom and not na_custom:
            return None
        # Daqui para baixo o provider usa keys proprias: NUNCA devolvemos
        # None, porque None manda o chamador para o catalogo do NightRouter.
        # Era esse o bug de "as vezes vai pro NightRouter mesmo com
        # custom configurado": bastava nao achar o registro ou dar um
        # erro qualquer para cair no catalogo do Night.
        import custom_modo
        nome = providers.nome_atual().replace("custom:", "")
        if eh_custom:
            import custom_provider
            prov = custom_provider.por_nome(nome)
        else:
            prov = {"nome": nome, "base": prov_cat.get("base", ""),
                    "titulo": prov_cat.get("titulo", nome), "modelo": "",
                    "modo": custom_modo.modo_atual(),
                    "adapter": prov_cat.get("adapter", ""), "keys": []}
        if not prov:
            return []
        # em modo saldo, usa a key ativa se houver
        chave = ""
        chaves = custom_modo.keys_vivas(nome)
        if chaves:
            chave = chaves[0]
        elif prov.get("keys"):
            chave = prov["keys"][0]
        ids, _bruto = custom_modo.listar(prov, chave)
        if ids:
            write_order(ids)
            return ids
        # upstream nao respondeu: cai no que a pessoa configurou
        if prov.get("modelo"):
            return [prov["modelo"]]
        return []
    except Exception:
        # provider com keys proprias e erro: devolve vazio em vez de
        # mentir que o catalogo e o do NightRouter
        try:
            import providers
            if (providers.nome_atual().startswith("custom:")
                    or (providers.atual() or {}).get("na_custom")):
                return []
        except Exception:
            pass
        return None

def write_order(models):
    """Rotation map: every model falls back to the next one in the list, so a
    quota error moves on instead of retrying the same name.

    MESCLA com o que ja existe no arquivo. Sem isso, cada descoberta de
    catalogo (que pode trazer so 6 modelos) apagava a vizinhanca inteira
    e o roteamento anti-TPM ficava sem para onde ir.
    """
    existente = {}
    try:
        with open(ORDER, encoding="utf-8") as f:
            lido = json.load(f)
        if isinstance(lido, dict):
            existente = lido
    except (OSError, ValueError):
        pass

    # universo = modelos descobertos + tudo que o arquivo ja conhecia
    universo = list(models)
    for nome in existente:
        if nome not in universo:
            universo.append(nome)

    order = {}
    total = len(universo)
    for i, name in enumerate(universo):
        order[name] = [universo[(i + j) % total] for j in range(total)]

    # preserva cadeias antigas de quem nao esta no universo novo
    for nome, cadeia in existente.items():
        if nome not in order:
            order[nome] = cadeia

    cache_write(ORDER, order)

def merge_free(page, api):
    """One entry per model. deepseek-v4.1-flash and deepseek-v4.1-flash-free
    are the same model, so the short name is the one kept."""
    out = []
    index = {}
    for name in list(page) + list(api):
        if not name:
            continue
        base = name[:-5] if name.endswith("-free") else name
        plain = not name.endswith("-free")
        if base in index:
            pos = index[base]
            if plain and out[pos].endswith("-free"):
                out[pos] = name
            continue
        index[base] = len(out)
        out.append(name)
    return out
