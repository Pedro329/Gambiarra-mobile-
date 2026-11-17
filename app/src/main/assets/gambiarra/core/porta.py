"""Acha uma porta livre para o servidor.

A 8080 costuma estar ocupada (Steam, Docker, outros servidores). Em vez de
falhar com WinError 10013, sobe na proxima livre e avisa.
"""
import os
import socket

PREFERIDAS = (8080, 8081, 8082, 8090, 8091, 8095, 8096, 8097, 8098, 8099)


def _livre(porta, host="127.0.0.1"):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, porta))
        return True
    except OSError:
        return False
    finally:
        s.close()


def escolher(preferida=None):
    """Devolve a porta a usar. A variavel GR_PORT manda, se existir."""
    env = os.environ.get("GR_PORT")
    if env:
        try:
            return int(env)
        except ValueError:
            pass
    if preferida and _livre(preferida):
        return preferida
    for p in PREFERIDAS:
        if _livre(p):
            return p
    # qualquer porta alta
    for p in range(8100, 8200):
        if _livre(p):
            return p
    return 8080


def explicar(porta):
    """Mensagem amigavel quando a porta mudou."""
    if porta != 8080:
        return ("a 8080 estava ocupada (Steam/docker costuma usar). "
                "subi na %d" % porta)
    return "porta %d" % porta
