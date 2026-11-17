"""Estado compartilhado com o servidor (grserver).

O servidor ja le grserver.State; aqui so expomos o jailbreak para o menu
poder ligar e desligar sem importar o servidor inteiro.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_JB = {"ativo": False}


def definir_jailbreak(valor):
    _JB["ativo"] = bool(valor)
    try:
        import grserver
        grserver.State.jailbreak = _JB["ativo"]
    except Exception:
        pass


def jailbreak_ativo():
    return _JB["ativo"]
