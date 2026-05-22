#!/usr/bin/env python3
"""
Charge les ontologies OWL dans Fuseki via son API HTTP (GSP - Graph Store Protocol).

Strategie :
  1. Verifier que Fuseki est actif
  2. Vider le dataset si --clear
  3. Envoyer chaque fichier OWL via HTTP POST sur l'endpoint /data
  4. Afficher les statistiques SPARQL

Fuseki standalone n'embarque pas tdbloader : le chargement passe par HTTP,
ce qui ne necessite pas d'arret/redemarrage de Fuseki.

Usage:
    python scripts/load_ontologies.py
    python scripts/load_ontologies.py --clear    # vide le dataset avant
    python scripts/load_ontologies.py --status   # stats sans charger
"""
import sys
import argparse
import platform
import subprocess
import time
import urllib.request
import urllib.error
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from config import cfg

IS_WINDOWS = platform.system() == "Windows"


# ---------------------------------------------------------------------------
# Fuseki control
# ---------------------------------------------------------------------------

def fuseki_running() -> bool:
    try:
        urllib.request.urlopen(cfg.fuseki.ping_url, timeout=3)
        return True
    except Exception:
        return False


def wait_for_fuseki(timeout: int = 30) -> bool:
    """Attend que Fuseki reponde, jusqu'a timeout secondes."""
    for _ in range(timeout):
        if fuseki_running():
            return True
        time.sleep(1)
    return False


def start_fuseki():
    """Demarre Fuseki en arriere-plan et attend qu'il reponde."""
    script = ROOT / "scripts" / ("windows" if IS_WINDOWS else "linux") / \
             ("start_fuseki.bat" if IS_WINDOWS else "start_fuseki.sh")

    if not script.exists():
        print(f"[ERROR] Script de demarrage introuvable : {script}")
        print("        Lancez d'abord : python scripts/install_fuseki.py")
        sys.exit(1)

    print("  Demarrage de Fuseki...", end=" ", flush=True)
    if IS_WINDOWS:
        subprocess.Popen(
            [str(script)],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            cwd=ROOT,
        )
    else:
        subprocess.Popen(
            ["bash", str(script)], cwd=ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    if wait_for_fuseki():
        print("[OK]")
    else:
        print("[ERROR] Fuseki ne repond pas apres 30s")
        sys.exit(1)


# ---------------------------------------------------------------------------
# GSP — Graph Store Protocol (chargement HTTP)
# ---------------------------------------------------------------------------

# Content-Type par extension de fichier
_MIME = {
    ".owl":  "application/rdf+xml",
    ".rdf":  "application/rdf+xml",
    ".ttl":  "text/turtle",
    ".n3":   "text/n3",
    ".nt":   "application/n-triples",
    ".nq":   "application/n-quads",
    ".trig": "application/trig",
    ".jsonld": "application/ld+json",
}


def _mime_for(path: Path) -> str:
    return _MIME.get(path.suffix.lower(), "application/rdf+xml")


def clear_dataset():
    """Vide le dataset via DELETE sur l'endpoint /data?default."""
    url = f"{cfg.fuseki.data_url}?default"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=cfg.fuseki.timeout):
            pass
        print("  [OK] Dataset vide")
    except urllib.error.HTTPError as e:
        # 404 = dataset vide ou absent — acceptable
        if e.code == 404:
            print("  [OK] Dataset deja vide")
        else:
            print(f"  [ERROR] DELETE /data : HTTP {e.code} {e.reason}")
            sys.exit(1)


def upload_file(owl_file: Path) -> bool:
    """
    Envoie un fichier OWL dans le graph par defaut via POST /data?default.
    Retourne True si succes.
    """
    mime = _mime_for(owl_file)
    data = owl_file.read_bytes()
    url  = f"{cfg.fuseki.data_url}?default"
    req  = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": mime},
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg.fuseki.timeout):
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  [ERROR] HTTP {e.code} : {body[:200]}")
        return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


# ---------------------------------------------------------------------------
# Stats via SPARQL
# ---------------------------------------------------------------------------

def get_stats() -> dict:
    queries = {
        "triples":     "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }",
        "classes":     "SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE { ?c a <http://www.w3.org/2002/07/owl#Class> }",
        "properties":  "SELECT (COUNT(DISTINCT ?p) AS ?n) WHERE { ?p a ?t FILTER(?t IN (<http://www.w3.org/2002/07/owl#ObjectProperty>,<http://www.w3.org/2002/07/owl#DatatypeProperty>)) }",
        "individuals": "SELECT (COUNT(DISTINCT ?i) AS ?n) WHERE { ?i a ?t FILTER(?t != <http://www.w3.org/2002/07/owl#Class> && ?t != <http://www.w3.org/2002/07/owl#ObjectProperty> && ?t != <http://www.w3.org/2002/07/owl#DatatypeProperty>) }",
    }
    stats = {}
    for key, q in queries.items():
        try:
            url = f"{cfg.fuseki.query_url}?query={urllib.request.quote(q)}"
            req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json"})
            with urllib.request.urlopen(req, timeout=cfg.fuseki.timeout) as resp:
                data = json.loads(resp.read())
            stats[key] = int(data["results"]["bindings"][0]["n"]["value"])
        except Exception:
            stats[key] = 0
    return stats


def print_stats(stats: dict):
    print("Dataset Fuseki :")
    print(f"  Triplets   : {stats['triples']}")
    print(f"  Classes    : {stats['classes']}")
    print(f"  Proprietes : {stats['properties']}")
    print(f"  Individus  : {stats['individuals']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Charge les ontologies dans Fuseki via HTTP")
    parser.add_argument("--clear",  action="store_true", help="Vider le dataset avant chargement")
    parser.add_argument("--status", action="store_true", help="Afficher les stats uniquement")
    args = parser.parse_args()

    print("=" * 55)
    print("  Chargement des ontologies -> Fuseki (HTTP/GSP)")
    print("=" * 55)
    print(f"  OWL    : {cfg.ontologies.owl_dir}")
    print(f"  Fuseki : {cfg.fuseki.url}/{cfg.fuseki.dataset}")
    print()

    # --- Fuseki doit etre actif ---
    if not fuseki_running():
        print("[INFO] Fuseki n'est pas actif, demarrage automatique :")
        start_fuseki()
        print()

    # --- Status only ---
    if args.status:
        print_stats(get_stats())
        return 0

    # --- Fichiers OWL ---
    owl_files = sorted(cfg.ontologies.owl_dir.rglob("*.owl"))
    if not owl_files:
        print(f"[ERROR] Aucun fichier .owl dans {cfg.ontologies.owl_dir}")
        return 1

    print(f"Fichiers a charger ({len(owl_files)}) :")
    for f in owl_files:
        print(f"  {f.relative_to(cfg.ontologies.owl_dir)}")
    print()

    # --- Vider si demande ---
    if args.clear:
        print("Vidage du dataset :")
        clear_dataset()
        print()

    # --- Charger via HTTP ---
    print("Chargement :")
    errors = 0
    for owl_file in owl_files:
        label = owl_file.relative_to(cfg.ontologies.owl_dir)
        print(f"  {label} ... ", end="", flush=True)
        if upload_file(owl_file):
            print("[OK]")
        else:
            errors += 1

    print()

    if errors:
        print(f"[WARN] {errors} fichier(s) en erreur sur {len(owl_files)}")
    else:
        print("[OK] Chargement termine")

    print()
    print_stats(get_stats())
    print()

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())