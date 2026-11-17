"""Tela do AutoAgent: grava a config do opencode ou do deepseek harness."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import menu_principal as mp
import temas

BASE_DIR = os.path.dirname(HERE)
DATA_DIR = os.path.join(BASE_DIR, "dados")
ESC = "\x1b["

try:
    import grserver

    def _porta():
        # le sempre o valor atual: o launcher pode trocar a porta
        return grserver.PORT
except Exception:
    def _porta():
        return int(os.environ.get("GR_PORT", "8080"))


def _p(tema):
    return temas.paleta(tema)


def _chave_local():
    caminho = os.path.join(BASE_DIR, "gambiarra_key.txt")
    try:
        with open(caminho, encoding="utf-8") as f:
            valor = f.read().strip()
        if valor:
            return valor
    except OSError:
        pass
    return "gambiarraapi-0000"


def BASE_URL():
    return "http://127.0.0.1:%d/v1" % _porta()


def gerar_opencode():
    """Escreve dados/opencode.json apontando para o servidor local."""
    dados = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "gambiarra": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Gambiarra",
                "options": {
                    "baseURL": BASE_URL(),
                    "apiKey": _chave_local(),
                },
                "models": {
                    "modelo-unlimited": {"name": "Gambiarra unlimited"},
                },
            }
        },
        "model": "gambiarra/modelo-unlimited",
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    caminho = os.path.join(DATA_DIR, "opencode.json")
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)
    os.replace(tmp, caminho)
    return caminho, "opencode.json"


def gerar_deepseek():
    """Escreve dados/ds_harness.env.ps1."""
    os.makedirs(DATA_DIR, exist_ok=True)
    caminho = os.path.join(DATA_DIR, "ds_harness.env.ps1")
    texto = (
        "# gerado pelo Night Router\r\n"
        "$env:OPENAI_BASE_URL = '%s'\r\n"
        "$env:OPENAI_API_KEY  = '%s'\r\n"
        "$env:OPENAI_MODEL    = 'modelo-unlimited'\r\n"
        "Write-Host 'Night Router: ambiente carregado' -ForegroundColor Cyan\r\n"
        % (BASE_URL(), _chave_local())
    )
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    return caminho, "ds_harness.env.ps1"


def _mostrar(corpo, tema, largura, t, cols):
    if tema == temas.INFINITY:
        caixa = mp.moldura_infinity(corpo, largura, t)
    else:
        caixa = mp.moldura_legacy(corpo, largura)
    saida = [""]
    for l in caixa:
        saida.append(mp._centro(l, cols))
    return saida


def abrir(app, cols=None, rows=None):
    tema = app.tema
    mp.drenar()
    escolhido = 0
    opcoes = [("OpenCode", "grava dados/opencode.json"),
              ("DeepSeek Harness", "grava dados/ds_harness.env.ps1")]
    resultado = ""
    sys.stdout.write(ESC + "?25l")
    try:
        while True:
            c, r = mp.tamanho()
            t = time.time() - app.t0
            largura = max(50, min(c - 1, 90))
            p = _p(tema)
            corpo = [""]
            if tema == temas.INFINITY:
                corpo.append(mp._centro(temas.rolar_arco("AUTOAGENT", t), largura - 2))
            else:
                corpo.append(mp._centro(p["brilho"] + temas.BOLD
                                        + "AUTOAGENT" + temas.RESET, largura - 2))
            corpo.append("")
            corpo.append("  " + p["fraco"]
                         + "aponta o agente para o servidor local" + temas.RESET)
            corpo.append("  " + p["fraco"] + "base url  " + temas.RESET
                         + p["texto2"] + BASE_URL() + temas.RESET)
            corpo.append("")
            for i, (nome, desc) in enumerate(opcoes):
                sel = (i == escolhido)
                if tema == temas.INFINITY:
                    marca = temas.rolar_arco("▸ ", t) if sel else "  "
                else:
                    marca = (p["destaque"] + "▸ " + temas.RESET) if sel else "  "
                if sel:
                    fundo = (temas.rgb(80, 60, 180, fundo=True)
                             if tema == temas.INFINITY else p["fundo_destaque"])
                    corpo.append("  " + marca + fundo + temas.BOLD
                                 + " " + nome.ljust(18) + temas.RESET
                                 + "  " + p["texto"] + desc + temas.RESET)
                else:
                    corpo.append("  " + marca + temas.BOLD + " " + p["texto2"]
                                 + nome.ljust(18) + temas.RESET + "  "
                                 + p["fraco"] + desc + temas.RESET)
            corpo.append("")
            if resultado:
                corpo.append("  " + p["ok"] + "+ " + resultado + temas.RESET)
            else:
                corpo.append("")
            corpo.append("")
            dica = "setas mover   enter gravar   esc voltar"
            if tema == temas.INFINITY:
                corpo.append(" " + temas.pintar_arco(dica, t * 0.2, brilho=0.72))
            else:
                corpo.append(" " + p["fraco"] + dica + temas.RESET)
            mp.desenhar(_mostrar(corpo, tema, largura, t, c), c, r)

            tecla = mp.le_tecla(0.1)
            if tecla is None:
                continue
            if tecla in ("esc", "backspace"):
                return
            if tecla in ("cima", "k"):
                escolhido = (escolhido - 1) % len(opcoes)
            elif tecla in ("baixo", "j"):
                escolhido = (escolhido + 1) % len(opcoes)
            elif tecla in ("1", "2"):
                escolhido = int(tecla) - 1
                tecla = "enter"
            if tecla == "enter":
                try:
                    if escolhido == 0:
                        caminho, nome = gerar_opencode()
                    else:
                        caminho, nome = gerar_deepseek()
                    resultado = "%s gravado em dados/%s" % (nome, nome)
                    app.aviso(resultado, 5)
                except Exception as exc:
                    resultado = "falhou: %s" % str(exc)[:50]
    finally:
        sys.stdout.write(temas.RESET + ESC + "?25h")
        sys.stdout.flush()
