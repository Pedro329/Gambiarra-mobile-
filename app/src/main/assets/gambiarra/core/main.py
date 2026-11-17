"""Night Router - ponto de entrada.

  1. primeira vez? pergunta o tema
  2. loading do tema escolhido
  3. menu principal (servidor ja no ar)
"""
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import temas

ESC = "\x1b["


def _titulo():
    """Titulo da janela, igual em todos os sistemas."""
    nome = "Gambiarra-Infinite"
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(nome)
            return
        except Exception:
            pass
    # ANSI OSC: Linux, macOS e Windows Terminal
    try:
        sys.stdout.write("\x1b]0;%s\x07" % nome)
        sys.stdout.flush()
    except Exception:
        pass


def _prepara_codepage():
    if os.name != "nt":
        return
    os.system("")
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass


def _sobe_servidor():
    """Sobe o gateway numa thread. Devolve o servidor ou None."""
    try:
        import router_main
        app = router_main.App()
        app.load()
        if app.start_server():
            return app
    except Exception as exc:
        return {"erro": str(exc)[:120]}
    return None


def _arrancar_servidor():
    import grserver
    import porta as porta_mod
    # a 8080 costuma estar ocupada (Steam, Docker); sobe numa livre
    escolhida = porta_mod.escolher(grserver.PORT)
    grserver.PORT = escolhida
    os.environ["GR_PORT"] = str(escolhida)

    import router_main
    router_main.grserver.PORT = escolhida
    app = router_main.App()
    app.load()
    ok = app.start_server()
    return (app, ok)


def main():
    _prepara_codepage()
    _titulo()

    # maximiza antes de qualquer desenho: ascii e loading precisam de tela
    try:
        import menu_principal
        menu_principal.preparar_terminal()
    except Exception:
        pass
    time.sleep(0.25)

    conf = temas.carregar()

    # 1. tema: primeira vez pergunta, depois respeita o salvo
    if temas.precisa_escolher():
        try:
            import seletor_tema
            escolhido = seletor_tema.escolher()
            conf = temas.carregar()
            conf["tema"] = escolhido
            temas.salvar(conf)
        except Exception:
            conf["tema"] = temas.LEGACY
            temas.salvar(conf)
        conf = temas.carregar()

    tema = conf.get("tema") or temas.LEGACY

    # 2. carrega os modulos que o loading precisa saber
    etapas = [
        "carregando tema %s" % temas.NOMES[tema],
        "inspecionando navegador",
        "preparando proxy",
        "subindo o servidor",
        "pronto para o farm",
    ]

    caixa = {}

    def tarefa():
        # roda na thread principal entre quadros, sem travar a animacao
        pass

    try:
        import loading
        if tema == temas.INFINITY:
            # descobre o navegador antes, para a etapa ser verdadeira
            import navegadores
            if not conf.get("navegador"):
                try:
                    achado = navegadores.escolhido(conf)
                    if achado:
                        conf["navegador"] = achado
                        temas.salvar(conf)
                except Exception:
                    pass
            loading.rodar(etapas, tarefa=tarefa)
        else:
            loading.loading_legacy([e for e in etapas], pausa=0.18)
    except Exception:
        pass

    # 3. sobe o servidor de verdade
    servidor = None
    try:
        servidor, ok = _arrancar_servidor()
        if not ok:
            servidor = None
    except Exception:
        servidor = None

    try:
        import estado_servidor
        estado_servidor.definir_jailbreak(conf.get("jailbreak", False))
    except Exception:
        pass

    # 4. menu
    import menu_principal
    try:
        menu_principal.abrir(conf, servidor)
    finally:
        try:
            if servidor is not None and hasattr(servidor, "shutdown"):
                servidor.shutdown()
        except Exception:
            pass



def headless():
    """Sem TUI: so o servidor, para rodar em background."""
    conf = temas.carregar()
    if temas.precisa_escolher():
        conf["tema"] = temas.LEGACY
        temas.salvar(conf)
    servidor, ok = _arrancar_servidor()
    if not ok:
        print("  porta ocupada")
        return 3
    print("  Night Router no ar")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    if "--headless" in sys.argv:
        sys.exit(headless())
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write(temas.RESET + ESC + "?25h" + ESC + "2J" + ESC + "H")
        print("  ate mais. " + temas.DISCORD)
