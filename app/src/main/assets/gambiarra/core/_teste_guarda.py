"""Regressao: com provider custom ativo, NUNCA cair no NightRouter.

Reproduz a reclamacao "tem hr q ele buga e mesmo com provider custom ele
fica indo pro router": qualquer falha no custom (registro sumido, upstream
fora do ar, excecao) fazia o catalogo e as keys voltarem para o Night.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import custom_modo
import custom_provider
import keyring
import models
import providers
import router_main

ok = falha = 0


def checar(rot, cond, extra=""):
    global ok, falha
    if cond:
        ok += 1
        print("  [OK]    %s %s" % (rot, extra))
    else:
        falha += 1
        print("  [FALHA] %s %s" % (rot, extra))


def limpar():
    try:
        custom_provider.remover("guarda-teste")
    except Exception:
        pass
    try:
        custom_modo.reviver("guarda-teste")
    except Exception:
        pass
    providers.definir("nightrouter")


def main():
    # guarda o estado real para devolver EXATAMENTE como estava no fim:
    # este teste nao pode deixar o app apontando para outro provider nem
    # apagar keys de um custom de verdade
    provider_original = providers.nome_atual()
    customs_original = custom_provider.carregar(forcar=True)
    limpar()

    print("=== 1. nightrouter normal (nao deve mudar nada) ===")
    providers.definir("nightrouter")
    checar("_custom_ativo devolve None", models._custom_ativo(None) is None)
    chaves, caminho = router_main.load_keys()
    checar("load_keys nao e custom", not caminho.startswith("custom:"), caminho)

    print("\n=== 2. custom ativo com modelo configurado ===")
    custom_provider.adicionar("guarda-teste", "http://127.0.0.1:9/v1",
                              ["sk-guarda"], titulo="Guarda", modo="saldo")
    custom_provider.atualizar_campo("guarda-teste", "modelo", "modelo-x")
    providers.definir("custom:guarda-teste")
    ids = models._custom_ativo(None)
    checar("nao caiu no Night", ids is not None, str(ids))
    checar("usou o modelo configurado", ids == ["modelo-x"], str(ids))

    print("\n=== 3. custom ativo, upstream FORA do ar e sem modelo ===")
    custom_provider.atualizar_campo("guarda-teste", "modelo", "")
    ids = models._custom_ativo(None)
    checar("devolveu lista vazia, nao None", ids == [], repr(ids))
    checar("nao caiu no catalogo do Night", ids is not None, repr(ids))

    print("\n=== 4. custom ativo mas registro SUMIU ===")
    dados = custom_provider.carregar(forcar=True)
    guardado = [p for p in dados if p["nome"] == "guarda-teste"]
    custom_provider._gravar([p for p in dados if p["nome"] != "guarda-teste"])
    custom_provider._cache["at"] = 0
    ids = models._custom_ativo(None)
    checar("registro sumido = lista vazia, nao Night", ids == [], repr(ids))
    custom_provider._gravar(guardado + [p for p in dados
                                        if p["nome"] != "guarda-teste"])
    custom_provider._cache["at"] = 0

    print("\n=== 5. all_free respeita o custom ===")
    custom_provider.atualizar_campo("guarda-teste", "modelo", "modelo-y")
    lista = models.all_free(None)
    checar("all_free devolve o do custom", lista == ["modelo-y"], str(lista))

    print("\n=== 6. load_keys usa as keys do custom ===")
    chaves, caminho = router_main.load_keys()
    checar("caminho e custom", caminho.startswith("custom:"), caminho)
    checar("key do custom", chaves == ["sk-guarda"], str(chaves))

    print("\n=== 7. conta sem saldo sai da rotacao ===")
    custom_modo.marcar_morta("guarda-teste", "sk-guarda", "HTTP 402 teste")
    chaves, _ = router_main.load_keys()
    checar("key morta fora do router", chaves == [], str(chaves))
    keyring.reload(force=True)
    checar("keyring tambem vazio", keyring.rotation() == [],
           str(keyring.rotation()))

    print("\n=== 8. volta ao Night limpa ===")
    custom_modo.reviver("guarda-teste")
    providers.definir("nightrouter")
    checar("_custom_ativo None de novo", models._custom_ativo(None) is None)
    keyring.reload(force=True)
    chaves, caminho = router_main.load_keys()
    checar("load_keys do night", "custom:" not in caminho, caminho)

    limpar()

    # devolve o estado real: customs e provider como estavam antes
    try:
        atual = custom_provider.carregar(forcar=True)
        existentes = {p["nome"] for p in atual}
        restaurado = [p for p in atual if p["nome"] != "guarda-teste"]
        for p in customs_original:
            if p["nome"] not in existentes:
                restaurado.append(p)
        custom_provider._gravar(restaurado, proteger=False)
        custom_provider._cache["at"] = 0
    except Exception:
        pass
    try:
        providers.definir(provider_original)
        keyring.reload(force=True)
    except Exception:
        pass

    print("\n" + "=" * 46)
    print("  %d ok | %d falhas" % (ok, falha))
    return 0 if falha == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
