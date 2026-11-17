"""Regressao: editar a URL do proxy rotativo depois de salva.

Antes, salvar a URL prendia o usuario: a tela mostrava apenas
"salvo: http://user:***@host" e o enter, com "rotativo" ja escolhido,
simplesmente fechava — nao havia como corrigir a URL sem editar o
config.json na mao.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import tela_config   # noqa: E402

ok = falha = 0


def checar(rot, cond, extra=""):
    global ok, falha
    if cond:
        ok += 1
        print("  [OK]    %s %s" % (rot, extra))
    else:
        falha += 1
        print("  [FALHA] %s %s" % (rot, extra))


def detectar_existe():
    return callable(getattr(tela_config, "_menu_editar_proxy", None))


def main():
    print("=== 1. menu de edicao existe ===")
    checar("_menu_editar_proxy definido", detectar_existe())

    import inspect
    src = inspect.getsource(tela_config._menu_editar_proxy)
    checar("opcao usar", '"usar"' in src)
    checar("opcao editar", '"editar"' in src)
    checar("opcao apagar", '"apagar"' in src)
    checar("esc volta (None)", "return None" in src)
    checar("atalho e = editar", '"e"' in src and '"editar"' in src)

    print("\n=== 2. o fluxo do enter trata rotativa salva ===")
    fonte = inspect.getsource(tela_config.tela_proxy)
    checar("chama o menu", "_menu_editar_proxy(st)" in fonte)
    checar("abre edicao ao escolher editar",
           'acao == "editar"' in fonte)
    checar("apaga a URL", 'acao == "apagar"' in fonte)
    checar("volta para auto ao apagar",
           '"auto"' in fonte.split('acao == "apagar"')[1][:300])
    checar("sem URL abre edicao vazia",
           'not st.conf.get("proxy_url")' in fonte)
    checar("atalho e na lista", 'tecla == "e"' in fonte)

    print("\n=== 3. a dica aparece na tela ===")
    checar("mostra 'enter abre as opcoes de editar'",
           "enter abre as opcoes de editar" in fonte)
    checar("dica so quando rotativa esta selecionada",
           'opcoes[escolhido] == "rotativa"' in fonte)

    print("\n=== 4. a URL salva nao e perdida ao abrir o menu ===")
    checar("menu le proxy_url do conf",
           'st.conf.get("proxy_url")' in src)
    checar("editar reaproveita a URL atual",
           'buffer = st.conf.get("proxy_url", "")' in fonte)

    print("\n=== 5. _esconder preserva o formato na tela ===")
    import navegadores
    u = "http://usuario:senha@proxy.exemplo.com:8080"
    oculta = navegadores._esconder(u)
    checar("escondeu a senha", "senha" not in oculta, oculta)
    checar("mostra o host", "proxy.exemplo.com" in oculta, oculta)

    print("\n" + "=" * 46)
    print("  %d ok | %d falhas" % (ok, falha))
    return 0 if falha == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
