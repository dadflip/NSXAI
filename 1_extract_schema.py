#!/usr/bin/env python3
"""
1_extract_schema.py
===================
Analyse agnostique de toute la suite d'ontologies NSXAI et génère :
  - data/schema.json          : schéma complet (classes, propriétés, hiérarchie, namespaces)
  - data/templates/<cls>.csv  : un CSV-template vide par classe instanciable

Modifications v2 :
  - Injection post-extraction des propriétés de recommandation absentes des OWL
    (recommendedFor, satisfies, matchesLevel, masteryScore, engagementIndex,
     gdeCompatibilityScore) directement dans schema.json et les templates CSV.
  - Les classes précédemment vides (SDT_*, Yee_*, Category*, Resource, Curriculum…)
    reçoivent maintenant des templates CSV enrichis via 2_populate.py.

Usage:
    python 1_extract_schema.py [--onto-dir <path>] [--out-dir <path>]

Dépendances: owlready2
"""

import argparse, json, os, csv, re, sys
from collections import defaultdict
import owlready2 as owl

# ── helpers ────────────────────────────────────────────────────────────────────

def safe_name(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_]', '_', name)

def prop_type_label(range_list) -> str:
    if not range_list:
        return "str"
    r = range_list[0]
    if r is None:
        return "str"
    s = str(r)
    if "float" in s or "double" in s or "decimal" in s:
        return "float"
    if "int" in s or "integer" in s:
        return "int"
    if "bool" in s:
        return "bool"
    if "date" in s.lower():
        return "date"
    if "ConstrainedDatatype" in s:
        inner = s
        if "float" in inner: return "float[0..1]"
        if "int"   in inner: return "int"
    return "str"

def collect_ancestors(cls, visited=None):
    if visited is None:
        visited = set()
    for parent in cls.is_a:
        if isinstance(parent, owl.entity.ThingClass) and parent.name not in ("Thing", None):
            if parent.name not in visited:
                visited.add(parent.name)
                collect_ancestors(parent, visited)
    return visited

# ── Propriétés de recommandation manquantes dans les OWL ──────────────────────
# Définies dans ANALYSE_REGLES.md, injectées ici dans schema.json sans modifier
# les fichiers OWL sources.

EXTRA_OBJECT_PROPS = {
    "recommendedFor": {
        "iri":    "http://nsxai.org/instances#recommendedFor",
        "domain": ["DesignPractice"],
        "range":  ["GamifiedITS"],
    },
    "satisfies": {
        "iri":    "http://nsxai.org/instances#satisfies",
        "domain": ["Player"],
        "range":  ["SDT_Autonomy", "SDT_Competence", "SDT_Relatedness"],
    },
    "matchesLevel": {
        "iri":    "http://nsxai.org/instances#matchesLevel",
        "domain": ["Resource"],
        "range":  ["Player"],
    },
}

EXTRA_DATA_PROPS = {
    "masteryScore": {
        "iri":        "http://nsxai.org/instances#masteryScore",
        "domain":     ["Player"],
        "range_type": "float[0..1]",
    },
    "engagementIndex": {
        "iri":        "http://nsxai.org/instances#engagementIndex",
        "domain":     ["Resource"],
        "range_type": "float[0..1]",
    },
    "gdeCompatibilityScore": {
        "iri":        "http://nsxai.org/instances#gdeCompatibilityScore",
        "domain":     ["DesignPractice"],
        "range_type": "float[0..1]",
    },
}

# Colonnes extra à ajouter dans les templates CSV des classes concernées.
EXTRA_CLASS_COLS: dict[str, dict] = {
    "Player": {
        "masteryScore":  {"kind": "data",   "type": "float[0..1]", "description": "Mastery score [0..1] (derived)"},
        "REF_satisfies": {"kind": "object",  "range_classes": ["SDT_Autonomy","SDT_Competence","SDT_Relatedness"],
                          "property": "satisfies", "description": "SDT psychological need satisfied"},
    },
    "DesignPractice": {
        "gdeCompatibilityScore": {"kind": "data",   "type": "float[0..1]", "description": "GDE-player compat. [0..1]"},
        "REF_recommendedFor":    {"kind": "object",  "range_classes": ["GamifiedITS"],
                                  "property": "recommendedFor", "description": "Target GamifiedITS"},
    },
    "Resource": {
        "engagementIndex":  {"kind": "data",   "type": "float[0..1]", "description": "Engagement index [0..1]"},
        "REF_matchesLevel": {"kind": "object",  "range_classes": ["Player"],
                             "property": "matchesLevel", "description": "Player whose level matches"},
    },
}

# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Extract NSXAI ontology schema to CSV templates")
    parser.add_argument("--onto-dir", default="ontologies", help="Directory containing .owl files")
    parser.add_argument("--out-dir",  default="data",       help="Output directory")
    args = parser.parse_args()

    onto_dir = os.path.abspath(args.onto_dir)
    out_dir  = os.path.abspath(args.out_dir)
    tmpl_dir = os.path.join(out_dir, "templates")
    os.makedirs(tmpl_dir, exist_ok=True)

    owl.onto_path.clear()
    owl.onto_path.append(onto_dir)
    world = owl.World()

    load_order = [
        "sioc_stub.owl",
        "gato.owl",
        "its_domain.owl",
        "gado_core.owl",
        "gado_full.owl",
        "its_pedagogical.owl",
        "meututor_domain.owl",
        "meututor_domain_cp.owl",
        "meututor_domain_curriculum.owl",
        "meututor_domain_resource.owl",
    ]

    ontos = []
    for fname in load_order:
        path = os.path.join(onto_dir, fname)
        if not os.path.exists(path):
            print(f"  [WARN] {fname} not found, skipping")
            continue
        try:
            o = world.get_ontology(f"file://{path}").load()
            ontos.append(o)
            print(f"  [OK] Loaded {fname}")
        except Exception as e:
            print(f"  [WARN] Could not load {fname}: {e}")

    # ── Collect all classes ────────────────────────────────────────────────────
    seen_iris = {}
    for onto in ontos:
        for cls in onto.classes():
            if cls.iri and cls.iri not in seen_iris:
                seen_iris[cls.iri] = cls

    all_classes = list(seen_iris.values())
    print(f"\n  Found {len(all_classes)} unique classes")

    # ── Collect all properties ─────────────────────────────────────────────────
    obj_props  = {}
    data_props = {}

    for onto in ontos:
        for p in onto.object_properties():
            if p.name and p.name not in obj_props:
                dom = [d.name for d in p.domain if hasattr(d, 'name') and d.name] if p.domain else []
                rng = [r.name for r in p.range  if hasattr(r, 'name') and r.name] if p.range  else []
                obj_props[p.name] = {"iri": p.iri, "domain": dom, "range": rng}

        for p in onto.data_properties():
            if p.name and p.name not in data_props:
                dom = [d.name for d in p.domain if hasattr(d, 'name') and d.name] if p.domain else []
                rng = prop_type_label(p.range)
                data_props[p.name] = {"iri": p.iri, "domain": dom, "range_type": rng}

    # ── Inject extra recommendation properties ─────────────────────────────────
    for pname, pinfo in EXTRA_OBJECT_PROPS.items():
        if pname not in obj_props:
            obj_props[pname] = {"iri": pinfo["iri"], "domain": pinfo["domain"], "range": pinfo["range"]}
            print(f"  [INJECT-OP] {pname}")

    for pname, pinfo in EXTRA_DATA_PROPS.items():
        if pname not in data_props:
            data_props[pname] = {"iri": pinfo["iri"], "domain": pinfo["domain"], "range_type": pinfo["range_type"]}
            print(f"  [INJECT-DP] {pname}")

    # ── Build class → applicable properties mapping ────────────────────────────
    def props_for_class(cls_name: str, ancestors: set) -> tuple[dict, dict]:
        scope = {cls_name} | ancestors
        applicable_data = {}
        applicable_obj  = {}
        for pname, pinfo in data_props.items():
            dom = set(pinfo["domain"])
            if not dom or dom & scope:
                applicable_data[pname] = pinfo
        for pname, pinfo in obj_props.items():
            dom = set(pinfo["domain"])
            if not dom or dom & scope:
                applicable_obj[pname] = pinfo
        return applicable_data, applicable_obj

    # ── Build schema dict ─────────────────────────────────────────────────────
    schema = {
        "namespaces": {
            "instances":   "http://nsxai.org/instances#",
            "gado_core":   "http://surveys.nees.com.br/ontologies/gado_core.owl#",
            "gado_full":   "http://surveys.nees.com.br/ontologies/gado_full.owl#",
            "gato":        "http://surveys.nees.com.br/ontologies/gato.owl#",
            "its_domain":  "http://surveys.nees.com.br/ontologies/its_domain.owl#",
            "its_ped":     "http://surveys.nees.com.br/ontologies/its/its_pedagogical.owl#",
            "mt":          "http://meututor.com.br/Ontologies/meututor_domain.owl#",
            "mt_cp":       "http://meututor.com.br/Ontologies/meututor_domain_cp.owl#",
            "mt_cur":      "http://meututor.com.br/Ontologies/meututor_domain_curriculum.owl#",
            "mt_res":      "http://meututor.com.br/Ontologies/meututor_domain_resource.owl#",
            "sioc":        "http://rdfs.org/sioc/ns#",
        },
        "classes": {},
        "object_properties": obj_props,
        "data_properties":   data_props,
    }

    ABSTRACT = {
        "THINGDomain", "THINGCurriculum", "THINGInstrutionalPlan",
        "THINGPedagogicalModel", "ThingResource",
        "Game_Design_Element",
        "Gamification_Context",
        "Activity_Loop",
        "Target_Behavior_Category",
        "Motivational_Component",
        "Player_Model",
        "Yees_Motivational_Components",
    }

    for cls in all_classes:
        cname = cls.name
        if not cname:
            continue

        ancestors = collect_ancestors(cls)
        d_props, o_props = props_for_class(cname, ancestors)
        is_abstract = (cname in ABSTRACT) or cname.startswith("THING")

        prefix = cname[0].lower() + cname[1:]
        prefix = re.sub(r'[^a-zA-Z0-9]', '', prefix)

        schema["classes"][cname] = {
            "iri":           cls.iri,
            "is_abstract":   is_abstract,
            "id_prefix":     prefix,
            "ancestors":     sorted(ancestors),
            "data_props":    {k: {"range_type": v["range_type"], "iri": v["iri"]} for k, v in d_props.items()},
            "object_props":  {k: {"range": v["range"], "iri": v["iri"]} for k, v in o_props.items()},
        }

    schema_path = os.path.join(out_dir, "schema.json")
    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
    print(f"\n  Schema saved → {schema_path}")

    # ── Generate CSV templates ─────────────────────────────────────────────────
    generated = 0
    skipped_abstract = 0
    for cname, cinfo in schema["classes"].items():
        if cinfo["is_abstract"]:
            skipped_abstract += 1
            continue

        cols = ["id"]
        col_meta = {"id": {"kind": "id", "description": f"Unique identifier, e.g. {cinfo['id_prefix']}_0001"}}

        for pname, pinfo in cinfo["data_props"].items():
            cols.append(pname)
            col_meta[pname] = {"kind": "data", "type": pinfo["range_type"]}

        for pname, pinfo in cinfo["object_props"].items():
            col_name = f"REF_{pname}"
            cols.append(col_name)
            targets = pinfo["range"] if pinfo["range"] else ["?"]
            col_meta[col_name] = {"kind": "object", "range_classes": targets,
                                   "property": pname, "description": f"Ref to {targets}"}

        # Inject extra columns for recommendation properties
        for extra_col, extra_meta in EXTRA_CLASS_COLS.get(cname, {}).items():
            if extra_col not in cols:
                cols.append(extra_col)
                col_meta[extra_col] = extra_meta

        fname = safe_name(cname) + ".csv"
        fpath = os.path.join(tmpl_dir, fname)
        with open(fpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            f.write("# CLASS: " + cname + "\n")
            f.write("# IRI: "   + cinfo["iri"] + "\n")
            f.write("# COLUMNS:\n")
            for col, meta in col_meta.items():
                desc = meta.get("description") or meta.get("type") or ""
                f.write(f"#   {col}: {meta['kind']} — {desc}\n")
            f.write("# ─── Data rows below (delete this line) ───────────────────────\n")
            writer.writeheader()
            for i in range(1, 4):
                row = {"id": f"{cinfo['id_prefix']}_{i:04d}"}
                writer.writerow(row)

        generated += 1

    print(f"\n  Generated {generated} CSV templates → {tmpl_dir}/")
    print(f"  Skipped {skipped_abstract} abstract classes")
    print(f"  Extra recommendation properties injected: "
          f"{list(EXTRA_OBJECT_PROPS)} + {list(EXTRA_DATA_PROPS)}")
    print("\n  Next step: run  python 2_populate.py  to fill the CSVs with synthetic data")

if __name__ == "__main__":
    main()
