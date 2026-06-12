"""
config.py - Loader de configuration centrale NSXAI
Lit config.yaml depuis la racine du projet.
"""
from pathlib import Path
from types import SimpleNamespace
import yaml

ROOT = Path(__file__).parent

class Config:
    def __init__(self, path: Path | None = None):
        self._path = path or ROOT / "config.yaml"
        if not self._path.exists():
            raise FileNotFoundError(f"config.yaml introuvable : {self._path}")

        with open(self._path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        self.verbose = raw.get("verbose", False)
        self.quiet   = raw.get("quiet", False)

        # Convert dict sections to SimpleNamespace for dot-notation access
        self.jena       = SimpleNamespace(**raw.get("jena", {}))
        self.fuseki     = SimpleNamespace(**raw.get("fuseki", {}))
        self.frontend   = SimpleNamespace(**raw.get("frontend", {}))
        self.api        = SimpleNamespace(**raw.get("api", {}))
        self.ontologies = SimpleNamespace(**raw.get("ontologies", {}))
        self.mlops      = SimpleNamespace(**raw.get("mlops", {}))

        # --- API & Frontend ---
        self.api.host = getattr(self.api, "host", "localhost")
        self.api.port = getattr(self.api, "port", 8000)
        self.api.debug = getattr(self.api, "debug", True)
        self.api.cors_origins = getattr(self.api, "cors_origins", ["http://localhost:5173"])
        self.api.url = f"http://{self.api.host}:{self.api.port}"

        self.frontend.host = getattr(self.frontend, "host", "localhost")
        self.frontend.port = getattr(self.frontend, "port", 5173)
        self.frontend.dir  = ROOT / getattr(self.frontend, "dir", "nsxai/app")
        self.frontend.url  = f"http://{self.frontend.host}:{self.frontend.port}"

        # --- Computed URLs (Fuseki) ---
        url  = getattr(self.fuseki, "url", "http://localhost:3030")
        dset = getattr(self.fuseki, "dataset", "nsxai")
        self.fuseki.url = url
        self.fuseki.dataset = dset
        self.fuseki.timeout = getattr(self.fuseki, "timeout", 30)
        self.fuseki.query_endpoint  = f"{url}/{dset}/sparql"
        self.fuseki.update_endpoint = f"{url}/{dset}/update"
        self.fuseki.data_endpoint   = f"{url}/{dset}/data"
        self.fuseki.ping_url        = f"{url}/$/ping"

        # --- Computed Paths (Jena) ---
        v = getattr(self.jena, "version", "5.1.0")
        self.jena.install_dir = ROOT / getattr(self.jena, "install_dir", "triplestore")
        self.jena.dir         = self.jena.install_dir / getattr(self.jena, "extracted_dir", f"apache-jena-fuseki-{v}").format(version=v)
        self.jena.fuseki_bat  = self.jena.dir / getattr(self.jena, "fuseki_bat", "fuseki-server.bat").format(version=v)
        self.jena.fuseki_sh   = self.jena.dir / getattr(self.jena, "fuseki_sh", "fuseki-server").format(version=v)
        self.jena.run_dir     = self.jena.dir / getattr(self.jena, "run_dir", "run").format(version=v)
        
        # --- Ontologies ---
        self.ontologies.owl_dir = ROOT / getattr(self.ontologies, "owl_dir", "ontologies/owl")
        self.ontologies.fuseki_config = ROOT / getattr(self.ontologies, "fuseki_config", "scripts/config/fuseki_config.ttl")

        # --- MLOps Columns ---
        self.mlops.artifact_path = ROOT / getattr(self.mlops, "artifact_path", "nsxai/api/artifacts/task4_explanations.csv")
        cols = getattr(self.mlops, "columns", {})
        self.mlops.col_source       = cols.get("source", "source")
        self.mlops.col_target       = cols.get("target", "target")
        self.mlops.col_score        = cols.get("score", "neurosymbolic_score")
        self.mlops.col_probability  = cols.get("probability", "probability_mean")
        self.mlops.col_confidence   = cols.get("confidence", "symbolic_confidence")
        self.mlops.col_label        = cols.get("label", "confidence_label")
        self.mlops.col_explanation  = cols.get("explanation", "explanation")
        self.mlops.col_is_validated = cols.get("is_validated", "known_positive")

cfg = Config()
config = cfg

def load_config(path: str | Path | None = None) -> Config:
    if path is None:
        return cfg
    return Config(Path(path))