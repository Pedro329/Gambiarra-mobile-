"""O probe do farm usa os modelos REAIS da conta?

Em 15/11/2026 o pool free do NightRouter caiu para um unico modelo
(glm-5.3-flash-free). O farmer testava cinco nomes fixos, todos mortos,
e toda key nova era reprovada com "sem canal em deepseek-v3.2-free" —
o farm nao gerava nada mesmo com a key boa.

Este teste garante que:
  1. a lista vem de /v1/models (com cache), nao de KEY_GROUP_PROBE
  2. se /models cair, ainda existe um palpite de reserva
  3. "model_not_found" conta como sem canal (e nao como key invalida)
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import farmer  # noqa: E402

ok = falha = 0


def checar(rot, cond, extra=""):
    global ok, falha
    if cond:
        ok += 1
        print("  [OK]    %s %s" % (rot, extra))
    else:
        falha += 1
        print("  [FALHA] %s %s" % (rot, extra))


class _Resp:
    def __init__(self, dados):
        self._dados = dados

    def read(self):
        import json
        return json.dumps(self._dados).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def main():
    print("=== 1. lista vem do servidor, com cache ===")
    chamadas = {"n": 0}
    dados = {"data": [{"id": "glm-5.3-flash-free"},
                      {"id": "outro-modelo-free"}]}

    def falso(url, timeout=None):
        chamadas["n"] += 1
        return _Resp(dados)

    original = farmer.urllib.request.urlopen
    farmer.urllib.request.urlopen = falso
    farmer._MODELOS_CACHE.clear()
    try:
        ids = farmer.modelos_da_conta("sk-teste")
        checar("leu do servidor", ids == ["glm-5.3-flash-free",
                                         "outro-modelo-free"], str(ids))
        checar("uma chamada", chamadas["n"] == 1, str(chamadas["n"]))
        farmer.modelos_da_conta("sk-teste")
        checar("cache evita nova chamada", chamadas["n"] == 1, str(chamadas["n"]))
        farmer.modelos_da_conta("sk-teste", forcar=True)
        checar("forcar ignora cache", chamadas["n"] == 2, str(chamadas["n"]))

        print("\n=== 2. erro no servidor cai no palpite ===")
        def quebrado(url, timeout=None):
            raise OSError("sem rede")
        farmer.urllib.request.urlopen = quebrado
        farmer._MODELOS_CACHE.clear()
        ids = farmer.modelos_da_conta("sk-outra")
        checar("usa reserva", ids == list(farmer.KEY_GROUP_PROBE), str(ids[:2]))
        checar("reserva nao esta vazia", len(farmer.KEY_GROUP_PROBE) > 0)
        checar("glm esta na reserva", "glm-5.3-flash-free" in farmer.KEY_GROUP_PROBE,
               str(farmer.KEY_GROUP_PROBE))
    finally:
        farmer.urllib.request.urlopen = original
        farmer._MODELOS_CACHE.clear()

    print("\n=== 3. models_aleatorios ===")
    farmer.urllib.request.urlopen = lambda url, timeout=None: _Resp(
        {"data": [{"id": "a-free"}, {"id": "b-free"}, {"id": "c-free"},
                  {"id": "d-free"}]})
    try:
        farmer._MODELOS_CACHE.clear()
        r = farmer.models_aleatorios("sk-x", 2)
        checar("devolve 2", len(r) == 2, str(r))
        todos = {"a-free", "b-free", "c-free", "d-free"}
        checar("so da lista", set(r) <= todos, str(r))
    finally:
        farmer.urllib.request.urlopen = original
        farmer._MODELOS_CACHE.clear()

    print("\n=== 4. usable_group usa a lista da conta ===")
    testados = []

    def probe_falso(api_key, model=None, timeout=None):
        testados.append(model)
        # o modelo real responde; os fixos velhos nao existem mais
        if model == "glm-5.3-flash-free":
            return 200, '{"choices":[]}'
        return 503, '{"error":{"code":"model_not_found","message":' \
                    '"No available channel for model %s"}}' % model

    original_probe = farmer.probe_chat
    original_url = farmer.urllib.request.urlopen
    farmer.probe_chat = probe_falso
    farmer.urllib.request.urlopen = lambda url, timeout=None: _Resp(
        {"data": [{"id": "glm-5.3-flash-free"}]})
    try:
        farmer._MODELOS_CACHE.clear()
        okk, msg = farmer.usable_group(None, "sk-y")
        checar("key aprovada", okk is True, msg)
        checar("testou so o modelo real",
               "glm-5.3-flash-free" in testados, str(testados))
        checar("nao testou nome morto",
               "deepseek-v3.2-free" not in testados, str(testados))

        print("\n=== 5. model_not_found = sem canal, nao key invalida ===")
        testados.clear()

        def probe_morto(api_key, model=None, timeout=None):
            testados.append(model)
            return 503, '{"error":{"code":"model_not_found"}}'

        farmer.probe_chat = probe_morto
        farmer._MODELOS_CACHE.clear()
        okk2, msg2 = farmer.usable_group(None, "sk-z")
        checar("reprova quando nada responde", okk2 is False, msg2)
        checar("motivo fala de canal", "canal" in msg2, msg2)
        checar("limitou tentativas", len(testados) <= 4, str(len(testados)))

        print("\n=== 6. conta sem saldo ===")
        def probe_sem_saldo(api_key, model=None, timeout=None):
            return 402, '{"error":{"code":"insufficient_user_quota"}}'
        farmer.probe_chat = probe_sem_saldo
        farmer._MODELOS_CACHE.clear()
        okk3, msg3 = farmer.usable_group(None, "sk-w")
        checar("reprova", okk3 is False, msg3)
        checar("motivo = sem saldo", "saldo" in msg3, msg3)

        print("\n=== 7. rate limit conta como canal ok ===")
        def probe_rl(api_key, model=None, timeout=None):
            return 429, '{"error":{"message":"rate_limit reached"}}'
        farmer.probe_chat = probe_rl
        farmer._MODELOS_CACHE.clear()
        okk4, msg4 = farmer.usable_group(None, "sk-v")
        checar("aprova", okk4 is True, msg4)
    finally:
        farmer.probe_chat = original_probe
        farmer.urllib.request.urlopen = original_url
        farmer._MODELOS_CACHE.clear()

    print("\n" + "=" * 46)
    print("  %d ok | %d falhas" % (ok, falha))
    return 0 if falha == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
