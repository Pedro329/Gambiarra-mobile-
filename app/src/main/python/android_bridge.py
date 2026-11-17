import json, os, re, secrets, sys, threading, time

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
    lista = []
    try:
        import keyring
        keyring.reload(force=True)
        lista = keyring.rotation() or []
    except Exception:
        pass
    if not lista:
        keys_path = os.path.join(_BASE_DIR, "dados", "keys.json")
        store = farmer.KeyStore(keys_path)
        lista = store.keys()
    grserver.State.keys = lista
    grpool.load_keys(lista)
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

def listar_providers_json(base_dir):
    if _BASE_DIR is None:
        setup(base_dir)
    import providers
    atual = providers.nome_atual()
    itens = []
    for p in providers.catalogo():
        itens.append({
            "nome": p.get("nome", ""),
            "titulo": p.get("titulo", p.get("nome", "")),
            "nota": p.get("nota", ""),
            "ativo": p.get("nome") == atual,
        })
    return json.dumps({"atual": atual, "providers": itens})

def trocar_provider(base_dir, nome):
    if _BASE_DIR is None:
        setup(base_dir)
    import providers
    if providers.definir(nome):
        total = _recarregar_keys()
        log("Provider alterado para: %s (%d keys)" % (providers.rotulo(), total))
        return json.dumps({"ok": True, "titulo": providers.rotulo()})
    log("Nao foi possivel trocar para: %s" % nome)
    return json.dumps({"ok": False})

def _salvar_custom_providers(lista_novos):
    custom_path = os.path.join(_BASE_DIR, "dados", "custom_providers.json")
    atuais = []
    if os.path.isfile(custom_path):
        try:
            with open(custom_path, encoding="utf-8") as f:
                dados = json.load(f)
            if isinstance(dados, list):
                atuais = dados
        except Exception:
            atuais = []

    novas_keys = 0
    ultimo_id = None
    for item in lista_novos:
        if not isinstance(item, dict):
            continue
        base = str(item.get("base") or "").strip().rstrip("/")
        chaves = [str(k).strip() for k in (item.get("keys") or []) if str(k).strip()]
        if not base or not chaves:
            continue
        titulo = str(item.get("titulo") or item.get("nome") or base).strip()
        slug = re.sub(r"[^a-zA-Z0-9_-]", "", str(item.get("nome") or titulo).lower()) or "custom"
        ultimo_id = "custom:" + slug

        existente = next((p for p in atuais if p.get("base", "").rstrip("/") == base or p.get("nome") == slug), None)
        if existente is not None:
            pool_atual = existente.setdefault("keys", [])
            for k in chaves:
                if k not in pool_atual:
                    pool_atual.append(k)
                    novas_keys += 1
        else:
            atuais.append({
                "nome": slug,
                "titulo": titulo,
                "base": base,
                "keys": chaves,
                "modelo": str(item.get("modelo") or ""),
            })
            novas_keys += len(chaves)

    os.makedirs(os.path.dirname(custom_path), exist_ok=True)
    with open(custom_path, "w", encoding="utf-8") as f:
        json.dump(atuais, f, indent=2, ensure_ascii=False)
    return novas_keys, ultimo_id

def adicionar_custom_manual(base_dir, titulo, base_url, api_key, modelo=""):
    if _BASE_DIR is None:
        setup(base_dir)
    import providers
    url = str(base_url or "").strip().rstrip("/")
    chave = str(api_key or "").strip()
    if not url or not chave:
        return json.dumps({"ok": False, "erro": "Preencha a URL e a API Key"})
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    nome_limpo = str(titulo or "").strip()
    if not nome_limpo:
        nome_limpo = re.sub(r"^https?://", "", url).split("/")[0]

    novas, ultimo_id = _salvar_custom_providers([{
        "nome": nome_limpo,
        "titulo": nome_limpo,
        "base": url,
        "keys": [chave],
        "modelo": str(modelo or "").strip(),
    }])
    if ultimo_id:
        providers.definir(ultimo_id)
    total = _recarregar_keys()
    log("Provider salvo e ativado: %s (%d keys)" % (providers.rotulo(), total))
    return json.dumps({"ok": True, "titulo": providers.rotulo(), "total": total})

def importar_keys_json(base_dir, conteudo_json):
    if _BASE_DIR is None:
        setup(base_dir)
    import farmer, providers
    try:
        raw = json.loads(conteudo_json)
    except Exception as e:
        log("Erro ao ler JSON: %s" % e)
        return json.dumps({"ok": False, "erro": "JSON invalido"})

    candidatos_custom = []
    if isinstance(raw, dict) and raw.get("base") and raw.get("keys"):
        candidatos_custom = [raw]
    elif isinstance(raw, list) and any(isinstance(x, dict) and x.get("base") for x in raw):
        candidatos_custom = [x for x in raw if isinstance(x, dict) and x.get("base")]

    if candidatos_custom:
        novas, ultimo_id = _salvar_custom_providers(candidatos_custom)
        if ultimo_id:
            providers.definir(ultimo_id)
        total = _recarregar_keys()
        log("Custom provider importado (+%d keys) e ativado!" % novas)
        return json.dumps({"ok": True, "novas": novas, "total": total})

    registros = []
    if isinstance(raw, dict) and isinstance(raw.get("keys"), list):
        for item in raw["keys"]:
            if isinstance(item, dict) and item.get("key"):
                registros.append(item)
            elif isinstance(item, str) and item.strip():
                registros.append({"name": "importada", "key": item.strip()})
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("key"):
                registros.append(item)
            elif isinstance(item, str) and item.strip():
                registros.append({"name": "importada", "key": item.strip()})

    if not registros:
        log("Nenhuma key encontrada no arquivo.")
        return json.dumps({"ok": False, "erro": "Nenhuma key encontrada"})

    keys_path = os.path.join(_BASE_DIR, "dados", "keys.json")
    store = farmer.KeyStore(keys_path)
    existentes = set(store.keys())
    novas = 0
    for rec in registros:
        chave = str(rec.get("key") or "").strip()
        if chave and chave not in existentes:
            store.add(rec)
            existentes.add(chave)
            novas += 1

    total = _recarregar_keys()
    log("Importadas +%d keys novas (Total: %d)" % (novas, total))
    return json.dumps({"ok": True, "novas": novas, "total": total})

def reviver_keys(base_dir):
    if _BASE_DIR is None:
        setup(base_dir)
    import grpool
    grpool.POOL.revive()
    total = _recarregar_keys()
    log("Pool recarregado (%d keys ativas)." % total)
    return total

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
