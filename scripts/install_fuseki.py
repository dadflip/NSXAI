#!/usr/bin/env python3
"""
Installation d'Apache Jena Fuseki standalone pour NSXAI.

Télécharge le package FUSEKI uniquement (apache-jena-fuseki-{version}.zip),
plus léger que le package Jena complet : il embarque fuseki-server mais pas
riot, tdbloader ou sparql en ligne de commande séparée.

Les opérations TDB2 (chargement des ontologies) passent par le protocole
SPARQL/HTTP de Fuseki lui-même, pas par tdbloader.

Lit la configuration depuis config.yaml à la racine du projet.
"""
import os
import sys
import shutil
import zipfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from config import cfg


# ---------------------------------------------------------------------------
# Téléchargement
# ---------------------------------------------------------------------------

def _download(url: str, dest: Path) -> Path:
    cfg.jena.install_dir.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"[OK] Archive déjà téléchargée : {dest.name}")
        return dest

    print(f"[INFO] Téléchargement Apache Jena Fuseki {cfg.jena.version}...")
    print(f"       {url}")

    def _progress(count, block, total):
        if total > 0:
            pct = min(count * block * 100 // total, 100)
            print(f"\r  {pct}%", end="", flush=True)

    try:
        urllib.request.urlretrieve(url, dest, reporthook=_progress)
        print("\r[OK] Téléchargement terminé")
        return dest
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _extract(zip_path: Path, expected_dir: Path) -> Path:
    if expected_dir.exists():
        print(f"[OK] Déjà extrait : {expected_dir.name}")
        return expected_dir

    print("[INFO] Extraction...")
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(cfg.jena.install_dir)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    if not expected_dir.exists():
        # Lister ce qui a été extrait pour aider au diagnostic
        extracted = [p.name for p in cfg.jena.install_dir.iterdir()]
        print(f"[ERROR] Dossier attendu introuvable : {expected_dir.name}")
        print(f"  Contenu de {cfg.jena.install_dir} : {extracted}")
        sys.exit(1)

    print(f"[OK] Extrait : {expected_dir.name}")
    return expected_dir


# ---------------------------------------------------------------------------
# Permissions (Linux/Mac)
# ---------------------------------------------------------------------------

def _fix_permissions(fuseki_dir: Path):
    """Rend les exécutables Fuseki exécutables sur Linux/Mac."""
    if sys.platform == "win32":
        return
    for candidate in [
        fuseki_dir / "fuseki-server",
        fuseki_dir / "fuseki",          # alias présent dans certaines versions
    ]:
        if candidate.exists():
            try:
                os.chmod(candidate, 0o755)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Installation principale
# ---------------------------------------------------------------------------

def install_fuseki() -> Path:
    zip_name = f"apache-jena-fuseki-{cfg.jena.version}.zip"
    zip_path = cfg.jena.install_dir / zip_name

    _download(cfg.jena.download_url, zip_path)
    fuseki_dir = _extract(zip_path, cfg.jena.dir)
    _fix_permissions(fuseki_dir)

    # Vérification des exécutables
    print()
    bat_ok = cfg.jena.fuseki_bat.exists()
    sh_ok  = cfg.jena.fuseki_sh.exists()
    print(f"  {'[OK]' if bat_ok else '[WARN]'} fuseki-server.bat (Windows)")
    print(f"  {'[OK]' if sh_ok  else '[WARN]'} fuseki-server     (Linux/Mac)")

    if not bat_ok and not sh_ok:
        print(f"\n[WARN] Aucun exécutable trouvé dans {fuseki_dir}")
        print(f"  Contenu : {[p.name for p in fuseki_dir.iterdir()]}")

    return fuseki_dir


# ---------------------------------------------------------------------------
# Déploiement de la config Fuseki
# ---------------------------------------------------------------------------

def deploy_config(fuseki_dir: Path):
    """
    Copie fuseki_config.ttl dans FUSEKI_BASE/config.ttl.

    Fuseki standalone cherche sa configuration dans FUSEKI_BASE/ au démarrage.
    On crée run/ à l'intérieur du dossier Fuseki (FUSEKI_BASE = jena.run_dir).
    """
    src = cfg.ontologies.fuseki_config
    if not src.exists():
        print(f"[ERROR] Config Fuseki introuvable : {src}")
        sys.exit(1)

    cfg.jena.run_dir.mkdir(parents=True, exist_ok=True)
    dest = cfg.jena.run_dir / "config.ttl"
    shutil.copy2(src, dest)
    print(f"[OK] Config : {src.relative_to(ROOT)} -> {dest.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Génération des scripts de démarrage
# ---------------------------------------------------------------------------

def create_scripts(fuseki_dir: Path):
    """
    Génère les scripts de démarrage pour Windows et Linux/Mac.

    Fuseki standalone se lance avec :
      fuseki-server --config=<config.ttl>
    ou en positionnant FUSEKI_BASE et en laissant Fuseki lire config.ttl
    depuis ce répertoire.
    """
    win_dir   = ROOT / "scripts" / "windows"
    linux_dir = ROOT / "scripts" / "linux"
    win_dir.mkdir(parents=True, exist_ok=True)
    linux_dir.mkdir(parents=True, exist_ok=True)

    run_dir_win  = str(cfg.jena.run_dir)
    run_dir_posix = cfg.jena.run_dir.as_posix()
    exe_posix    = cfg.jena.fuseki_sh.as_posix()
    exe_bat      = str(cfg.jena.fuseki_bat)

    # --- Windows .bat ---
    (win_dir / "start_fuseki.bat").write_text(
        "@echo off\n"
        f'set FUSEKI_BASE={run_dir_win}\n'
        f'echo Fuseki : {cfg.fuseki.url}\n'
        f'echo Dataset : {cfg.fuseki.dataset}\n'
        f'cd /d "{fuseki_dir}"\n'
        f'call "{exe_bat}"\n',
        encoding="utf-8",
    )

    # --- Windows PowerShell ---
    (win_dir / "start_fuseki.ps1").write_text(
        f'$env:FUSEKI_BASE = "{run_dir_posix}"\n'
        f'Set-Location "{fuseki_dir.as_posix()}"\n'
        f'& "{exe_bat}"\n',
        encoding="utf-8",
    )

    # --- Linux/Mac shell ---
    sh = linux_dir / "start_fuseki.sh"
    sh.write_text(
        "#!/bin/bash\n"
        f'export FUSEKI_BASE="{run_dir_posix}"\n'
        f'echo "Fuseki : {cfg.fuseki.url}"\n'
        f'echo "Dataset : {cfg.fuseki.dataset}"\n'
        f'cd "{fuseki_dir.as_posix()}" && "{exe_posix}"\n',
        encoding="utf-8",
    )
    if sys.platform != "win32":
        os.chmod(sh, 0o755)

    print("[OK] Scripts : scripts/windows/  scripts/linux/")


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    print("=" * 55)
    print(f"  Installation Apache Jena Fuseki {cfg.jena.version}")
    print("=" * 55)
    print(f"  URL    : {cfg.jena.download_url}")
    print(f"  Dest   : {cfg.jena.dir}")
    print(f"  Base   : {cfg.jena.run_dir}  (FUSEKI_BASE)")
    print()

    fuseki_dir = install_fuseki()
    print()
    deploy_config(fuseki_dir)
    create_scripts(fuseki_dir)

    print()
    print("=" * 55)
    print("[OK] Installation terminée")
    print("=" * 55)
    print()
    print("Démarrer Fuseki :")
    print("  Windows PowerShell : .\\scripts\\windows\\start_fuseki.bat")
    print("  Linux/Mac          : ./scripts/linux/start_fuseki.sh")
    print()
    print("Charger les ontologies (via HTTP Fuseki) :")
    print("  python scripts/load_ontologies.py --clear")
    print()


if __name__ == "__main__":
    main()