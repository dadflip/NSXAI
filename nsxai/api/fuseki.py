import sys
from pathlib import Path
from typing import Dict, Any, Optional
from SPARQLWrapper import SPARQLWrapper, JSON
import requests

# Root config
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
from config import cfg as config

class FusekiClient:
    def __init__(self):
        self.query_endpoint = config.fuseki.query_endpoint
        self.update_endpoint = config.fuseki.update_endpoint
        self.data_endpoint = config.fuseki.data_endpoint
        self.timeout = config.fuseki.timeout
    
    def query(self, sparql_query: str) -> Dict[str, Any]:
        sparql = SPARQLWrapper(self.query_endpoint)
        sparql.setQuery(sparql_query)
        sparql.setReturnFormat(JSON)
        sparql.setTimeout(self.timeout)
        try:
            return sparql.query().convert()
        except Exception as e:
            raise Exception(f"SPARQL query error: {str(e)}")
    
    def update(self, sparql_update: str) -> bool:
        try:
            response = requests.post(
                self.update_endpoint,
                data=sparql_update,
                headers={'Content-Type': 'application/sparql-update'},
                timeout=self.timeout
            )
            response.raise_for_status()
            return True
        except Exception as e:
            raise Exception(f"SPARQL update error: {str(e)}")
    
    def get_stats(self) -> Dict[str, int]:
        queries = {
            'triples': "SELECT (COUNT(*) as ?count) WHERE { ?s ?p ?o }",
            'classes': "PREFIX owl: <http://www.w3.org/2002/07/owl#> SELECT (COUNT(DISTINCT ?class) as ?count) WHERE { ?class a owl:Class . }",
            'properties': "PREFIX owl: <http://www.w3.org/2002/07/owl#> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> SELECT (COUNT(DISTINCT ?prop) as ?count) WHERE { ?prop rdf:type ?type . FILTER(?type IN (owl:ObjectProperty, owl:DatatypeProperty)) }",
            'individuals': "PREFIX owl: <http://www.w3.org/2002/07/owl#> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> SELECT (COUNT(DISTINCT ?ind) as ?count) WHERE { ?ind rdf:type ?type . FILTER(?type != owl:Class && ?type != owl:ObjectProperty && ?type != owl:DatatypeProperty) }"
        }
        stats = {}
        for key, query in queries.items():
            try:
                result = self.query(query)
                stats[key] = int(result['results']['bindings'][0]['count']['value'])
            except:
                stats[key] = 0
        return stats
    
    def ping(self) -> bool:
        try:
            response = requests.get(f"{config.fuseki.url}/$/ping", timeout=5)
            return response.status_code == 200
        except:
            return False

    def get_graph_export(self, accept_header: str) -> bytes:
        """Fetch the full graph from the data endpoint with the requested format."""
        try:
            response = requests.get(
                self.data_endpoint,
                headers={'Accept': accept_header},
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.content
        except Exception as e:
            raise Exception(f"Graph export error: {str(e)}")

fuseki_client = FusekiClient()
