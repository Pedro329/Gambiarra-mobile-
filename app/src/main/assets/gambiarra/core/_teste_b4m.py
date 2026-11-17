"""Regressao: Bike4Mind como provider fixo na aba Custom.

  * aparece no catalogo e na lista da aba custom
  * NAO da para excluir nem trocar a base
  * keys proprias, rotacao e cemiterio de sem saldo
  * adaptador traduz /api/chat -> formato OpenAI
  * NightRouter continua intocado
"""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import adaptador
import custom_modo
import provider_fixos
import providers

ok = falha = 0


def checar(rot, cond, extra=""):
    global ok, falha
    if cond:
        ok += 1
        print("  [OK]    %s %s" % (rot, extra))
    else:
        falha += 1
        print("  [FALHA] %s %s" % (rot, extra))


def main():
    print("=== 1. Bike4Mind no catalogo ===")
    cat = providers.catalogo()
    nomes = [p["nome"] for p in cat]
    checar("bike4mind existe", "bike4mind" in nomes, str(nomes))
    b4m = next((p for p in cat if p["nome"] == "bike4mind"), {})
    checar("marcado como fixo", b4m.get("fixo") is True)
    checar("aparece na aba custom", b4m.get("na_custom") is True)
    checar("adapter b4m-chat", b4m.get("adapter") == "b4m-chat")
    checar("base fixa", b4m.get("base") == "https://app.bike4mind.com/api/ai/v1")

    print("\n=== 2. nao da para excluir ===")
    checar("e_fixo_na_custom", provider_fixos.e_fixo_na_custom("bike4mind"))
    checar("nightrouter nao e fixo-custom",
           not provider_fixos.e_fixo_na_custom("nightrouter"))
    # remover por engano nao mexe na base
    antes = b4m.get("base")
    checar("base inalteravel no catalogo",
           next(p for p in providers.catalogo()
                if p["nome"] == "bike4mind")["base"] == antes)

    print("\n=== 3. adaptador ===")
    base = "https://app.bike4mind.com/api/ai/v1"
    checar("detecta b4m pelo host", adaptador.detectar(base) == "b4m-chat")
    checar("chat vai para /api/chat",
           adaptador.url_chat(base, "b4m-chat") == "https://app.bike4mind.com/api/chat")
    checar("models vai para /api/v1/models",
           adaptador.url_models(base, "b4m-chat")
           == "https://app.bike4mind.com/api/v1/models")
    checar("anyapi continua openai",
           adaptador.detectar("https://api.anyapi.ai/v1") == "openai")
    checar("nightrouter continua openai",
           adaptador.detectar("https://api.nightrouter.ai/v1") == "openai")

    print("\n=== 4. traducao da resposta ===")
    sse = ('data: {"type":"meta","requestId":"x"}\n'
           'data: {"type":"content","text":"ol"\n\n'      # linha truncada de proposito
           'data: {"type":"content","text":"a mundo"}\n\n'
           'data: [DONE]\n')
    env = adaptador.para_openai(sse, "b4m", "m1")
    checar("SSE vira choices", env and env["choices"][0]["message"]["content"] == "a mundo",
           repr(env["choices"][0]["message"]["content"]) if env else "None")
    js = json.dumps({"response": "oi", "model": "claude-haiku"})
    env2 = adaptador.para_openai(js, "b4m-chat", "")
    checar("/api/chat vira choices",
           env2 and env2["choices"][0]["message"]["content"] == "oi")

    print("\n=== 5. corpo enviado ao /api/chat ===")
    payload = {"model": "claude-haiku", "max_tokens": 10,
               "messages": [{"role": "system", "content": "seja curto"},
                            {"role": "user", "content": "oi"}]}
    corpo = adaptador.montar(payload, "b4m-chat")
    checar("tem campo message", "message" in corpo, str(list(corpo)))
    checar("system vira instrucoes", "seja curto" in corpo["message"])
    checar("pergunta preservada", corpo["message"].endswith("oi"))
    checar("wait=True", corpo.get("wait") is True)
    checar("max_tokens traduzido", corpo.get("maxTokens") == 10)

    print("\n=== 6. keys proprias + modo ===")
    provider_fixos.limpar("bike4mind")
    provider_fixos.adicionar("bike4mind", ["b4m_live_aaa", "b4m_live_bbb"])
    checar("2 keys salvas", len(provider_fixos.keys_de("bike4mind")) == 2)
    checar("modo saldo padrao", provider_fixos.modo_de("bike4mind") == "saldo")
    provider_fixos.definir_modo("bike4mind", "free")
    checar("modo free gravado", provider_fixos.modo_de("bike4mind") == "free")
    provider_fixos.definir_modo("bike4mind", "saldo")

    print("\n=== 7. conta sem saldo sai da rotacao ===")
    providers.definir("bike4mind")
    checar("provider ativo", providers.nome_atual() == "bike4mind")
    checar("rotulo de keys proprias", providers.atual().get("na_custom") is True)
    custom_modo.marcar_morta("bike4mind", "b4m_live_aaa", "You're out of credits")
    vivas = provider_fixos.keys_de("bike4mind")
    checar("key morta removida", vivas == ["b4m_live_bbb"], str(vivas))
    checar("registrada no cemiterio",
           "b4m_live_aaa" in custom_modo.listar_mortas("bike4mind"))
    checar("keys_vivas respeita",
           custom_modo.keys_vivas("bike4mind") == ["b4m_live_bbb"])

    print("\n=== 8. erro real do Bike4Mind detectado ===")
    checar("'out of credits' = sem saldo",
           custom_modo.e_sem_saldo(200, "You're out of credits. This request "
                                        "needs about 1649 credits, but only "
                                        "993 are available."))
    checar("'Insufficient credits' = sem saldo",
           custom_modo.e_sem_saldo(422, '{"errorCode":"insufficient_credits"}'))
    checar("429 nao e sem saldo",
           not custom_modo.e_sem_saldo(429, "Rate limit exceeded. Try again"))

    print("\n=== 9. NightRouter intacto ===")
    custom_modo.reviver("bike4mind")
    provider_fixos.limpar("bike4mind")
    providers.definir("nightrouter")
    checar("volta ao night", providers.nome_atual() == "nightrouter")
    checar("night nao tem na_custom",
           not providers.atual().get("na_custom"))
    checar("night base correta",
           providers.base_url_atual() == "https://api.nightrouter.ai/v1")

    print("\n" + "=" * 46)
    print("  %d ok | %d falhas" % (ok, falha))
    return 0 if falha == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
