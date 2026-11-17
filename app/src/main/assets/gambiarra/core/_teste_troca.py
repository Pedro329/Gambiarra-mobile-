"""Regressao do bug "troco de provider e continua no Night".

Tres causas ficavam abertas ao mesmo tempo:

  1. router_main.load_keys() so olhava para "custom:<id>" e ignorava os
     provider fixos com keys proprias (Bike4Mind). Resultado: mesmo com
     o Bike4Mind ativo ele devolvia as keys do keys.json do Night.

  2. App.load() so trocava as keys com `if novas or not self.keys`.
     Com o Night ja carregado, `self.keys` nao era vazio, entao as keys
     do Night ficavam para sempre.

  3. keyring.reload() guardava as keys por 2s sem lembrar de qual
     provider elas vieram. Trocando logo depois de uma leitura, o cache
     servia as keys antigas.

Este teste roda os dois sentidos (night -> bike4mind -> night) e confere
upstream, rotacao, load_keys e App.load a cada passo.
"""
import json
import os
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import grpool          # noqa: E402
import keyring         # noqa: E402
import provider_fixos  # noqa: E402
import providers       # noqa: E402
import router_main     # noqa: E402

ok = falha = 0

NIGHT_BASE = "https://api.nightrouter.ai/v1"
B4M_BASE = "https://app.bike4mind.com/api/ai/v1"
KEYS_NIGHT = ["sk-NIGHT-1", "sk-NIGHT-2"]
KEY_B4M = "b4m_live_KEY"


def checar(rot, cond, extra=""):
    global ok, falha
    if cond:
        ok += 1
        print("  [OK]    %s %s" % (rot, extra))
    else:
        falha += 1
        print("  [FALHA] %s %s" % (rot, extra))


class _App:
    """Casca do App so com o que App.load mexe."""
    pass


def _aplicar(app):
    """App.load sem tocar no grserver real."""
    app.session = {}
    app.keys = list(KEYS_NIGHT)
    app.keys_path = "keys.json"
    app.models = []
    app.routing = True
    app.selected = None
    app.apply = lambda: None
    router_main.App.load(app)
    return app


def main():
    d = tempfile.mkdtemp(prefix="bugprov_")
    orig = {
        "conf": providers.CONF_FILE,
        "data": keyring.DATA_DIR,
        "base": keyring.BASE_FILE,
        "farm": keyring.FARM_FILE,
        "pf_data": provider_fixos.DATA_DIR,
        "pf_arq": provider_fixos.ARQ,
        "rm_farm": router_main.FARM_KEYS,
        "rm_local": router_main.LOCAL_KEYS,
    }
    try:
        providers.CONF_FILE = os.path.join(d, "config.json")
        keyring.DATA_DIR = d
        keyring.BASE_FILE = os.path.join(d, "keys.json")
        keyring.FARM_FILE = os.path.join(d, "farm.json")
        router_main.FARM_KEYS = os.path.join(d, "keys.json")
        router_main.LOCAL_KEYS = os.path.join(d, "nao_existe.json")
        provider_fixos.DATA_DIR = d
        provider_fixos.ARQ = os.path.join(d, "provider_keys.json")

        with open(providers.CONF_FILE, "w", encoding="utf-8") as f:
            json.dump({"provider": "nightrouter"}, f)
        with open(keyring.BASE_FILE, "w", encoding="utf-8") as f:
            json.dump({"keys": [{"key": k} for k in KEYS_NIGHT]}, f)
        provider_fixos.limpar("bike4mind")
        provider_fixos.adicionar("bike4mind", [KEY_B4M])

        print("=== 1. NightRouter ativo ===")
        keyring.reload(force=True)
        checar("upstream night", grpool._upstream() == NIGHT_BASE)
        checar("rotacao night", keyring.rotation() == KEYS_NIGHT, str(keyring.rotation()))
        checar("load_keys night",
               router_main.load_keys()[0] == KEYS_NIGHT,
               str(router_main.load_keys()[0]))

        print("\n=== 2. troca para Bike4Mind ===")
        providers.definir("bike4mind")
        checar("provider bike4mind", providers.nome_atual() == "bike4mind")
        checar("upstream b4m", grpool._upstream() == B4M_BASE, grpool._upstream())
        checar("rotacao b4m", keyring.rotation() == [KEY_B4M], str(keyring.rotation()))
        checar("load_keys b4m",
               router_main.load_keys()[0] == [KEY_B4M],
               str(router_main.load_keys()[0]))

        print("\n=== 3. App.load nao mantem as keys do night ===")
        app = _aplicar(_App())
        checar("App.keys = b4m", app.keys == [KEY_B4M], str(app.keys))

        print("\n=== 4. troca logo depois (cache quente) ===")
        providers.definir("nightrouter")
        checar("rotacao volta ao night", keyring.rotation() == KEYS_NIGHT, str(keyring.rotation()))
        providers.definir("bike4mind")
        checar("rotacao volta ao b4m", keyring.rotation() == [KEY_B4M], str(keyring.rotation()))

        print("\n=== 5. volta para NightRouter ===")
        providers.definir("nightrouter")
        checar("provider night", providers.nome_atual() == "nightrouter")
        checar("upstream night", grpool._upstream() == NIGHT_BASE)
        checar("rotacao night", keyring.rotation() == KEYS_NIGHT, str(keyring.rotation()))
        app = _aplicar(_App())
        checar("App.keys = night", app.keys == KEYS_NIGHT, str(app.keys))

        print("\n=== 6. b4m sem key nao empresta as do night ===")
        provider_fixos.limpar("bike4mind")
        providers.definir("bike4mind")
        checar("rotacao vazia", keyring.rotation() == [], str(keyring.rotation()))
        checar("load_keys vazio", router_main.load_keys()[0] == [], str(router_main.load_keys()[0]))
        checar("upstream ainda b4m", grpool._upstream() == B4M_BASE, grpool._upstream())

        print("\n" + "=" * 46)
        print("  %d ok | %d falhas" % (ok, falha))
        return 0 if falha == 0 else 1
    finally:
        providers.CONF_FILE = orig["conf"]
        keyring.DATA_DIR = orig["data"]
        keyring.BASE_FILE = orig["base"]
        keyring.FARM_FILE = orig["farm"]
        provider_fixos.DATA_DIR = orig["pf_data"]
        provider_fixos.ARQ = orig["pf_arq"]
        router_main.FARM_KEYS = orig["rm_farm"]
        router_main.LOCAL_KEYS = orig["rm_local"]
        keyring.reload(force=True)


if __name__ == "__main__":
    sys.exit(main())
