#!/usr/bin/env python3
"""NSXAI CLI - Gestionnaire de services (Fuseki + API + Frontend)"""

import sys
import platform
import subprocess
import time
import argparse
from pathlib import Path

from config import load_config

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOT_DIR    = Path(__file__).parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
IS_WINDOWS  = platform.system() == "Windows"

cfg = load_config()


# ---------------------------------------------------------------------------
# Jena
# ---------------------------------------------------------------------------

def is_jena_installed() -> bool:
    d = cfg.jena.dir
    return (d / "bin" / "fuseki-server").exists() or (d / "bat" / "fuseki-server.bat").exists()


def ensure_jena():
    if is_jena_installed():
        print(f"[OK] Apache Jena {cfg.jena.version} déjà installé")
        return
    print(f"[WARN] Apache Jena {cfg.jena.version} non trouvé — installation en cours...")
    install_script = SCRIPTS_DIR / "install_fuseki.py"
    if not install_script.exists():
        print(f"[ERROR] Script d'installation introuvable : {install_script}")
        sys.exit(1)
    result = subprocess.run([sys.executable, str(install_script)], cwd=ROOT_DIR)
    if result.returncode != 0:
        print("[ERROR] L'installation de Jena a échoué.")
        sys.exit(1)
    print("[OK] Apache Jena installé")


# ---------------------------------------------------------------------------
# ServiceManager
# ---------------------------------------------------------------------------

class ServiceManager:

    def __init__(self):
        self._frontend_proc: subprocess.Popen | None = None

    def _script(self, name: str) -> Path:
        sub = "windows" if IS_WINDOWS else "linux"
        ext = ".bat"    if IS_WINDOWS else ".sh"
        return SCRIPTS_DIR / sub / f"{name}{ext}"

    def _run(self, name: str, background=False):
        path = self._script(name)
        if not path.exists():
            print(f"[ERROR] Script non trouvé : {path}")
            return None
        cmd = [str(path)] if IS_WINDOWS else ["bash", str(path)]
        if background:
            return subprocess.Popen(
                cmd, cwd=ROOT_DIR,
                creationflags=subprocess.CREATE_NEW_CONSOLE if IS_WINDOWS else 0,
            )
        return subprocess.run(cmd, cwd=ROOT_DIR)

    def _fuseki_ready(self) -> bool:
        try:
            import urllib.request
            urllib.request.urlopen(cfg.fuseki.url, timeout=cfg.fuseki.timeout)
            return True
        except Exception:
            return False

    def _api_ready(self) -> bool:
        try:
            import urllib.request
            r = urllib.request.urlopen(f"{cfg.api.url}/health", timeout=2)
            return r.status == 200
        except Exception:
            return False

    # --- Fuseki ---

    def start_fuseki(self):
        ensure_jena()
        print("[INFO] Démarrage de Fuseki...")
        self._run("start_fuseki", background=True)
        print(f"[OK] Fuseki démarré — {cfg.fuseki.url}")

    def stop_fuseki(self):
        print("[INFO] Arrêt de Fuseki...")
        self._run("stop_fuseki")
        print("[OK] Fuseki arrêté")

    def reset_fuseki(self):
        print("[INFO] Réinitialisation de Fuseki...")
        self._run("reset_fuseki")
        print("[OK] Fuseki réinitialisé")

    # --- API ---

    def start_api(self):
        print("[INFO] Démarrage de l'API Python...")
        self._run("start_api", background=True)
        print(f"[OK] API démarrée — {cfg.api.url}/api/docs")

    # --- Frontend ---

    def _npm_cmd(self) -> list[str]:
        return ["npm.cmd", "run", "dev"] if IS_WINDOWS else ["npm", "run", "dev"]

    def start_frontend(self):
        app_dir = cfg.frontend.dir
        if not app_dir.exists():
            print(f"[ERROR] Dossier frontend introuvable : {app_dir}")
            return None
        if not (app_dir / "node_modules").exists():
            print("[WARN] node_modules absent — npm install...")
            install = subprocess.run(
                ["npm.cmd", "install"] if IS_WINDOWS else ["npm", "install"],
                cwd=app_dir,
                shell=IS_WINDOWS,
            )
            if install.returncode != 0:
                print("[ERROR] npm install a échoué.")
                return None
        print("[INFO] Démarrage du frontend Vite...")
        self._frontend_proc = subprocess.Popen(
            self._npm_cmd(),
            cwd=app_dir,
            shell=IS_WINDOWS,
            creationflags=subprocess.CREATE_NEW_CONSOLE if IS_WINDOWS else 0,
        )
        print(f"[OK] Frontend démarré — {cfg.frontend.url}")
        return self._frontend_proc

    def stop_frontend(self):
        if self._frontend_proc and self._frontend_proc.poll() is None:
            self._frontend_proc.terminate()
            try:
                self._frontend_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._frontend_proc.kill()
            print("[OK] Frontend arrêté")
        self._frontend_proc = None

    # --- Divers ---

    def load_ontologies(self):
        print("[INFO] Chargement des ontologies dans TDB2...")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "load_ontologies.py"), "--clear"],
            cwd=ROOT_DIR
        )
        return result.returncode == 0

    def setup_venv(self):
        print("[INFO] Configuration de l'environnement Python...")
        self._run("setup_venv")
        print("[OK] Environnement configuré")

    # --- start_all / stop_all / status ---

    def start_all(self):
        print("=" * 50)
        ensure_jena()

        if not (ROOT_DIR / "venv").exists():
            print("[WARN] Environnement Python absent — configuration...")
            self.setup_venv()

        self.start_fuseki()
        print("[INFO] Attente de Fuseki", end="", flush=True)
        for _ in range(cfg.fuseki.timeout):
            time.sleep(1)
            print(".", end="", flush=True)
            if self._fuseki_ready():
                break
        print()

        self.start_api()
        print("=" * 50)
        print(f"  Fuseki   : {cfg.fuseki.url}")
        print(f"  API      : {cfg.api.url}/api/docs")
        print("=" * 50)

    def start_dev(self):
        """Démarre Fuseki, l'API et le frontend Vite."""
        self.start_all()
        print("[INFO] Attente de l'API", end="", flush=True)
        for _ in range(15):
            time.sleep(1)
            print(".", end="", flush=True)
            if self._api_ready():
                break
        print()
        self.start_frontend()
        print("=" * 50)
        print(f"  Fuseki   : {cfg.fuseki.url}")
        print(f"  API      : {cfg.api.url}/api/docs")
        print(f"  Frontend : {cfg.frontend.url}")
        print("=" * 50)

    def stop_all(self):
        self.stop_frontend()
        self.stop_fuseki()
        print("[OK] Tous les services arrêtés")

    def status(self):
        fuseki_ok = self._fuseki_ready()
        api_ok    = self._api_ready()
        print("=" * 50)
        print(f"Jena   : {'[OK] installé'  if is_jena_installed() else '[--] non installé'}")
        print(f"Fuseki : {'[OK] actif  — ' + cfg.fuseki.url       if fuseki_ok else '[--] arrêté'}")
        print(f"API    : {'[OK] active — ' + cfg.api.url + '/api/docs' if api_ok else '[--] arrêtée'}")
        print("=" * 50)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

EPILOG = """
Exemples :
  python nsxai_cli.py dev              # Fuseki + API + frontend Vite
  python nsxai_cli.py install          # Installe Apache Jena
  python nsxai_cli.py start all        # Démarre Fuseki + API
  python nsxai_cli.py start fuseki     # Démarre uniquement Fuseki
  python nsxai_cli.py start api        # Démarre uniquement l'API
  python nsxai_cli.py start frontend   # Démarre uniquement le frontend
  python nsxai_cli.py stop all         # Arrête tous les services
  python nsxai_cli.py status           # Affiche le statut
  python nsxai_cli.py load             # Charge les ontologies
  python nsxai_cli.py setup            # Configure l'environnement
"""

def main():
    parser = argparse.ArgumentParser(
        description="NSXAI CLI - Gestionnaire de services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    parser.add_argument("action", choices=[
        "install", "start", "stop", "restart", "status", "load", "setup", "reset", "dev"
    ])
    parser.add_argument("service", nargs="?", choices=["all", "fuseki", "api", "frontend"], default="all")
    args = parser.parse_args()

    m = ServiceManager()

    try:
        match args.action:
            case "install": ensure_jena()
            case "dev": m.start_dev()
            case "start":
                {"all": m.start_all, "fuseki": m.start_fuseki, "api": m.start_api, "frontend": m.start_frontend}[args.service]()
            case "stop":
                {
                    "all": m.stop_all,
                    "fuseki": m.stop_fuseki,
                    "frontend": m.stop_frontend,
                }.get(args.service, lambda: None)()
            case "restart":
                stop  = m.stop_all  if args.service == "all" else m.stop_fuseki
                start = m.start_all if args.service == "all" else m.start_fuseki
                stop(); time.sleep(2); start()
            case "status": m.status()
            case "load":   m.load_ontologies()
            case "setup":  m.setup_venv()
            case "reset":  m.reset_fuseki()

    except KeyboardInterrupt:
        print("\n[INFO] Interruption")
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()