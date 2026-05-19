#!/usr/bin/env python3
"""
3_csv_to_owl.py
===============
Parse les fichiers data/templates/<Classe>.csv et injecte les individus
dans instances.owl via owlready2.

Fonctionnement :
  - Lit chaque CSV (en ignorant les lignes #)
  - Crée (ou met à jour) les individus dans le world owlready2
  - Règle les datatype properties et les object properties (via REF_)
  - Sérialise le world dans instances.owl (RDF/XML) et optionnellement en Turtle

Modifications v2 :
  - Déclaration dynamique des propriétés OWL manquantes dans les fichiers source
    (recommendedFor, satisfies, matchesLevel, masteryScore, engagementIndex,
     gdeCompatibilityScore) directement dans instances_onto avant sauvegarde.
  - Les colonnes extra (masteryScore, engagementIndex, gdeCompatibilityScore,
    REF_recommendedFor, REF_satisfies, REF_matchesLevel) sont maintenant traitées
    même si elles n'existent pas dans les index OWL chargés.

Usage:
    python 3_csv_to_owl.py [--onto-dir ontologies]
                           [--templates data/templates]
                           [--output ontologies/instances.owl]
                           [--append]          # ajouter aux individus existants
                           [--replace]         # écraser les individus (défaut)
                           [--also-ttl]        # exporter aussi en Turtle

Dépendances: owlready2
"""

import argparse, csv, json, os, re, sys
from collections import defaultdict
from io import StringIO
import owlready2 as owl

# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

INSTANCES_BASE = "http://nsxai.org/instances#"

# Propriétés manquantes dans les OWL sources — déclarées dynamiquement
# dans instances_onto au moment de l'injection.
EXTRA_OWL_PROPS = {
    # Object properties
    "recommendedFor":       {"kind": "object", "domain": "DesignPractice", "range": "GamifiedITS"},
    "satisfies":            {"kind": "object", "domain": "Player",         "range": "owl.Thing"},
    "matchesLevel":         {"kind": "object", "domain": "Resource",       "range": "Player"},
    # Data properties
    "masteryScore":         {"kind": "data",   "domain": "Player",         "range_type": float},
    "engagementIndex":      {"kind": "data",   "domain": "Resource",       "range_type": float},
    "gdeCompatibilityScore":{"kind": "data",   "domain": "DesignPractice", "range_type": float},
}


def safe_name(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_]', '_', name)

def csv_to_class_name(fname: str) -> str:
    return os.path.splitext(os.path.basename(fname))[0]

def read_csv_skip_comments(fpath: str) -> tuple[list[str], list[dict]]:
    """Read CSV, skip lines starting with #. Returns (fieldnames, rows)."""
    lines = []
    with open(fpath, "r", encoding="utf-8") as f:
        for line in f:
            if not line.startswith("#"):
                lines.append(line)

    reader = csv.DictReader(StringIO("".join(lines)))
    rows   = [row for row in reader if any(v.strip() for v in row.values())]
    return reader.fieldnames or [], rows

def cast_value(val: str, range_type: str):
    """Cast a string value to the appropriate Python type."""
    val = val.strip()
    if not val:
        return None
    rt = range_type.lower()
    try:
        if "float" in rt or "double" in rt or "decimal" in rt:
            return float(val)
        if "int" in rt or "integer" in rt:
            return int(val)
        if "bool" in rt:
            return val.lower() in ("true", "1", "yes")
        if "date" in rt:
            from datetime import date
            return date.fromisoformat(val)
    except Exception:
        pass
    return val

def multi_ref(val: str) -> list[str]:
    if not val or not val.strip():
        return []
    return [v.strip() for v in val.split("|") if v.strip()]

# ══════════════════════════════════════════════════════════════════════════════
#  Ontology loading
# ══════════════════════════════════════════════════════════════════════════════

def load_all_ontologies(onto_dir: str) -> owl.World:
    world = owl.World()
    owl.onto_path.clear()
    owl.onto_path.append(onto_dir)

    load_order = [
        "sioc_stub.owl", "gato.owl", "its_domain.owl",
        "gado_core.owl", "gado_full.owl", "its_pedagogical.owl",
        "meututor_domain.owl", "meututor_domain_cp.owl",
        "meututor_domain_curriculum.owl", "meututor_domain_resource.owl",
    ]
    for fname in load_order:
        path = os.path.join(onto_dir, fname)
        if not os.path.exists(path):
            continue
        try:
            world.get_ontology(f"file://{path}").load()
        except Exception as e:
            print(f"  [WARN] {fname}: {e}")

    return world

def build_class_index(world: owl.World) -> dict:
    idx = {}
    for onto in world.ontologies.values():
        for cls in onto.classes():
            if cls.name:
                idx[cls.name]              = cls
                idx[safe_name(cls.name)]   = cls
    return idx

def build_prop_index(world: owl.World) -> tuple[dict, dict]:
    dp, op = {}, {}
    for onto in world.ontologies.values():
        for p in onto.data_properties():
            if p.name:
                dp[p.name]             = p
                dp[p.name.lower()]     = p
        for p in onto.object_properties():
            if p.name:
                op[p.name]             = p
                op[p.name.lower()]     = p
    return dp, op

# ══════════════════════════════════════════════════════════════════════════════
#  Declare missing OWL properties in instances_onto
# ══════════════════════════════════════════════════════════════════════════════

def declare_extra_properties(
    instances_onto: "owl.Ontology",
    class_idx: dict,
    dp_idx: dict,
    op_idx: dict,
) -> tuple[dict, dict]:
    """
    Declare recommendedFor, satisfies, matchesLevel, masteryScore,
    engagementIndex, gdeCompatibilityScore inside instances_onto if they are
    not already present in the loaded schema ontologies.

    Returns updated (dp_idx, op_idx) so inject_csv can find them.
    """
    with instances_onto:
        for pname, pinfo in EXTRA_OWL_PROPS.items():
            if pinfo["kind"] == "object" and pname not in op_idx:
                domain_cls = class_idx.get(pinfo["domain"])
                range_cls  = class_idx.get(pinfo["range"], owl.Thing)
                new_prop   = owl.types.new_class(
                    pname,
                    (owl.ObjectProperty,),
                )
                # owlready2 >= 0.40: domain/range must be set via list append
                # to avoid AttributeError on annotation-only properties
                try:
                    if domain_cls:
                        new_prop.domain.append(domain_cls)
                    if range_cls:
                        new_prop.range.append(range_cls)
                except Exception:
                    pass
                op_idx[pname]             = new_prop
                op_idx[pname.lower()]     = new_prop
                print(f"  [DECLARE-OP] {pname}")

            elif pinfo["kind"] == "data" and pname not in dp_idx:
                domain_cls  = class_idx.get(pinfo["domain"])
                range_type  = pinfo["range_type"]
                new_prop    = owl.types.new_class(
                    pname,
                    (owl.DataProperty,),
                )
                try:
                    if domain_cls:
                        new_prop.domain.append(domain_cls)
                except Exception:
                    pass
                # Skip range assignment for data properties (type is handled at value injection)
                dp_idx[pname]           = new_prop
                dp_idx[pname.lower()]   = new_prop
                print(f"  [DECLARE-DP] {pname}")

    return dp_idx, op_idx

# ══════════════════════════════════════════════════════════════════════════════
#  Core injection logic
# ══════════════════════════════════════════════════════════════════════════════

def inject_csv(
    fpath: str,
    class_name_hint: str,
    instances_onto: "owl.Ontology",
    class_idx: dict,
    dp_idx: dict,
    op_idx: dict,
    schema_classes: dict,
    ind_registry: dict,
    replace: bool = True,
) -> int:
    """Inject one CSV into the instances ontology. Returns count of created individuals."""

    fieldnames, rows = read_csv_skip_comments(fpath)
    if not rows:
        return 0

    # Resolve OWL class
    owl_cls = class_idx.get(class_name_hint)
    if owl_cls is None:
        for name, c in class_idx.items():
            if name.lower().replace("_", "") == class_name_hint.lower().replace("_", ""):
                owl_cls = c
                break
    if owl_cls is None:
        print(f"  [WARN] Class '{class_name_hint}' not found in ontology, "
              f"skipping {os.path.basename(fpath)}")
        return 0

    schema_info = schema_classes.get(class_name_hint, {})
    dp_schema   = schema_info.get("data_props", {})

    count = 0
    with instances_onto:
        for row in rows:
            ind_id = row.get("id", "").strip()
            if not ind_id:
                continue

            if replace and ind_id in ind_registry:
                owl.destroy_entity(ind_registry[ind_id])

            ind = owl_cls(ind_id, namespace=instances_onto)
            ind_registry[ind_id] = ind
            count += 1

            for col, val in row.items():
                if col == "id" or not col or not val or not val.strip():
                    continue

                if col.startswith("REF_"):
                    prop_name = col[4:]
                    prop = op_idx.get(prop_name) or op_idx.get(prop_name.lower())
                    if prop is None:
                        continue
                    refs    = multi_ref(val)
                    targets = [ind_registry[r] for r in refs if r in ind_registry]
                    if targets:
                        try:
                            current  = list(getattr(ind, prop.python_name) or [])
                            setattr(ind, prop.python_name, current + targets)
                        except Exception:
                            try:
                                setattr(ind, prop.python_name, targets[0])
                            except Exception:
                                pass
                else:
                    prop = dp_idx.get(col) or dp_idx.get(col.lower())
                    if prop is None:
                        continue
                    rtype     = dp_schema.get(col, {}).get("range_type", "str")
                    typed_val = cast_value(val, rtype)
                    if typed_val is not None:
                        try:
                            setattr(ind, prop.python_name, [typed_val])
                        except Exception:
                            pass

    return count


def resolve_forward_refs(
    fpath: str,
    class_name_hint: str,
    instances_onto: "owl.Ontology",
    op_idx: dict,
    ind_registry: dict,
) -> None:
    """Second pass: resolve any forward object-property references."""
    fieldnames, rows = read_csv_skip_comments(fpath)

    with instances_onto:
        for row in rows:
            ind_id = row.get("id", "").strip()
            ind    = ind_registry.get(ind_id)
            if ind is None:
                continue
            for col, val in row.items():
                if not col.startswith("REF_") or not val or not val.strip():
                    continue
                prop_name = col[4:]
                prop = op_idx.get(prop_name) or op_idx.get(prop_name.lower())
                if prop is None:
                    continue
                refs    = multi_ref(val)
                targets = [ind_registry[r] for r in refs if r in ind_registry]
                if targets:
                    try:
                        existing = list(getattr(ind, prop.python_name) or [])
                        combined = list({id(x): x for x in existing + targets}.values())
                        setattr(ind, prop.python_name, combined)
                    except Exception:
                        try:
                            setattr(ind, prop.python_name, targets[0])
                        except Exception:
                            pass

# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Inject CSV individuals into instances.owl")
    parser.add_argument("--onto-dir",   default="ontologies",              help="Directory with schema .owl files")
    parser.add_argument("--templates",  default="data/templates",          help="Directory with populated CSVs")
    parser.add_argument("--schema",     default="data/schema.json",        help="Schema JSON from step 1")
    parser.add_argument("--output",     default="ontologies/instances.owl",help="Output instances OWL file")
    parser.add_argument("--append",     action="store_true",               help="Append to existing individuals")
    parser.add_argument("--also-ttl",   action="store_true",               help="Also save Turtle output")
    args = parser.parse_args()

    onto_dir    = os.path.abspath(args.onto_dir)
    tmpl_dir    = os.path.abspath(args.templates)
    output      = os.path.abspath(args.output)
    schema_path = os.path.abspath(args.schema)
    replace     = not args.append

    print("Loading schema ontologies…")
    world     = load_all_ontologies(onto_dir)
    class_idx = build_class_index(world)
    dp_idx, op_idx = build_prop_index(world)

    # Load or create instances ontology
    inst_path       = os.path.join(onto_dir, "instances.owl")
    instances_onto  = None
    if os.path.exists(inst_path) and args.append:
        print(f"Appending to existing {inst_path}…")
        instances_onto = world.get_ontology(f"file://{inst_path}").load()
    else:
        print("Creating fresh instances ontology…")
        instances_onto = world.get_ontology(INSTANCES_BASE)

    # Declare recommendation properties missing from source OWL files
    print("\nDeclaring extra recommendation properties…")
    dp_idx, op_idx = declare_extra_properties(instances_onto, class_idx, dp_idx, op_idx)

    # Load schema for type info
    schema_classes = {}
    if os.path.exists(schema_path):
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
        schema_classes = schema.get("classes", {})

    # Build individual registry from existing instances (append mode)
    ind_registry: dict[str, object] = {}
    if args.append:
        for ind in instances_onto.individuals():
            local_name = ind.iri.split("#")[-1]
            ind_registry[local_name] = ind

    csv_files = sorted([f for f in os.listdir(tmpl_dir) if f.endswith(".csv")])
    if not csv_files:
        print(f"No CSV files found in {tmpl_dir}")
        sys.exit(1)

    print(f"\nFirst pass: creating individuals from {len(csv_files)} CSV files…")
    total     = 0
    processed = []
    for fname in csv_files:
        fpath      = os.path.join(tmpl_dir, fname)
        class_name = csv_to_class_name(fname)
        n = inject_csv(
            fpath, class_name,
            instances_onto, class_idx, dp_idx, op_idx,
            schema_classes, ind_registry, replace=replace,
        )
        if n > 0:
            print(f"  [OK] {fname}: {n} individuals")
            processed.append(fpath)
            total += n

    print(f"\nSecond pass: resolving forward object-property references…")
    for fpath in processed:
        class_name = csv_to_class_name(os.path.basename(fpath))
        resolve_forward_refs(fpath, class_name, instances_onto, op_idx, ind_registry)

    os.makedirs(os.path.dirname(output), exist_ok=True)

    print(f"\nSaving OWL/XML → {output}…")
    instances_onto.save(file=output, format="rdfxml")

    if args.also_ttl:
        ttl_out = output.replace(".owl", ".ttl")
        print(f"Saving Turtle → {ttl_out}…")
        instances_onto.save(file=ttl_out, format="ntriples")

    print(f"\n✓ Done: {total} individuals injected into {output}")
    print(f"  Registry contains {len(ind_registry)} unique individuals")

if __name__ == "__main__":
    main()
