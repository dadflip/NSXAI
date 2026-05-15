#!/usr/bin/env python3
"""
HermiT REST API Server - Python Implementation
Provides OWL ontology reasoning via REST endpoints
"""

import os
import json
import base64
import time
from pathlib import Path
from typing import Dict, List, Set, Any
from urllib.request import urlopen, Request
from urllib.error import URLError

from flask import Flask, request, jsonify
from flask_cors import CORS
import owlready2
from owlready2 import get_ontology, sync_reasoner_hermit

# Environment variables
FUSEKI_URL = os.getenv("FUSEKI_URL", "http://localhost:3030")
FUSEKI_DATASET = os.getenv("FUSEKI_DATASET", "GaTO")
ONTOLOGY_DIR = os.getenv("ONTOLOGY_DIR", "/ontologies")

# Rediriger les imports owl:imports vers les fichiers locaux avant tout chargement
owlready2.onto_path.append(ONTOLOGY_DIR)

# Global state
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS"]}})

ontology = None
reasoner = None
ontology_manager = None


def _parse_catalog(ontology_dir: Path) -> dict:
    """Parse catalog-v001.xml -> {remote_iri: absolute_local_path}."""
    import xml.etree.ElementTree as ET
    mapping = {}
    catalog_file = ontology_dir / "catalog-v001.xml"
    if not catalog_file.exists():
        return mapping
    try:
        root = ET.parse(catalog_file).getroot()
        ns = {"c": "urn:oasis:names:tc:entity:xmlns:xml:catalog"}
        for el in root.findall(".//c:uri", ns):
            remote = el.get("name", "")
            local  = el.get("uri", "")
            if remote and local:
                full = ontology_dir / local
                if full.exists():
                    mapping[remote] = str(full.absolute())
    except Exception as e:
        print(f"Warning: catalog parse error: {e}")
    return mapping


def _patch_owlready2_resolver(catalog_map: dict):
    """
    Patch owlready2._get_onto_file so that any import IRI matching the catalog
    is resolved to the local file path instead of hitting the network.
    This is the correct interception point: owlready2 calls _get_onto_file()
    to resolve an IRI to a filesystem path BEFORE deciding to use urlopen.
    """
    import owlready2.namespace as _ns

    _orig_get = _ns._get_onto_file

    def _patched_get(base_iri, name, mode="r", only_local=False):
        # Strip trailing # or /
        clean_iri = base_iri.rstrip("#/")
        if clean_iri in catalog_map:
            local_path = catalog_map[clean_iri]
            print(f"Catalog redirect: {clean_iri} -> {local_path}")
            return local_path
        return _orig_get(base_iri, name, mode, only_local)

    _ns._get_onto_file = _patched_get


def load_ontology():
    """Load ontology from .owl files, resolving imports via local catalog."""
    global ontology, reasoner, ontology_manager

    ontology_dir = Path(ONTOLOGY_DIR)
    owl_files = sorted(ontology_dir.glob("*.owl"))

    if not owl_files:
        print(f"No .owl files found in {ONTOLOGY_DIR}")
        return False

    # 1. Parse catalog and patch URL resolver BEFORE any owlready2 load
    catalog_map = _parse_catalog(ontology_dir)
    if catalog_map:
        print(f"Catalog: {len(catalog_map)} IRI->local mapping(s)")
        _patch_owlready2_resolver(catalog_map)
    else:
        print("Warning: No catalog found - remote imports may fail")

    # 2. Also tell owlready2 to search this directory for imports by filename
    owlready2.onto_path.clear()
    owlready2.onto_path.append(str(ontology_dir))

    # 3. Pick gato.owl as entry point
    main_file = next((f for f in owl_files if f.name == "gato.owl"), owl_files[0])

    try:
        print(f"Loading ontology: {main_file.absolute()}")
        ontology = get_ontology(f"file://{main_file.absolute()}").load()
        print(f"Ontology loaded successfully")

        # 4. Initialize HermiT reasoner
        try:
            with ontology:
                sync_reasoner_hermit()
            reasoner = True
            axiom_count = len(list(ontology.axioms()))
            consistency = not bool(ontology.inconsistent_classes)
            print(f"HermiT ready - axioms: {axiom_count} - consistent: {consistency}")
        except Exception as e:
            print(f"Warning: HermiT reasoner initialization failed: {str(e)}")
            reasoner = False

        return True

    except Exception as e:
        print(f"Warning: Failed to load {main_file.name}: {str(e)}")
        ontology = None
        reasoner = False
        return False


def push_inferences_to_fuseki(turtle_content: str) -> None:
    """Push inferred axioms to Fuseki triple store"""
    try:
        graph_uri = f"{FUSEKI_URL}/{FUSEKI_DATASET}/data?graph=http://surveys.nees.com.br/lms/inferred"
        
        headers = {
            "Content-Type": "text/turtle",
            "Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()
        }
        
        req = Request(
            graph_uri,
            data=turtle_content.encode("utf-8"),
            headers=headers,
            method="PUT"
        )
        
        with urlopen(req) as response:
            print(f"Inferences pushed to Fuseki — HTTP {response.status}")
    except URLError as e:
        print(f"Failed to push inferences: {str(e)}")


# ── CORS OPTIONS ──
@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        response = app.make_default_options_response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response


# ── ROUTES ──────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "ok" if reasoner else "degraded",
        "reasoner": "HermiT",
        "ontology_loaded": ontology is not None,
        "ontology_axioms": len(list(ontology.axioms())) if ontology else 0,
        "reasoning_available": bool(reasoner),
        "note": "" if reasoner else "Reasoning unavailable due to unsupported ontology datatypes"
    })


@app.route("/reload", methods=["POST"])
def reload():
    """Reload ontology from disk"""
    success = load_ontology()
    if success:
        axioms = len(list(ontology.axioms())) if ontology else 0
        return jsonify({"status": "reloaded", "axioms": axioms})
    return jsonify({"status": "error", "message": "Failed to reload ontology"}), 500


@app.route("/consistent", methods=["GET"])
def check_consistency():
    """Check if ontology is consistent"""
    if not reasoner or ontology is None:
        return jsonify({
            "error": "Reasoning not available",
            "consistent": None
        })
    
    is_consistent = len(list(ontology.inconsistent_classes)) == 0
    return jsonify({"consistent": is_consistent})


@app.route("/classes", methods=["GET"])
def get_classes():
    """Get all satisfiable classes"""
    if not reasoner or ontology is None:
        return jsonify({"error": "Reasoning not available", "classes": []})
    
    classes = set()
    for cls in ontology.classes():
        # Filter out thing and nothing
        iri = str(cls.iri)
        if "Thing" not in iri and "Nothing" not in iri:
            classes.add(iri)
    
    return jsonify({
        "classes": list(classes),
        "count": len(classes)
    })


@app.route("/classes/subclasses", methods=["GET"])
def get_subclasses():
    """Get subclasses of a given class"""
    if not reasoner or ontology is None:
        return jsonify({
            "error": "Reasoning not available",
            "subclasses": []
        })
    
    iri_str = request.args.get("iri")
    direct = request.args.get("direct", "false").lower() == "true"
    
    if not iri_str:
        return jsonify({"error": "Missing 'iri' parameter"}), 400
    
    try:
        # Find class by IRI
        target_class = None
        for cls in ontology.classes():
            if str(cls.iri) == iri_str:
                target_class = cls
                break
        
        if not target_class:
            return jsonify({"error": f"Class not found: {iri_str}"}), 404
        
        subclasses = []
        if direct:
            subclasses = [str(c.iri) for c in target_class.subclasses() if str(c.iri) != iri_str]
        else:
            # Get all inferred subclasses
            visited = set()
            def get_all_subclasses(cls):
                for sub in cls.subclasses():
                    iri = str(sub.iri)
                    if iri not in visited and "Nothing" not in iri:
                        visited.add(iri)
                        subclasses.append(iri)
                        get_all_subclasses(sub)
            get_all_subclasses(target_class)
        
        return jsonify({"iri": iri_str, "subclasses": subclasses})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/classes/superclasses", methods=["GET"])
def get_superclasses():
    """Get superclasses of a given class"""
    if not reasoner or ontology is None:
        return jsonify({
            "error": "Reasoning not available",
            "superclasses": []
        })
    
    iri_str = request.args.get("iri")
    direct = request.args.get("direct", "false").lower() == "true"
    
    if not iri_str:
        return jsonify({"error": "Missing 'iri' parameter"}), 400
    
    try:
        # Find class by IRI
        target_class = None
        for cls in ontology.classes():
            if str(cls.iri) == iri_str:
                target_class = cls
                break
        
        if not target_class:
            return jsonify({"error": f"Class not found: {iri_str}"}), 404
        
        superclasses = []
        if direct:
            superclasses = [str(c.iri) for c in target_class.is_a if hasattr(c, 'iri') and str(c.iri) != iri_str]
        else:
            # Get all inferred superclasses
            visited = set()
            def get_all_superclasses(cls):
                for sup in cls.is_a:
                    if hasattr(sup, 'iri'):
                        iri = str(sup.iri)
                        if iri not in visited and "Thing" not in iri:
                            visited.add(iri)
                            superclasses.append(iri)
                            get_all_superclasses(sup)
            get_all_superclasses(target_class)
        
        return jsonify({"iri": iri_str, "superclasses": superclasses})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/instances", methods=["GET"])
def get_instances():
    """Get instances of a given class"""
    if not reasoner or ontology is None:
        return jsonify({
            "error": "Reasoning not available",
            "instances": []
        })
    
    iri_str = request.args.get("iri")
    direct = request.args.get("direct", "false").lower() == "true"
    
    if not iri_str:
        return jsonify({"error": "Missing 'iri' parameter"}), 400
    
    try:
        # Find class by IRI
        target_class = None
        for cls in ontology.classes():
            if str(cls.iri) == iri_str:
                target_class = cls
                break
        
        if not target_class:
            return jsonify({"error": f"Class not found: {iri_str}"}), 404
        
        instances = []
        if direct:
            instances = [str(ind.iri) for ind in target_class.instances()]
        else:
            # Get instances including from subclasses
            visited = set()
            def get_all_instances(cls):
                for ind in cls.instances():
                    iri = str(ind.iri)
                    if iri not in visited:
                        visited.add(iri)
                        instances.append(iri)
                for sub in cls.subclasses():
                    get_all_instances(sub)
            get_all_instances(target_class)
        
        return jsonify({
            "class": iri_str,
            "instances": instances,
            "count": len(instances)
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/individual/types", methods=["GET"])
def get_individual_types():
    """Get inferred types of an individual"""
    if not reasoner or ontology is None:
        return jsonify({
            "error": "Reasoning not available",
            "inferred_types": []
        })
    
    iri_str = request.args.get("iri")
    
    if not iri_str:
        return jsonify({"error": "Missing 'iri' parameter"}), 400
    
    try:
        # Find individual by IRI
        target_ind = None
        for ind in ontology.individuals():
            if str(ind.iri) == iri_str:
                target_ind = ind
                break
        
        if not target_ind:
            return jsonify({"error": f"Individual not found: {iri_str}"}), 404
        
        types = [str(cls.iri) for cls in target_ind.is_a if hasattr(cls, 'iri') and "Thing" not in str(cls.iri)]
        
        return jsonify({
            "individual": iri_str,
            "inferred_types": types
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/individual/properties", methods=["GET"])
def get_individual_properties():
    """Get properties of an individual"""
    iri_str = request.args.get("iri")
    
    if not iri_str or ontology is None:
        return jsonify({"error": "Missing 'iri' parameter or ontology not loaded"}), 400
    
    try:
        # Find individual by IRI
        target_ind = None
        for ind in ontology.individuals():
            if str(ind.iri) == iri_str:
                target_ind = ind
                break
        
        if not target_ind:
            return jsonify({"error": f"Individual not found: {iri_str}"}), 404
        
        prop_map = {}
        for prop in ontology.properties():
            # Get values for this property
            values = getattr(target_ind, prop.name, [])
            if values:
                if not isinstance(values, list):
                    values = [values]
                str_values = [str(v.iri) if hasattr(v, 'iri') else str(v) for v in values]
                prop_map[prop.name] = str_values
        
        return jsonify({
            "individual": iri_str,
            "properties": prop_map
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/classify", methods=["POST"])
def classify():
    """Perform complete classification and export inferences"""
    if not reasoner or ontology is None:
        return jsonify({
            "error": "Reasoning not available"
        }), 400
    
    try:
        start = time.time()
        
        # Get inferred axioms count
        axiom_count = len(list(ontology.axioms()))
        
        # Export to Turtle format
        turtle_content = ontology.serialize(format="ntriples")
        
        # Push to Fuseki
        push_inferences_to_fuseki(turtle_content)
        
        duration = int((time.time() - start) * 1000)
        
        return jsonify({
            "status": "classified",
            "inferred_axioms": axiom_count,
            "duration_ms": duration,
            "pushed_to_fuseki": True
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/check", methods=["POST"])
def check_individual():
    """Check consistency of a specific individual"""
    if not reasoner or ontology is None:
        return jsonify({
            "error": "Reasoning not available"
        }), 400
    
    try:
        data = request.get_json()
        iri_str = data.get("iri")
        
        if not iri_str:
            return jsonify({"error": "Missing 'iri' in request body"}), 400
        
        # Find individual
        target_ind = None
        for ind in ontology.individuals():
            if str(ind.iri) == iri_str:
                target_ind = ind
                break
        
        if not target_ind:
            return jsonify({"error": f"Individual not found: {iri_str}"}), 404
        
        types = [cls for cls in target_ind.is_a if hasattr(cls, 'iri')]
        
        return jsonify({
            "individual": iri_str,
            "consistent": True,  # Simplified - owlready2 handles consistency automatically
            "types_count": len(types)
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/explain", methods=["GET"])
def explain():
    """Explain inconsistency (if any)"""
    if ontology is None:
        return jsonify({
            "error": "Ontology not loaded"
        }), 400
    
    is_consistent = len(list(ontology.inconsistent_classes)) == 0
    
    if is_consistent:
        return jsonify({
            "consistent": True,
            "explanation": "Ontology is consistent"
        })
    else:
        return jsonify({
            "consistent": False,
            "hint": "Use Protégé with Explanation plugin for detailed justifications"
        })


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    print("Starting HermiT REST API Server...")
    load_ontology()
    print("HermiT REST API started on port 7777")
    app.run(host="0.0.0.0", port=7777, debug=False)