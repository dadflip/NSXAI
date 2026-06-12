import sys
import json
from pathlib import Path
# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi import HTTPException, Request, Query
# pyrefly: ignore [missing-import]
from fastapi.responses import StreamingResponse
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
# pyrefly: ignore [missing-import]
import uvicorn
# pyrefly: ignore [missing-import]
import pandas as pd
import networkx as nx
# pyrefly: ignore [missing-import]
import io
# pyrefly: ignore [missing-import]
import zipfile
# pyrefly: ignore [missing-import]
import random
# pyrefly: ignore [missing-import]
import uuid
# pyrefly: ignore [missing-import]
import requests
# pyrefly: ignore [missing-import]
import subprocess
# pyrefly: ignore [missing-import]
import rdflib
# pyrefly: ignore [missing-import]
from rdflib.namespace import RDF, RDFS, OWL
# pyrefly: ignore [missing-import]
from rdflib import URIRef, Literal
# Load global configuration
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
from config import cfg as config

# Local imports
from .fuseki import fuseki_client
from .mlops import app as mlops_app

app = FastAPI(
    title="NSXAI API",
    description="Backend Python allégé pour NSXAI (Proxy SPARQL & MLOps)",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if mlops_app:
    # We remove the default docs routes from mlops_app to avoid duplicating them
    mlops_app.router.routes = [r for r in mlops_app.router.routes if not r.path.startswith(("/docs", "/redoc", "/openapi.json"))]
    app.include_router(mlops_app.router, prefix="/api/ml", tags=["MLOps"])

from fastapi.responses import RedirectResponse

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/api/docs")

@app.on_event("startup")
async def startup_event():
    print("=" * 60)
    print("  NSXAI API - Démarrage")
    print(f"  Host: {config.api.host}:{config.api.port} | Fuseki: {config.fuseki.url}")
    print("=" * 60)
    
    if fuseki_client.ping():
        print("[OK] Fuseki connecté")
    else:
        print("[WARN] Fuseki non accessible")
    
    print()

# =============================================================================
# ROUTE : SPARQL PROXY
# =============================================================================
@app.post("/api/sparql", tags=["sparql"])
async def execute_sparql(request: Request) -> Dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    body = await request.body()
    
    if "application/json" in content_type:
        query = json.loads(body).get("query", "")
    else:
        query = body.decode("utf-8")
        
    if not query.strip():
        raise HTTPException(status_code=400, detail="Missing SPARQL query")
    
    # Check Fuseki connectivity first to return a clear 503
    if not fuseki_client.ping():
        raise HTTPException(
            status_code=503,
            detail="Fuseki triplestore is not reachable. Please start the Fuseki server."
        )
        
    try:
        import re
        # Remove PREFIX lines to find the actual command verb
        query_body = re.sub(r'PREFIX\s+[a-zA-Z0-9_-]*:\s*<[^>]+>', '', query, flags=re.IGNORECASE).strip().upper()
        if query_body.startswith("INSERT") or query_body.startswith("DELETE") or query_body.startswith("CLEAR") or query_body.startswith("WITH"):
            success = fuseki_client.update(query)
            return {"update": success, "message": "Mise à jour réussie"}
        else:
            return fuseki_client.query(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sparql/stats", tags=["sparql"])
async def get_dataset_stats() -> Dict[str, int]:
    try:
        return fuseki_client.get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# ROUTE : MLOPS EXPORTS
# =============================================================================
@app.get("/api/export/dataset", tags=["export"])
def export_dataset(action: str = Query("download", description="download or local")):
    """Génère un ZIP contenant l'ontologie sous forme de Matrice d'Adjacence Enrichie."""
    try:
        import traceback
        
        try:
            print("[DEBUG] Querying all triplets from Fuseki...")
            query = "SELECT ?s ?p ?o WHERE { ?s ?p ?o }"
            results = fuseki_client.query(query)
            bindings = results.get("results", {}).get("bindings", [])
            
            print("[DEBUG] Triplets loaded. Size:", len(bindings))
            
            # Note : on n'ajoute plus le tbox.owl local "à la volée" car on s'appuie 
            # strictement sur ce qui est dans le triplestore (qui contient déjà la TBox si chargée).

            print("[DEBUG] Building matrix dict...")
            matrix_dict = {}

            for row in bindings:
                s_type = row["s"]["type"]
                s_val = row["s"]["value"]
                
                # Formatage du sujet (ajout de _: pour les Blank Nodes)
                s_str = f"_:{s_val}" if s_type == "bnode" else s_val
                
                p_str = row["p"]["value"]
                p_short = p_str.split("#")[-1].split("/")[-1]
                
                o_type = row["o"]["type"]
                o_val = row["o"]["value"]
                
                # Formatage de l'objet
                o_str = f"_:{o_val}" if o_type == "bnode" else o_val
                
                if s_str not in matrix_dict:
                    matrix_dict[s_str] = {}
                    
                if p_short not in matrix_dict[s_str]:
                    matrix_dict[s_str][p_short] = [o_str]
                else:
                    current_val = matrix_dict[s_str][p_short]
                    if isinstance(current_val, list):
                        if o_str not in current_val:
                            current_val.append(o_str)
                    else:
                        if o_str != current_val:
                            matrix_dict[s_str][p_short] = [current_val, o_str]

            print("[DEBUG] Flattening matrix...")
            flattened_matrix = []
            for s_str, props in matrix_dict.items():
                flat_row = {"id": s_str}
                for k, v in props.items():
                    col_name = "ontology_id" if k == "id" else k
                    if isinstance(v, list):
                        flat_row[col_name] = "|".join(v)
                    else:
                        flat_row[col_name] = str(v)
                flattened_matrix.append(flat_row)
                
            print("[DEBUG] Creating dataframe...")
            df_matrix = pd.DataFrame(flattened_matrix)
            
            cols = list(df_matrix.columns)
            if "id" in cols: cols.remove("id")
            if "label" in cols: cols.remove("label")
            if "type" in cols: cols.remove("type")
            
            ordered_cols = ["id"]
            if "label" in df_matrix.columns: ordered_cols.append("label")
            if "type" in df_matrix.columns: ordered_cols.append("type")
            ordered_cols.extend(sorted(cols))
            
            df_matrix = df_matrix[ordered_cols]

            print("[DEBUG] Saving to CSV...")
            task1_dir = config._path.parent / "nsxai" / "ml" / "task1"
            task1_dir.mkdir(parents=True, exist_ok=True)
            
            df_matrix.to_csv(task1_dir / "ontology_matrix.csv", index=False)
            
            print("[DEBUG] Writing README...")
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("ontology_matrix.csv", df_matrix.to_csv(index=False))
                readme_text = (
                    "NSXAI - MLOps Dataset Export (Enriched Adjacency Matrix)\n"
                    "==========================================================\n\n"
                    "Ce jeu de données a été exporté sous forme d'une Matrice d'Adjacence Enrichie unique.\n\n"
                    "### Fichier exporté :\n"
                    "- ontology_matrix.csv : Contient les sources en lignes (colonne `id`), les prédicats en colonnes, "
                    "et les objets dans les cellules. Les objets multiples pour un même prédicat sont séparés par des pipes (|).\n\n"
                    "### Comment utiliser pour le ML :\n"
                    "Ce format vous permet d'avoir toutes les features d'un noeud sur une seule ligne. "
                    "Si vous avez besoin d'extraire des arêtes (edges), vous pouvez dépivoter ou filtrer les colonnes "
                    "correspondant aux `ObjectProperties` dans Pandas.\n"
                )
                
            with open(task1_dir / "README.txt", "w", encoding="utf-8") as f:
                f.write(readme_text)
                
            if action == "local":
                print("[DEBUG] Returning local success")
                return {"status": "success", "message": f"Matrice générée localement dans {task1_dir}"}
                
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("README.txt", readme_text)
                
            zip_buffer.seek(0)
            return StreamingResponse(
                zip_buffer, 
                media_type="application/zip", 
                headers={"Content-Disposition": "attachment; filename=nsxai_ontology_matrix.zip"}
            )
        except Exception as e:
            print("[DEBUG] Exception caught in logic!")
            traceback.print_exc()
            raise e
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=traceback.format_exc())

@app.get("/api/export/dataset_csv", tags=["export"])
def export_dataset_csv():
    """Génère et renvoie directement le fichier ontology_matrix.csv."""
    try:
        from fastapi.responses import FileResponse
        # Re-use the generation logic by calling it locally
        export_dataset(action="local")
        task1_dir = config._path.parent / "nsxai" / "ml" / "task1"
        csv_path = task1_dir / "ontology_matrix.csv"
        if csv_path.exists():
            return FileResponse(csv_path, media_type="text/csv", filename="ontology_matrix.csv")
        else:
            raise HTTPException(status_code=404, detail="CSV file not generated.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# ROUTE : ARTIFACTS VIEWER
# =============================================================================
OUTPUTS_DIR = config._path.parent / "nsxai" / "ml" / "outputs"

@app.get("/api/artifacts/tree", tags=["artifacts"])
def get_artifacts_tree():
    """Returns the directory structure of ml/outputs."""
    def build_tree(path: Path):
        tree = []
        try:
            for p in sorted(path.iterdir()):
                if p.is_dir():
                    tree.append({
                        "name": p.name,
                        "type": "directory",
                        "path": str(p.relative_to(OUTPUTS_DIR)).replace("\\", "/"),
                        "children": build_tree(p)
                    })
                else:
                    tree.append({
                        "name": p.name,
                        "type": "file",
                        "path": str(p.relative_to(OUTPUTS_DIR)).replace("\\", "/"),
                        "size": p.stat().st_size,
                        "ext": p.suffix.lower()
                    })
        except Exception:
            pass
        return tree
    
    if not OUTPUTS_DIR.exists():
        return []
    return build_tree(OUTPUTS_DIR)

from fastapi.responses import FileResponse
@app.get("/api/artifacts/download/{filepath:path}", tags=["artifacts"])
def download_artifact(filepath: str):
    """Streams or downloads an artifact file."""
    target = OUTPUTS_DIR / filepath
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Path traversal protection
    try:
        target.resolve().relative_to(OUTPUTS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden path")

    ext = target.suffix.lower()
    media_type = "application/octet-stream"
    if ext == ".png":
        media_type = "image/png"
    elif ext == ".csv":
        media_type = "text/csv"
    elif ext == ".html":
        media_type = "text/html"
    elif ext in (".json", ".log", ".txt", ".yaml"):
        media_type = "text/plain"

    return FileResponse(target, media_type=media_type)

@app.post("/api/dataset/duplicate", tags=["mlops", "data"])
async def duplicate_row(request: Request):
    """Duplique une entité existante un nombre de fois donné."""
    try:
        data = await request.json()
        source_uri = data.get("source_uri")
        count = int(data.get("count", 1))
        
        if not source_uri:
            raise HTTPException(status_code=400, detail="Missing source_uri")
            
        # 1. Fetch properties for the given entity
        query = f"SELECT ?p ?o WHERE {{ <{source_uri}> ?p ?o }}"
        results = fuseki_client.query(query)
        bindings = results.get("results", {}).get("bindings", [])
        
        if not bindings:
            raise HTTPException(status_code=404, detail="Entity not found or has no properties")
            
        # 2. Duplicate the entity
        import uuid
        triples_to_insert = []
        
        for i in range(count):
            # Using _1, _2 suffix + short hash to avoid any collisions if run multiple times
            short_id = f"{i+1}_{uuid.uuid4().hex[:4]}"
            if "#" in source_uri:
                base_ns, local_name = source_uri.split("#", 1)
                new_uri = f"{base_ns}#{local_name}_{short_id}"
            else:
                new_uri = f"{source_uri}_{short_id}"
                
            for row in bindings:
                p = row["p"]["value"]
                o_val = row["o"]["value"]
                o_type = row["o"]["type"]
                
                if o_type == "uri":
                    o_fmt = f"<{o_val}>"
                else:
                    safe_o = o_val.replace('"', '\\"')
                    o_fmt = f'"{safe_o}"'
                    
                triples_to_insert.append(f"<{new_uri}> <{p}> {o_fmt} .")
                
        # 3. Insert into triplestore
        if triples_to_insert:
            batch_size = 500
            for i in range(0, len(triples_to_insert), batch_size):
                batch = triples_to_insert[i:i+batch_size]
                insert_query = "INSERT DATA { " + " ".join(batch) + " }"
                success = fuseki_client.update(insert_query)
                if not success:
                    raise HTTPException(status_code=500, detail="Failed to insert a batch of duplicated data.")
                    
        return {"status": "success", "generated": count}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/export/ontology", tags=["export"])
def export_ontology(fmt: str = Query("ttl", description="Format: ttl, rdf, jsonld, nt")):
    """Exporte l'ontologie au format demandé, dans un ZIP avec un README."""
    format_map = {
        "ttl": ("text/turtle", "turtle"),
        "rdf": ("application/rdf+xml", "rdf+xml"),
        "jsonld": ("application/ld+json", "json-ld"),
        "nt": ("application/n-triples", "n-triples")
    }
    
    if fmt not in format_map:
        raise HTTPException(status_code=400, detail="Format non supporté. Choisissez parmi: ttl, rdf, jsonld, nt")
        
    mime_type, ext_name = format_map[fmt]
    
    rdflib_fmt = {
        "ttl": "turtle",
        "rdf": "xml",
        "jsonld": "json-ld",
        "nt": "nt"
    }.get(fmt, "turtle")

    try:
        g = rdflib.Graph()
        nt_data = fuseki_client.get_graph_export("application/n-triples")
        g.parse(data=nt_data, format="nt")
        
        # Include TBOX context
        tbox_path = config.ontologies.owl_dir / "tbox.owl"
        if tbox_path.exists():
            g.parse(str(tbox_path), format="xml")
            
        graph_data = g.serialize(format=rdflib_fmt).encode('utf-8')
        
        # Création du ZIP en mémoire
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"ontology.{fmt}", graph_data)
            
            readme_text = (
                f"NSXAI - Ontology Export ({ext_name})\n"
                "==================================\n\n"
                f"Ce fichier contient l'intégralité de la base de connaissances NSXAI au format {ext_name}.\n\n"
                "Cas d'usage selon le format :\n"
                "- Turtle (.ttl) : Format lisible par l'humain, idéal pour l'édition manuelle ou la revue de code.\n"
                "- RDF/XML (.rdf) : Format historique, utilisé par les anciens parseurs ou des outils de validation stricts.\n"
                "- JSON-LD (.jsonld) : Idéal pour l'intégration web et l'utilisation avec des APIs modernes ou du JavaScript.\n"
                "- N-Triples (.nt) : Format ligne par ligne, parfait pour le traitement par lots (batch processing) ou les très gros volumes.\n"
            )
            zf.writestr("README.txt", readme_text)
            
        zip_buffer.seek(0)
        return StreamingResponse(
            zip_buffer, 
            media_type="application/zip", 
            headers={"Content-Disposition": f"attachment; filename=nsxai_ontology_{fmt}.zip"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/ontology/reset", tags=["ontology"])
def reset_ontology():
    try:
        fuseki_client.update("CLEAR DEFAULT")
        
        owl_path = config.ontologies.owl_dir / "tg.owl"
        if not owl_path.exists():
            raise FileNotFoundError(f"Fichier ontologie introuvable: {owl_path}")
            
        with open(owl_path, "rb") as f:
            data = f.read()
            
        response = requests.post(
            config.fuseki.data_endpoint,
            data=data,
            headers={'Content-Type': 'application/rdf+xml'},
            timeout=120
        )
        response.raise_for_status()
        
        return {"status": "success", "message": "Ontologie réinitialisée avec succès."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok"}

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
def main():
    uvicorn.run("nsxai.api.main:app", host=config.api.host, port=config.api.port, reload=config.api.debug)

if __name__ == "__main__":
    main()
