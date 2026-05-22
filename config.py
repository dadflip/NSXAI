"""
config.py - Loader de configuration centrale NSXAI
Lit config.yaml depuis la racine du projet.

Usage dans n'importe quel script :
    from config import cfg
    print(cfg.fuseki.url)
    print(cfg.jena.dir)
    print(cfg.ontologies.owl_dir)
"""
from __future__ import annotations
from pathlib import Path
import yaml

# Racine du projet = dossier contenant ce fichier
ROOT = Path(__file__).parent


class Config:
    """Configuration globale NSXAI."""

    def __init__(self, path: Path | None = None):
        self._path = path or ROOT / "config.yaml"
        self._load()

    def _load(self):
        if not self._path.exists():
            raise FileNotFoundError(f"config.yaml introuvable : {self._path}")

        with open(self._path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        # --- Jena / Fuseki server ---
        j = raw.get("jena", {})
        version        = j.get("version", "5.1.0")
        install_dir    = ROOT / j.get("install_dir", "triplestore")
        url_tpl        = j.get("download_url", "")
        dir_tpl        = j.get("extracted_dir", "apache-jena-fuseki-{version}")
        fuseki_bat_tpl = j.get("fuseki_bat", "fuseki-server.bat")
        fuseki_sh_tpl  = j.get("fuseki_sh",  "fuseki-server")
        run_dir_tpl    = j.get("run_dir",    "run")

        class JenaConfig:
            pass

        self.jena = JenaConfig()
        self.jena.version      = version
        self.jena.install_dir  = install_dir
        self.jena.dir          = install_dir / dir_tpl.format(version=version)
        self.jena.download_url = url_tpl.format(version=version)
        self.jena.fuseki_bat   = self.jena.dir / fuseki_bat_tpl.format(version=version)
        self.jena.fuseki_sh    = self.jena.dir / fuseki_sh_tpl.format(version=version)
        self.jena.run_dir      = self.jena.dir / run_dir_tpl.format(version=version)

        # --- Fuseki (triplestore) ---
        fk = raw.get("fuseki", {})

        class FusekiConfig:
            pass

        self.fuseki = FusekiConfig()
        self.fuseki.url        = fk.get("url",     "http://localhost:3030")
        self.fuseki.dataset    = fk.get("dataset", "nsxai")
        self.fuseki.timeout    = fk.get("timeout", 30)
        self.fuseki.query_url  = f"{self.fuseki.url}/{self.fuseki.dataset}/sparql"
        self.fuseki.update_url = f"{self.fuseki.url}/{self.fuseki.dataset}/update"
        self.fuseki.data_url   = f"{self.fuseki.url}/{self.fuseki.dataset}/data"
        self.fuseki.ping_url   = f"{self.fuseki.url}/$/ping"
        # Aliases pour compatibilite avec nsxai/api/services/fuseki.py
        self.fuseki.query_endpoint  = self.fuseki.query_url
        self.fuseki.update_endpoint = self.fuseki.update_url
        self.fuseki.data_endpoint   = self.fuseki.data_url

        # --- Frontend (Vite) ---
        fe = raw.get("frontend", {})

        class FrontendConfig:
            pass

        self.frontend = FrontendConfig()
        self.frontend.host = fe.get("host", "localhost")
        self.frontend.port = fe.get("port", 5173)
        self.frontend.dir  = ROOT / fe.get("dir", "nsxai/app")
        self.frontend.url  = f"http://{self.frontend.host}:{self.frontend.port}"

        # --- API ---
        ap = raw.get("api", {})

        class ApiConfig:
            pass

        self.api = ApiConfig()
        self.api.host         = ap.get("host",  "localhost")
        self.api.port         = ap.get("port",  8000)
        self.api.debug        = ap.get("debug", True)
        self.api.cors_origins = ap.get("cors_origins", ["http://localhost:5173"])
        self.api.url          = f"http://{self.api.host}:{self.api.port}"

        # --- Ontologies ---
        ont = raw.get("ontologies", {})

        class OntConfig:
            pass

        self.ontologies = OntConfig()
        self.ontologies.owl_dir       = ROOT / ont.get("owl_dir", "ontologies/owl")
        self.ontologies.fuseki_config = ROOT / ont.get(
            "fuseki_config", "scripts/config/fuseki_config.ttl"
        )

        # --- Options globales ---
        self.verbose = raw.get("verbose", False)
        self.quiet   = raw.get("quiet",   False)


# Instance globale — importée par tous les scripts
cfg = Config()

# Compat avec l'ancien nsxai/api/config.py qui expose `config`
config = cfg


def load_config(path: str | Path | None = None) -> Config:
    """Charge et retourne la configuration (utile pour les tests)."""
    if path is None:
        return cfg
    return Config(Path(path))