"""
Chargement et réinitialisation du dataset Fuseki (aligné sur scripts/load_ontologies.py).
"""
from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..config import config

_MIME = {
    ".owl": "application/rdf+xml",
    ".rdf": "application/rdf+xml",
    ".ttl": "text/turtle",
    ".n3": "text/n3",
    ".nt": "application/n-triples",
}


def _mime_for(path: Path) -> str:
    return _MIME.get(path.suffix.lower(), "application/rdf+xml")


def find_ontology_files(owl_dir: Path) -> List[Path]:
    files: List[Path] = []
    for ext in (".owl", ".ttl", ".rdf"):
        files.extend(sorted(owl_dir.rglob(f"*{ext}")))
    return files


def clear_dataset_http() -> Tuple[bool, str]:
    """Vide le graphe par défaut via GSP DELETE."""
    url = f"{config.fuseki.data_url}?default"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=config.fuseki.timeout):
            return True, "Dataset vidé"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return True, "Dataset déjà vide"
        return False, f"DELETE /data : HTTP {e.code} {e.reason}"
    except Exception as e:
        return False, str(e)


def upload_ontology_file(path: Path) -> Tuple[bool, str]:
    url = f"{config.fuseki.data_url}?default"
    data = path.read_bytes()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": _mime_for(path)},
    )
    try:
        with urllib.request.urlopen(req, timeout=config.fuseki.timeout):
            return True, ""
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return False, f"HTTP {e.code}: {body[:300]}"
    except Exception as e:
        return False, str(e)


def reload_ontology_store(clear_sparql: bool = True) -> Dict[str, Any]:
    """
    Réinitialise le triplestore : vidage puis rechargement des OWL/TTL sources.
    """
    from .fuseki import fuseki_client

    owl_dir = config.ontologies.owl_dir
    if not owl_dir.exists():
        return {"success": False, "error": f"Répertoire introuvable : {owl_dir}"}

    files = find_ontology_files(owl_dir)
    if not files:
        return {"success": False, "error": f"Aucun fichier OWL/TTL dans {owl_dir}"}

    errors: List[str] = []

    if clear_sparql:
        try:
            fuseki_client.update("CLEAR ALL")
        except Exception as e:
            errors.append(f"SPARQL CLEAR: {e}")

    ok_del, msg_del = clear_dataset_http()
    if not ok_del:
        errors.append(msg_del)

    loaded = 0
    for f in files:
        ok, err = upload_ontology_file(f)
        if ok:
            loaded += 1
        else:
            errors.append(f"{f.name}: {err}")

    if loaded == 0:
        return {
            "success": False,
            "error": "Aucun fichier chargé",
            "details": errors,
            "files": len(files),
        }

    try:
        stats = fuseki_client.get_stats()
        triples = stats.get("triples", 0)
    except Exception:
        triples = 0

    return {
        "success": len(errors) == 0 or loaded > 0,
        "size": triples,
        "filesLoaded": loaded,
        "filesTotal": len(files),
        "warnings": errors if errors else None,
    }
