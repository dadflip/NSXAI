#!/usr/bin/env python3
"""NSXAI CLI - Gestionnaire de services (Fuseki + API + Frontend)"""

import sys
import os
import platform
import subprocess
import time
import argparse
import shutil
from pathlib import Path

# Tentative d'import de psutil pour la gestion des processus
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from config import load_config

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOT_DIR    = Path(__file__).parent.absolute()
SCRIPTS_DIR = ROOT_DIR / "scripts"
IS_WINDOWS  = platform.system() == "Windows"

cfg = load_config()


# ---------------------------------------------------------------------------
# Jena
# ---------------------------------------------------------------------------

def is_jena_installed() -> bool:
    return cfg.jena.fuseki_bat.exists() or cfg.jena.fuseki_sh.exists()

def ensure_jena():
    if is_jena_installed():
        print(f"[OK] Apache Jena {cfg.jena.version} déjà installé")
        return
    print(f"[WARN] Apache Jena {cfg.jena.version} non trouvé — installation en cours...")
    install_script = SCRIPTS_DIR / "install_fuseki.py"
    if not install_script.exists():
        print(f"[ERROR] Script d'installation introuvable : {install_script}")
        sys.exit(1)
    result = subprocess.run([sys.executable, str(install_script)], cwd=str(ROOT_DIR))
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

    def _fuseki_ready(self) -> bool:
        try:
            import urllib.request
            urllib.request.urlopen(cfg.fuseki.ping_url, timeout=cfg.fuseki.timeout)
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

    def _kill_process(self, pattern: str, name_label: str):
        """Tue un processus cross-platform en cherchant le pattern dans sa ligne de commande."""
        if not HAS_PSUTIL:
            print(f"[WARN] Impossible d'arrêter proprement {name_label} : module 'psutil' non installé.")
            print("       Installez-le avec `pip install psutil`.")
            return

        found = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and any(pattern in arg for arg in cmdline):
                    proc.kill()
                    print(f"[OK] {name_label} arrêté (PID {proc.info['pid']})")
                    found = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        if not found:
            print(f"[INFO] Aucun processus {name_label} trouvé")

    # --- Fuseki ---

    def start_fuseki(self):
        self.stop_fuseki()
        ensure_jena()
        print("[INFO] Démarrage de Fuseki...")
        env = os.environ.copy()
        env["FUSEKI_BASE"] = str(cfg.jena.run_dir.absolute())
        
        if IS_WINDOWS:
            cmd = f'title NSXAI Fuseki && "{cfg.jena.fuseki_bat.absolute()}"'
        else:
            cmd = ["bash", str(cfg.jena.fuseki_sh.absolute())]
        
        subprocess.Popen(
            cmd,
            cwd=str(cfg.jena.dir.absolute()),
            env=env,
            shell=IS_WINDOWS,
            creationflags=subprocess.CREATE_NEW_CONSOLE if IS_WINDOWS else 0,
        )
        print(f"[OK] Fuseki démarré — {cfg.fuseki.url}")

    def stop_fuseki(self):
        print("[INFO] Arrêt de Fuseki...")
        self._kill_process("fuseki-server", "Fuseki")

    def reset_fuseki(self):
        print("[INFO] Réinitialisation de Fuseki...")
        self.stop_fuseki()
        time.sleep(2)
        
        run_dir = cfg.jena.run_dir
        for d in ["system", "databases"]:
            target = run_dir / d
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
                print(f"   - {d}/ supprimé")
        print("[OK] Fuseki réinitialisé")

    # --- API ---

    def start_api(self):
        self.stop_api()
        print("[INFO] Démarrage de l'API Python...")
        if IS_WINDOWS:
            cmd = f'title NSXAI API && "{sys.executable}" -m nsxai.api.main'
        else:
            cmd = [sys.executable, "-m", "nsxai.api.main"]
        
        subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            shell=IS_WINDOWS,
            creationflags=subprocess.CREATE_NEW_CONSOLE if IS_WINDOWS else 0,
        )
        print(f"[OK] API démarrée — {cfg.api.url}/api/docs")

    def stop_api(self):
        print("[INFO] Arrêt de l'API...")
        self._kill_process("nsxai.api.main", "API")

    # --- Frontend ---

    def start_frontend(self):
        self.stop_frontend()
        app_dir = cfg.frontend.dir
        if not app_dir.exists():
            print(f"[ERROR] Dossier frontend introuvable : {app_dir}")
            return None
        if not (app_dir / "node_modules").exists():
            print("[WARN] node_modules absent — npm install...")
            install = subprocess.run(
                ["npm.cmd", "install"] if IS_WINDOWS else ["npm", "install"],
                cwd=str(app_dir),
                shell=IS_WINDOWS,
            )
            if install.returncode != 0:
                print("[ERROR] npm install a échoué.")
                return None
        print("[INFO] Démarrage du frontend Vite...")
        
        if IS_WINDOWS:
            cmd = 'title NSXAI Frontend && npm run dev'
        else:
            cmd = ["npm", "run", "dev"]
            
        self._frontend_proc = subprocess.Popen(
            cmd,
            cwd=str(app_dir),
            shell=IS_WINDOWS,
            creationflags=subprocess.CREATE_NEW_CONSOLE if IS_WINDOWS else 0,
        )
        print(f"[OK] Frontend démarré — {cfg.frontend.url}")
        return self._frontend_proc

    def stop_frontend(self):
        print("[INFO] Arrêt du frontend...")
        # Arrêter le processus géré par cette instance du CLI
        if self._frontend_proc and self._frontend_proc.poll() is None:
            self._frontend_proc.terminate()
            try:
                self._frontend_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._frontend_proc.kill()
            print("[OK] Frontend arrêté (processus CLI natif)")
            self._frontend_proc = None
            return

        # Arrêter tout autre processus Vite
        self._kill_process("vite", "Frontend")

    # --- Divers ---

    def load_ontologies(self):
        print("[INFO] Chargement des ontologies dans TDB2...")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "load_ontologies.py"), "--clear"],
            cwd=str(ROOT_DIR)
        )
        return result.returncode == 0

    def setup_venv(self):
        print("[INFO] Configuration de l'environnement Python...")
        if not (ROOT_DIR / "venv").exists():
            subprocess.run([sys.executable, "-m", "venv", "venv"], cwd=str(ROOT_DIR), check=True)
        
        pip_exe = ROOT_DIR / "venv" / "Scripts" / "pip.exe" if IS_WINDOWS else ROOT_DIR / "venv" / "bin" / "pip"
        subprocess.run([str(pip_exe), "install", "-r", "requirements.txt"], cwd=str(ROOT_DIR), check=True)
        print("[OK] Environnement configuré")

    def start_all(self):
        print("=" * 50)
        ensure_jena()

        if not (ROOT_DIR / "venv").exists() or not HAS_PSUTIL:
            print("[WARN] Environnement incomplet — configuration des dépendances...")
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
        self.stop_api()
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
  python nsxai_cli.py install          # Installe Apache Jena
  python nsxai_cli.py start all        # Démarre Fuseki + API + Frontend
  python nsxai_cli.py start fuseki     # Démarre uniquement Fuseki
  python nsxai_cli.py start api        # Démarre uniquement l'API
  python nsxai_cli.py start frontend   # Démarre uniquement le frontend
  python nsxai_cli.py stop all         # Arrête tous les services
  python nsxai_cli.py status           # Affiche le statut
  python nsxai_cli.py load             # Charge les ontologies
  python nsxai_cli.py setup            # Configure l'environnement
  python nsxai_cli.py reset            # Réinitialise la base de données
"""

def main():
    parser = argparse.ArgumentParser(
        description="NSXAI CLI - Gestionnaire unifié de services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    parser.add_argument("action", choices=[
        "install", "start", "stop", "restart", "status", "load", "setup", "reset"
    ])
    parser.add_argument("service", nargs="?", choices=["all", "fuseki", "api", "frontend"], default="all")
    args = parser.parse_args()

    m = ServiceManager()

    try:
        match args.action:
            case "install": ensure_jena()
            case "start":
                {"all": m.start_all, "fuseki": m.start_fuseki, "api": m.start_api, "frontend": m.start_frontend}[args.service]()
            case "stop":
                {
                    "all": m.stop_all,
                    "fuseki": m.stop_fuseki,
                    "api": m.stop_api,
                    "frontend": m.stop_frontend,
                }.get(args.service, lambda: None)()
            case "restart":
                stop  = m.stop_all  if args.service == "all" else getattr(m, f"stop_{args.service}")
                start = m.start_all if args.service == "all" else getattr(m, f"start_{args.service}")
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