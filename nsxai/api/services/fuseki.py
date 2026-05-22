"""
Client Fuseki pour l'API NSXAI
Gère les connexions et requêtes vers Apache Jena Fuseki
"""
from typing import Dict, Any, List, Optional
from SPARQLWrapper import SPARQLWrapper, JSON, POST, GET
import requests
from ..config import config


class FusekiClient:
    """Client pour interagir avec Apache Jena Fuseki"""
    
    def __init__(self):
        self.query_endpoint = config.fuseki.query_endpoint
        self.update_endpoint = config.fuseki.update_endpoint
        self.data_endpoint = config.fuseki.data_endpoint
        self.timeout = config.fuseki.timeout
    
    def query(self, sparql_query: str) -> Dict[str, Any]:
        """
        Exécute une requête SPARQL SELECT/CONSTRUCT/ASK
        
        Args:
            sparql_query: Requête SPARQL
            
        Returns:
            Résultats au format JSON
        """
        sparql = SPARQLWrapper(self.query_endpoint)
        sparql.setQuery(sparql_query)
        sparql.setReturnFormat(JSON)
        sparql.setTimeout(self.timeout)
        
        try:
            results = sparql.query().convert()
            return results
        except Exception as e:
            raise Exception(f"SPARQL query error: {str(e)}")
    
    def update(self, sparql_update: str) -> bool:
        """
        Exécute une requête SPARQL UPDATE (INSERT/DELETE)
        
        Args:
            sparql_update: Requête SPARQL UPDATE
            
        Returns:
            True si succès
        """
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
    
    def load_ttl(self, ttl_content: str, graph_uri: Optional[str] = None) -> bool:
        """
        Charge du contenu Turtle dans Fuseki
        
        Args:
            ttl_content: Contenu Turtle
            graph_uri: URI du graphe nommé (optionnel)
            
        Returns:
            True si succès
        """
        url = self.data_endpoint
        if graph_uri:
            url += f"?graph={graph_uri}"
        
        try:
            response = requests.post(
                url,
                data=ttl_content,
                headers={'Content-Type': 'text/turtle'},
                timeout=self.timeout
            )
            response.raise_for_status()
            return True
        except Exception as e:
            raise Exception(f"TTL load error: {str(e)}")
    
    def clear_dataset(self) -> bool:
        """
        Vide complètement le dataset
        
        Returns:
            True si succès
        """
        sparql_update = "CLEAR ALL"
        return self.update(sparql_update)
    
    def get_stats(self) -> Dict[str, int]:
        """
        Récupère les statistiques du dataset
        
        Returns:
            Dictionnaire avec le nombre de triplets, classes, propriétés, etc.
        """
        queries = {
            'triples': "SELECT (COUNT(*) as ?count) WHERE { ?s ?p ?o }",
            'classes': """
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                SELECT (COUNT(DISTINCT ?class) as ?count) WHERE {
                    ?class a owl:Class .
                }
            """,
            'properties': """
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                SELECT (COUNT(DISTINCT ?prop) as ?count) WHERE {
                    ?prop rdf:type ?type .
                    FILTER(?type IN (owl:ObjectProperty, owl:DatatypeProperty))
                }
            """,
            'individuals': """
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                SELECT (COUNT(DISTINCT ?ind) as ?count) WHERE {
                    ?ind rdf:type ?type .
                    FILTER(?type != owl:Class && ?type != owl:ObjectProperty && ?type != owl:DatatypeProperty)
                }
            """
        }
        
        stats = {}
        for key, query in queries.items():
            try:
                result = self.query(query)
                count = int(result['results']['bindings'][0]['count']['value'])
                stats[key] = count
            except:
                stats[key] = 0
        
        return stats
    
    def ping(self) -> bool:
        """
        Vérifie que Fuseki est accessible
        
        Returns:
            True si accessible
        """
        try:
            response = requests.get(
                f"{config.fuseki.url}/$/ping",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False


# Instance globale du client
fuseki_client = FusekiClient()
