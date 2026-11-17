import json
import os
import random
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(BASE_DIR)
PROFILE = os.path.join(BASE_DIR, "profile")
SESSION = os.path.join(BASE_DIR, "session.json")
COOKIES = os.path.join(BASE_DIR, "session.cookies")

BROWSERS = [
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
]

QUIET = [
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=Translate,MediaRouter,OptimizationHints",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-popup-blocking",
    "--start-maximized",
    "--window-position=0,0",
]

def find_browser():
    for raw in BROWSERS:
        path = os.path.expandvars(raw)
        if os.path.exists(path):
            return path
    return None

def kill_browser(grace=3.0):
    if os.name == "nt":
        for image in ("chrome.exe", "msedge.exe"):
            subprocess.run(["taskkill", "/F", "/T", "/IM", image],
                           capture_output=True, text=True)
    time.sleep(grace)
    shutil.rmtree(PROFILE, ignore_errors=True)

def new_profile():
    kill_browser()
    os.makedirs(os.path.join(PROFILE, "Default"), exist_ok=True)
    prefs = {
        "profile": {"exit_type": "Normal", "exited_cleanly": True,
                    "default_content_setting_values": {"notifications": 2}},
        "incognito": {"mode_availability": 2},
        "browser": {"has_seen_welcome_page": True, "check_default_browser": False},
        "credentials_enable_service": False,
        "autofill": {"profile_enabled": False},
    }
    try:
        with open(os.path.join(PROFILE, "Default", "Preferences"), "w",
                  encoding="utf-8") as f:
            json.dump(prefs, f)
        with open(os.path.join(PROFILE, "First Run"), "w", encoding="utf-8") as f:
            f.write("1")
    except OSError:
        pass

def open_incognito(url="https://nightrouter.ai/login", extra=()):
    browser = find_browser()
    if not browser:
        return None
    new_profile()
    args = [browser, "--user-data-dir=" + PROFILE, "--incognito"] + QUIET
    args += list(extra)
    args.append(url)
    try:
        return subprocess.Popen(args, creationflags=0x00000008)
    except OSError:
        return None

def wait_for_session(timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(COOKIES) or os.path.exists(SESSION):
            return True
        time.sleep(2)
    return False

def save_cookies_from_profile():
    src = os.path.join(PROFILE, "Default", "Network", "Cookies")
    if not os.path.exists(src):
        return False
    try:
        shutil.copy2(src, COOKIES)
        return True
    except OSError:
        return False

def random_delay(low=2, high=7):
    time.sleep(random.uniform(low, high))

def main():
    print(" abrindo navegador anonimo (perfil novo)...")
    proc = open_incognito()
    if proc is None:
        print(" [!] Chrome/Edge nao encontrado")
        return 2
    print(" logue na conta (Google ou email) e volte aqui")
    print(" quando terminar: feche o navegador. vou seguir sozinho.")
    input(" ENTER quando ja estiver logado: ")
    save_cookies_from_profile()
    kill_browser()
    print(" navegador fechado. perfil descartado.")
    print(" proximo passo: menu > Farm Key")
    return 0

if __name__ == "__main__":
    sys.exit(main())
