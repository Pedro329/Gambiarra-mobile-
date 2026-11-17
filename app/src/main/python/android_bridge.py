import json, os, secrets, sys, threading, time

_SERVER = None
_SERVER_THREAD = None
_LOGS = []
_LOG_LOCK = threading.Lock()
_BASE_DIR = None

def log(msg):
    linha = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    with _LOG_LOCK:
        _LOGS.append(linha)
        if len(_LOGS) > 120:
            del _LOGS[:-120]

def setup(base_dir):
    global _BASE_DIR
    _BASE_DIR = base_dir
    core_dir = os.path.join(base_dir, "core")
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    os.chdir(base_dir)
    _carregar_estado()

def _carregar_estado():
    import grpool, grserver
    key_path = os.path.join(_BASE_DIR, "gambiarra_key.txt")
    if os.path.isfile(key_path):
        with open(key_path, encoding="utf-8") as f:
            k = f.read().strip()
        if k:
            grserver.State.local_key = k
    if not grserver.State.local_key:
        k = "sk-gambiarra-" + secrets.token_hex(12)
        with open(key_path, "w", encoding="utf-8") as f:
            f.write(k)
        grserver.State.local_key = k

    mapa = {}
    free_path = os.path.join(_BASE_DIR, "free_models.json")
    if os.path.isfile(free_path):
        try:
            with open(free_path, encoding="utf-8") as f:
                dados = json.load(f)
            if isinstance(dados, dict):
                mapa.update(dados)
            elif isinstance(dados, list):
                for m in dados:
                    mapa[m] = m
        except Exception:
            pass
    for k, cadeia in grpool.ROUTER.routes.items():
        mapa.setdefault(k, k)
        for m in cadeia:
            mapa.setdefault(m, m)
    grserver.State.model_map = mapa
    if mapa and not grserver.State.selected:
        grserver.State.selected = next(iter(mapa.keys()))
    _recarregar_keys()

def _recarregar_keys():
    import farmer, grpool, grserver
    keys_path = os.path.join(_BASE_DIR, "dados", "keys.json")
    store = farmer.KeyStore(keys_path)
    lista = store.keys()
    grserver.State.keys = lista
    grpool.load_keys(lista)
    try:
        import keyring
        keyring.reload(force=True)
    except Exception:
        pass
    return len(lista)

def iniciar_servidor(base_dir):
    global _SERVER, _SERVER_THREAD
    setup(base_dir)
    if _SERVER is not None:
        return True
    import grserver
    try:
        _SERVER = grserver.build()
        _SERVER_THREAD = threading.Thread(target=_SERVER.serve_forever, daemon=True)
        _SERVER_THREAD.start()
        log("Servidor iniciado em http://127.0.0.1:%d/v1" % grserver.PORT)
        return True
    except Exception as e:
        _SERVER = None
        log("Erro ao iniciar servidor: %s" % e)
        return False

def parar_servidor():
    global _SERVER, _SERVER_THREAD
    if _SERVER is not None:
        try:
            _SERVER.shutdown()
            _SERVER.server_close()
        except Exception:
            pass
        _SERVER = None
        _SERVER_THREAD = None
        log("Servidor parado.")

def farmar_uma(base_dir):
    setup(base_dir)
    import farmer
    log("Iniciando farm de nova key...")
    rec, err = farmer.harvest_one(1)
    if not rec:
        log("Falha no farm: %s" % err)
        return json.dumps({"ok": False, "erro": err})
    keys_path = os.path.join(_BASE_DIR, "dados", "keys.json")
    store = farmer.KeyStore(keys_path)
    store.add(rec)
    total = _recarregar_keys()
    log("Key criada: %s... (Total: %d)" % (rec["key"][:12], total))
    return json.dumps({"ok": True, "key": rec["key"], "total": total})

def status_json(base_dir):
    if _BASE_DIR is None:
        setup(base_dir)
    import grpool, grserver, providers
    total, uteis, mortas, frias = grpool.POOL.resumo()
    if total == 0:
        total = len(grserver.State.keys)
        uteis = total
    with _LOG_LOCK:
        ultimos_logs = "\n".join(_LOGS[-35:])
    return json.dumps({
        "rodando": _SERVER is not None,
        "porta": grserver.PORT,
        "local_key": grserver.State.local_key or "",
        "provider": providers.rotulo(),
        "modelos": len(grserver.State.model_map),
        "keys_total": total,
        "keys_uteis": uteis,
        "requests": grserver.State.requests,
        "tokens_in": grserver.State.tokens_in,
        "tokens_out": grserver.State.tokens_out,
        "logs": ultimos_logs,
    })
