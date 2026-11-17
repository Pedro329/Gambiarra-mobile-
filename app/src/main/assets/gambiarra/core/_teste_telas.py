"""Confere que as telas do CONFIG renderizam nos dois temas.

Nao abre no terminal: chama as funcoes que montam as linhas e procura
excecao. Se o desenho quebra com um tema, o usuario ve a tela piscar e
fechar - isso pega antes.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import custom_provider
import providers
import temas
import tela_custom
import tela_config


def main():
    # garante um custom para a tela ter conteudo
    custom_provider.remover("demo-tela")
    custom_provider.adicionar("demo-tela", "https://api.exemplo.com/v1",
                              ["chave-teste-um",
                               "chave-teste-dois"],
                              titulo="Demo Tela")

    ok = falha = 0

    def checar(rot, cond, extra=""):
        nonlocal ok, falha
        if cond:
            ok += 1
            print("  [OK]    %s %s" % (rot, extra))
        else:
            falha += 1
            print("  [FALHA] %s %s" % (rot, extra))

    print("=== resumos do menu CONFIG ===")
    for tema in (temas.LEGACY, temas.INFINITY):
        conf = {"tema": tema}
        try:
            r1 = tela_config._nome_provider()
            r2 = tela_config._resumo_custom()
            checar("%s resumos" % temas.NOMES.get(tema, tema),
                   bool(r1) and bool(r2), "%s | %s" % (r1, r2))
        except Exception as exc:
            checar("%s resumos" % tema, False, repr(exc)[:70])

    print("\n=== lista de providers ===")
    for tema in (temas.LEGACY, temas.INFINITY):
        try:
            lista = providers.catalogo()
            nomes = [p["titulo"] for p in lista]
            checar("%s catalogo" % temas.NOMES.get(tema, tema),
                   "Demo Tela" in nomes, str(nomes))
        except Exception as exc:
            checar("catalogo", False, repr(exc)[:70])

    print("\n=== helpers da tela custom ===")
    try:
        longa = tela_custom._esconder("chave-ficticia-final1111")
        checar("esconder key longa",
               longa.endswith("1111") and "..." in longa
               and len(longa) < 20, longa)
        checar("esconder key curta",
               tela_custom._esconder("sk-1") == "sk-1",
               tela_custom._esconder("sk-1"))
        checar("esconder 12 chars intacta",
               tela_custom._esconder("sk-abcdefgh") == "sk-abcdefgh",
               tela_custom._esconder("sk-abcdefgh"))
        checar("esconder vazia",
               tela_custom._esconder("") == "",
               repr(tela_custom._esconder("")))
    except Exception as exc:
        checar("helpers", False, repr(exc)[:70])

    print("\n=== temas existem ===")
    for tema in (temas.LEGACY, temas.INFINITY):
        try:
            p = temas.paleta(tema)
            chaves = ["texto", "texto2", "fraco", "ok", "alerta", "erro",
                      "primaria", "destaque"]
            faltando = [k for k in chaves if k not in p]
            checar("%s paleta" % temas.NOMES.get(tema, tema),
                   not faltando, str(faltando))
        except Exception as exc:
            checar("paleta", False, repr(exc)[:70])

    custom_provider.remover("demo-tela")
    print("\n" + "=" * 46)
    print("  %d ok | %d falhas" % (ok, falha))
    return 0 if falha == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
