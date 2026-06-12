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

# Activer ANSI sur Windows si nécessaire
if platform.system() == "Windows":
    os.system("")

class Colors:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

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
        print(f"{Colors.GREEN}[OK]{Colors.ENDC} Apache Jena {cfg.jena.version} déjà installé")
        return
    print(f"{Colors.YELLOW}[WARN]{Colors.ENDC} Apache Jena {cfg.jena.version} non trouvé — installation en cours...")
    install_script = SCRIPTS_DIR / "install_fuseki.py"
    if not install_script.exists():
        print(f"{Colors.RED}[ERROR]{Colors.ENDC} Script d'installation introuvable : {install_script}")
        sys.exit(1)
    result = subprocess.run([sys.executable, str(install_script)], cwd=str(ROOT_DIR))
    if result.returncode != 0:
        print(f"{Colors.RED}[ERROR]{Colors.ENDC} L'installation de Jena a échoué.")
        sys.exit(1)
    print(f"{Colors.GREEN}[OK]{Colors.ENDC} Apache Jena installé")


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
        """Tue un processus de manière ciblée en vérifiant qu'il appartient bien à NSXAI (ROOT_DIR)."""
        if not HAS_PSUTIL:
            print(f"{Colors.YELLOW}[WARN]{Colors.ENDC} Impossible d'arrêter proprement {name_label} : 'psutil' non installé.")
            print(f"       Installez-le avec `pip install psutil`.")
            return

        found = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
            try:
                cmdline = proc.info.get('cmdline')
                cwd = proc.info.get('cwd')
                
                # Vérification stricte du répertoire de travail pour ne pas tuer des process externes
                if cwd:
                    try:
                        # Est-ce que le processus tourne dans un sous-dossier de ROOT_DIR ?
                        is_our_proc = Path(cwd).resolve().is_relative_to(ROOT_DIR.resolve())
                    except AttributeError:
                        # Fallback pour Python < 3.9
                        try:
                            Path(cwd).resolve().relative_to(ROOT_DIR.resolve())
                            is_our_proc = True
                        except ValueError:
                            is_our_proc = False
                            
                    if not is_our_proc:
                        continue # Ce processus appartient à un autre projet

                if cmdline and any(pattern in arg for arg in cmdline):
                    proc.kill()
                    print(f"{Colors.GREEN}[OK]{Colors.ENDC} {name_label} arrêté (PID {proc.info['pid']})")
                    found = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        if not found:
            print(f"{Colors.BLUE}[INFO]{Colors.ENDC} Aucun processus {name_label} trouvé")

    # --- Fuseki ---

    def start_fuseki(self):
        self.stop_fuseki()
        ensure_jena()
        print(f"{Colors.BLUE}[INFO]{Colors.ENDC} Démarrage de Fuseki...")
        env = os.environ.copy()
        env["FUSEKI_BASE"] = str(cfg.jena.run_dir.absolute())
        
        if IS_WINDOWS:
            cmd = 'cmd.exe /k "title NSXAI Fuseki && call fuseki-server.bat"'
        else:
            cmd = ["bash", str(cfg.jena.fuseki_sh.absolute())]
        
        subprocess.Popen(
            cmd,
            cwd=str(cfg.jena.dir.absolute()),
            env=env,
            shell=False,
            creationflags=subprocess.CREATE_NEW_CONSOLE if IS_WINDOWS else 0,
        )
        print(f"{Colors.GREEN}[OK]{Colors.ENDC} Fuseki démarré — {cfg.fuseki.url}")

    def stop_fuseki(self):
        print(f"{Colors.BLUE}[INFO]{Colors.ENDC} Arrêt de Fuseki...")
        self._kill_process("fuseki-server", "Fuseki")

    def reset_fuseki(self):
        print(f"{Colors.BLUE}[INFO]{Colors.ENDC} Réinitialisation de Fuseki...")
        self.stop_fuseki()
        time.sleep(2)
        
        run_dir = cfg.jena.run_dir
        for d in ["system", "databases"]:
            target = run_dir / d
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
                print(f"   - {d}/ supprimé")
        print(f"{Colors.GREEN}[OK]{Colors.ENDC} Fuseki réinitialisé")

    # --- API ---

    def start_api(self):
        self.stop_api()
        print(f"{Colors.BLUE}[INFO]{Colors.ENDC} Démarrage de l'API Python...")
        if IS_WINDOWS:
            cmd = f'cmd.exe /k "title NSXAI API && "{sys.executable}" -m nsxai.api.main"'
        else:
            cmd = [sys.executable, "-m", "nsxai.api.main"]
        
        subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            shell=False,
            creationflags=subprocess.CREATE_NEW_CONSOLE if IS_WINDOWS else 0,
        )
        print(f"{Colors.GREEN}[OK]{Colors.ENDC} API démarrée — {cfg.api.url}/api/docs")

    def stop_api(self):
        print(f"{Colors.BLUE}[INFO]{Colors.ENDC} Arrêt de l'API...")
        self._kill_process("nsxai.api.main", "API")

    # --- Frontend ---

    def start_frontend(self):
        self.stop_frontend()
        app_dir = cfg.frontend.dir
        if not app_dir.exists():
            print(f"{Colors.RED}[ERROR]{Colors.ENDC} Dossier frontend introuvable : {app_dir}")
            return None
        if not (app_dir / "node_modules").exists():
            print(f"{Colors.YELLOW}[WARN]{Colors.ENDC} node_modules absent — npm install...")
            install = subprocess.run(
                ["npm.cmd", "install"] if IS_WINDOWS else ["npm", "install"],
                cwd=str(app_dir),
                shell=IS_WINDOWS,
            )
            if install.returncode != 0:
                print(f"{Colors.RED}[ERROR]{Colors.ENDC} npm install a échoué.")
                return None
        print(f"{Colors.BLUE}[INFO]{Colors.ENDC} Démarrage du frontend Vite...")
        
        if IS_WINDOWS:
            cmd = 'cmd.exe /k "title NSXAI Frontend && npm run dev"'
        else:
            cmd = ["npm", "run", "dev"]
            
        self._frontend_proc = subprocess.Popen(
            cmd,
            cwd=str(app_dir),
            shell=False,
            creationflags=subprocess.CREATE_NEW_CONSOLE if IS_WINDOWS else 0,
        )
        print(f"{Colors.GREEN}[OK]{Colors.ENDC} Frontend démarré — {cfg.frontend.url}")
        return self._frontend_proc

    def stop_frontend(self):
        print(f"{Colors.BLUE}[INFO]{Colors.ENDC} Arrêt du frontend...")
        if self._frontend_proc and self._frontend_proc.poll() is None:
            self._frontend_proc.terminate()
            try:
                self._frontend_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._frontend_proc.kill()
            print(f"{Colors.GREEN}[OK]{Colors.ENDC} Frontend arrêté (processus CLI natif)")
            self._frontend_proc = None
            return

        self._kill_process("vite", "Frontend")

    # --- Divers ---

    def load_ontologies(self):
        print(f"{Colors.BLUE}[INFO]{Colors.ENDC} Chargement des ontologies dans TDB2...")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "load_ontologies.py"), "--clear"],
            cwd=str(ROOT_DIR)
        )
        return result.returncode == 0

    def setup_venv(self):
        print(f"{Colors.BLUE}[INFO]{Colors.ENDC} Configuration de l'environnement Python...")
        if not (ROOT_DIR / "venv").exists():
            subprocess.run([sys.executable, "-m", "venv", "venv"], cwd=str(ROOT_DIR), check=True)
        
        pip_exe = ROOT_DIR / "venv" / "Scripts" / "pip.exe" if IS_WINDOWS else ROOT_DIR / "venv" / "bin" / "pip"
        subprocess.run([str(pip_exe), "install", "-r", "requirements.txt"], cwd=str(ROOT_DIR), check=True)
        print(f"{Colors.GREEN}[OK]{Colors.ENDC} Environnement configuré")

    def start_all(self):
        print("=" * 50)
        ensure_jena()

        if not (ROOT_DIR / "venv").exists() or not HAS_PSUTIL:
            print(f"{Colors.YELLOW}[WARN]{Colors.ENDC} Environnement incomplet — configuration des dépendances...")
            self.setup_venv()

        self.start_fuseki()
        print(f"{Colors.BLUE}[INFO]{Colors.ENDC} Attente de Fuseki", end="", flush=True)
        for _ in range(cfg.fuseki.timeout):
            time.sleep(1)
            print(".", end="", flush=True)
            if self._fuseki_ready():
                break
        print()

        self.start_api()
        print(f"{Colors.BLUE}[INFO]{Colors.ENDC} Attente de l'API", end="", flush=True)
        for _ in range(15):
            time.sleep(1)
            print(".", end="", flush=True)
            if self._api_ready():
                break
        print()
        
        self.start_frontend()
        print("=" * 50)
        print(f"  {Colors.BOLD}Fuseki{Colors.ENDC}   : {cfg.fuseki.url}")
        print(f"  {Colors.BOLD}API{Colors.ENDC}      : {cfg.api.url}/api/docs")
        print(f"  {Colors.BOLD}Frontend{Colors.ENDC} : {cfg.frontend.url}")
        print("=" * 50)

    def run_dev(self):
        """Mode superviseur de développement (foreground avec redirection simple)"""
        print("=" * 50)
        ensure_jena()

        if not (ROOT_DIR / "venv").exists() or not HAS_PSUTIL:
            print(f"{Colors.YELLOW}[WARN]{Colors.ENDC} Environnement incomplet — configuration des dépendances...")
            self.setup_venv()

        print(f"{Colors.BLUE}[INFO]{Colors.ENDC} Lancement du mode DEV ({Colors.BOLD}Ctrl+C pour tout arrêter{Colors.ENDC})...")
        self.stop_all() # Nettoyage initial
        
        procs = []
        
        # 1. Fuseki
        env = os.environ.copy()
        env["FUSEKI_BASE"] = str(cfg.jena.run_dir.absolute())
        
        if IS_WINDOWS:
            fuseki_cmd = ["cmd.exe", "/c", "fuseki-server.bat"]
        else:
            fuseki_cmd = ["bash", str(cfg.jena.fuseki_sh.absolute())]
            
        p_fuseki = subprocess.Popen(fuseki_cmd, cwd=str(cfg.jena.dir.absolute()), env=env, shell=False)
        procs.append(("Fuseki", p_fuseki))
        
        # 2. API
        api_cmd = [sys.executable, "-m", "nsxai.api.main"]
        p_api = subprocess.Popen(api_cmd, cwd=str(ROOT_DIR), shell=False)
        procs.append(("API", p_api))
        
        # 3. Frontend
        app_dir = cfg.frontend.dir
        if not (app_dir / "node_modules").exists():
            print(f"{Colors.YELLOW}[WARN]{Colors.ENDC} node_modules absent — npm install...")
            subprocess.run(["npm.cmd" if IS_WINDOWS else "npm", "install"], cwd=str(app_dir), shell=IS_WINDOWS)
            
        front_cmd = ["npm.cmd" if IS_WINDOWS else "npm", "run", "dev"]
        p_front = subprocess.Popen(front_cmd, cwd=str(app_dir), shell=False)
        procs.append(("Frontend", p_front))
        
        print("=" * 50)
        print(f"  {Colors.BOLD}Fuseki{Colors.ENDC}   : {cfg.fuseki.url}")
        print(f"  {Colors.BOLD}API{Colors.ENDC}      : {cfg.api.url}/api/docs")
        print(f"  {Colors.BOLD}Frontend{Colors.ENDC} : {cfg.frontend.url}")
        print("=" * 50)
        print(f"{Colors.BLUE}[INFO]{Colors.ENDC} Services en cours d'exécution dans ce terminal.")
        
        try:
            while True:
                time.sleep(1)
                # Vérifier si l'un des processus a crashé
                for name, p in procs:
                    if p.poll() is not None:
                        print(f"{Colors.RED}[ERROR]{Colors.ENDC} Le service {name} s'est arrêté inopinément (code {p.returncode}).")
                        raise KeyboardInterrupt # Déclenche l'arrêt global
        except KeyboardInterrupt:
            print(f"\n{Colors.BLUE}[INFO]{Colors.ENDC} Interruption : Arrêt de tous les services (DEV mode)...")
            for name, p in procs:
                if p.poll() is None:
                    p.terminate()
            
            # Laisser un court instant pour la terminaison propre
            for name, p in procs:
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
            print(f"{Colors.GREEN}[OK]{Colors.ENDC} Tous les processus DEV ont été arrêtés proprement.")

    def stop_all(self):
        self.stop_frontend()
        self.stop_api()
        self.stop_fuseki()
        print(f"{Colors.GREEN}[OK]{Colors.ENDC} Tous les services arrêtés")

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
  python nsxai_cli.py dev              # Démarre tous les services en mode superviseur (foreground)
  python nsxai_cli.py start all        # Démarre Fuseki + API + Frontend (background / fenêtres séparées)
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
        "dev", "install", "start", "stop", "restart", "status", "load", "setup", "reset"
    ])
    parser.add_argument("service", nargs="?", choices=["all", "fuseki", "api", "frontend"], default="all")
    args = parser.parse_args()

    m = ServiceManager()

    try:
        if args.action == "dev":
            m.run_dev()
        elif args.action == "install":
            ensure_jena()
        elif args.action == "start":
            {"all": m.start_all, "fuseki": m.start_fuseki, "api": m.start_api, "frontend": m.start_frontend}[args.service]()
        elif args.action == "stop":
            {
                "all": m.stop_all,
                "fuseki": m.stop_fuseki,
                "api": m.stop_api,
                "frontend": m.stop_frontend,
            }.get(args.service, lambda: None)()
        elif args.action == "restart":
            stop  = m.stop_all  if args.service == "all" else getattr(m, f"stop_{args.service}")
            start = m.start_all if args.service == "all" else getattr(m, f"start_{args.service}")
            stop()
            time.sleep(2)
            start()
        elif args.action == "status":
            m.status()
        elif args.action == "load":
            m.load_ontologies()
        elif args.action == "setup":
            m.setup_venv()
        elif args.action == "reset":
            m.reset_fuseki()

    except KeyboardInterrupt:
        print(f"\n{Colors.BLUE}[INFO]{Colors.ENDC} Interruption")
        sys.exit(0)
    except Exception as e:
        print(f"{Colors.RED}[ERROR]{Colors.ENDC} {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()