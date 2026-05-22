"""
Routes Ontology - Architecture et gestion des ontologies
"""
from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any, List
from ..services.fuseki import fuseki_client

router = APIRouter(prefix="/api/ontology", tags=["ontology"])

BASE_URI = "https://lms.flipova.fr/nsxai/v1/ontologies/data#"

OWL_CLASS    = "http://www.w3.org/2002/07/owl#Class"
OWL_OP       = "http://www.w3.org/2002/07/owl#ObjectProperty"
OWL_DP       = "http://www.w3.org/2002/07/owl#DatatypeProperty"
OWL_NI       = "http://www.w3.org/2002/07/owl#NamedIndividual"
RDF_TYPE     = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL   = "http://www.w3.org/2000/01/rdf-schema#label"
RDFS_COMMENT = "http://www.w3.org/2000/01/rdf-schema#comment"
RDFS_DOMAIN  = "http://www.w3.org/2000/01/rdf-schema#domain"
RDFS_RANGE   = "http://www.w3.org/2000/01/rdf-schema#range"
RDFS_SUBCLASSOF = "http://www.w3.org/2000/01/rdf-schema#subClassOf"


@router.get("/architecture")
async def get_architecture() -> Dict[str, Any]:
    """
    Récupère l'architecture complète de l'ontologie
    
    Returns:
        - classes: liste des classes OWL avec labels, comments, subClassOf
        - properties: liste des propriétés avec domains, ranges
        - imports: liste des imports
        - individuals: liste des individus
        - individualLinks: liens entre individus
    """
    try:
        # Requête pour les classes
        classes_query = """
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT DISTINCT ?class ?label ?comment ?subClassOf
            WHERE {
                ?class a owl:Class .
                OPTIONAL { ?class rdfs:label ?label }
                OPTIONAL { ?class rdfs:comment ?comment }
                OPTIONAL { ?class rdfs:subClassOf ?subClassOf }
            }
        """
        
        # Requête pour les propriétés
        properties_query = """
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT DISTINCT ?property ?type ?domain ?range ?label ?comment
            WHERE {
                ?property rdf:type ?type .
                FILTER(?type IN (owl:ObjectProperty, owl:DatatypeProperty, owl:AnnotationProperty))
                OPTIONAL { ?property rdfs:domain ?domain }
                OPTIONAL { ?property rdfs:range ?range }
                OPTIONAL { ?property rdfs:label ?label }
                OPTIONAL { ?property rdfs:comment ?comment }
            }
        """
        
        # Requête pour les imports
        imports_query = """
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            SELECT DISTINCT ?ontology ?imported
            WHERE {
                ?ontology owl:imports ?imported .
            }
        """
        
        # Requête pour les individus
        individuals_query = """
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT DISTINCT ?ind ?class
            WHERE {
                ?ind rdf:type ?class .
                FILTER(?class != owl:Class && ?class != owl:ObjectProperty && ?class != owl:DatatypeProperty)
            }
        """
        
        # Exécuter les requêtes
        classes_result = fuseki_client.query(classes_query)
        properties_result = fuseki_client.query(properties_query)
        imports_result = fuseki_client.query(imports_query)
        individuals_result = fuseki_client.query(individuals_query)
        
        # Traiter les classes
        class_map = {}
        for binding in classes_result['results']['bindings']:
            uri = binding['class']['value']
            if uri not in class_map:
                class_map[uri] = {
                    'uri': uri,
                    'label': binding.get('label', {}).get('value'),
                    'comment': binding.get('comment', {}).get('value'),
                    'subClassOfs': []
                }
            if 'subClassOf' in binding:
                class_map[uri]['subClassOfs'].append(binding['subClassOf']['value'])
        
        classes = list(class_map.values())
        
        # Traiter les propriétés
        prop_map = {}
        for binding in properties_result['results']['bindings']:
            uri = binding['property']['value']
            if uri not in prop_map:
                prop_map[uri] = {
                    'uri': uri,
                    'type': binding.get('type', {}).get('value'),
                    'label': binding.get('label', {}).get('value'),
                    'comment': binding.get('comment', {}).get('value'),
                    'domains': [],
                    'ranges': []
                }
            if 'domain' in binding:
                prop_map[uri]['domains'].append(binding['domain']['value'])
            if 'range' in binding:
                prop_map[uri]['ranges'].append(binding['range']['value'])
        
        properties = list(prop_map.values())
        
        # Traiter les imports
        imports = [
            {
                'ontology': b['ontology']['value'],
                'imported': b['imported']['value']
            }
            for b in imports_result['results']['bindings']
        ]
        
        # Traiter les individus
        ind_map = {}
        for binding in individuals_result['results']['bindings']:
            uri = binding['ind']['value']
            if uri not in ind_map:
                ind_map[uri] = {
                    'uri': uri,
                    'type': binding['class']['value']
                }
        
        individuals = list(ind_map.values())
        
        # Liens entre individus
        links_query = """
            SELECT DISTINCT ?s ?p ?o
            WHERE {
                ?s ?p ?o .
                FILTER(isIRI(?s) && isIRI(?o))
                FILTER(?p != <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>)
                FILTER(?p != <http://www.w3.org/2000/01/rdf-schema#subClassOf>)
            }
        """
        
        links_result = fuseki_client.query(links_query)
        individual_links = [
            {
                'source': b['s']['value'],
                'target': b['o']['value'],
                'property': b['p']['value']
            }
            for b in links_result['results']['bindings']
        ]
        
        return {
            'classes': classes,
            'properties': properties,
            'imports': imports,
            'individuals': individuals,
            'individualLinks': individual_links
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/triples")
async def get_triples() -> Dict[str, Any]:
    """
    Liste tous les triplets du dataset
    """
    try:
        query = "SELECT ?s ?p ?o WHERE { ?s ?p ?o }"
        result = fuseki_client.query(query)
        
        triples = [
            {
                'subject': b['s']['value'],
                'predicate': b['p']['value'],
                'object': b['o']['value'],
                'objectType': b['o']['type']
            }
            for b in result['results']['bindings']
        ]
        
        return {'triples': triples}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/triples")
async def add_triples(request: Request) -> Dict[str, Any]:
    """
    Ajoute des triplets au dataset

    Body: [{"s": "uri", "p": "uri", "o": "value", "isLiteral": bool}]
    ou   {"triples": [...]}
    """
    try:
        body = await request.json()
        # Accepte soit une liste directe, soit {"triples": [...]}
        if isinstance(body, list):
            triples = body
        else:
            triples = body.get('triples', body)

        sparql_parts = ["INSERT DATA {"]
        for triple in triples:
            s = f"<{triple['s']}>"
            p = f"<{triple['p']}>"
            o = f'"{triple["o"]}"' if triple.get('isLiteral') else f"<{triple['o']}>"
            sparql_parts.append(f"  {s} {p} {o} .")
        sparql_parts.append("}")

        success = fuseki_client.update("\n".join(sparql_parts))
        return {'success': success, 'count': len(triples)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def create_entity(request: Request) -> Dict[str, Any]:
    """
    Cree une entite (class, individual, property) dans le dataset.
    Body: { type, uri, label?, comment?, additionalTriples? }
    """
    try:
        body = await request.json()
        entity_type = body.get('type', 'individual')
        uri = body.get('uri', '')
        label = body.get('label', '')
        comment = body.get('comment', '')
        additional = body.get('additionalTriples', [])

        if not uri:
            raise HTTPException(status_code=400, detail="uri is required")

        type_map = {
            'class':      OWL_CLASS,
            'property':   OWL_OP,
            'individual': OWL_NI,
        }
        rdf_type = type_map.get(entity_type, OWL_NI)

        parts = ["INSERT DATA {", f"  <{uri}> <{RDF_TYPE}> <{rdf_type}> ."]
        if label:
            parts.append(f'  <{uri}> <{RDFS_LABEL}> "{label}" .')
        if comment:
            parts.append(f'  <{uri}> <{RDFS_COMMENT}> "{comment}" .')
        for t in additional:
            p = t.get('p', '')
            o = t.get('o', '')
            if not p or not o:
                continue
            o_str = f'"{o}"' if t.get('isLiteral') else f'<{o}>'
            parts.append(f'  <{uri}> <{p}> {o_str} .')
        parts.append("}")

        fuseki_client.update("\n".join(parts))

        inserted = [
            {'s': uri, 'p': RDF_TYPE, 'o': rdf_type, 'isLiteral': False},
            *([{'s': uri, 'p': RDFS_LABEL, 'o': label, 'isLiteral': True}] if label else []),
            *([{'s': uri, 'p': RDFS_COMMENT, 'o': comment, 'isLiteral': True}] if comment else []),
            *[{'s': uri, 'p': t['p'], 'o': t['o'], 'isLiteral': t.get('isLiteral', False)}
              for t in additional if t.get('p') and t.get('o')],
        ]
        return {'success': True, 'uri': uri, 'triples': inserted}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suggestions/{class_uri:path}")
async def get_suggestions(class_uri: str) -> Dict[str, Any]:
    """
    Retourne les proprietes dont le domaine correspond a la classe
    (ou ses superclasses directes). Utilise par IndividualFields.
    """
    try:
        query = f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX owl:  <http://www.w3.org/2002/07/owl#>
            PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT DISTINCT ?prop ?range ?label ?comment
            WHERE {{
                {{
                    ?prop rdfs:domain <{class_uri}> .
                }} UNION {{
                    <{class_uri}> rdfs:subClassOf ?parent .
                    ?prop rdfs:domain ?parent .
                }}
                OPTIONAL {{ ?prop rdfs:range ?range }}
                OPTIONAL {{ ?prop rdfs:label ?label }}
                OPTIONAL {{ ?prop rdfs:comment ?comment }}
                FILTER(?prop != rdf:type)
            }}
        """
        result = fuseki_client.query(query)
        suggestions = [
            {
                'uri':     b['prop']['value'],
                'range':   b.get('range', {}).get('value'),
                'label':   b.get('label', {}).get('value'),
                'comment': b.get('comment', {}).get('value'),
            }
            for b in result['results']['bindings']
        ]
        return {'suggestions': suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/instances/{class_uri:path}")
async def get_instances(class_uri: str) -> Dict[str, Any]:
    """
    Retourne tous les individus d'une classe donnee.
    Utilise par IndividualFields pour les dropdowns.
    """
    try:
        query = f"""
            PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT DISTINCT ?s ?label
            WHERE {{
                ?s rdf:type <{class_uri}> .
                OPTIONAL {{ ?s rdfs:label ?label }}
            }}
        """
        result = fuseki_client.query(query)
        instances = [
            {
                'uri':   b['s']['value'],
                'label': b.get('label', {}).get('value'),
            }
            for b in result['results']['bindings']
        ]
        return {'instances': instances}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/populate")
async def populate(request: Request) -> Dict[str, Any]:
    """
    Genere N individus aleatoires a partir des classes et proprietes de l'ontologie.
    Body: { count: int }
    """
    import random
    import uuid
    try:
        body = await request.json()
        count = int(body.get('count', 100))

        # Recuperer les classes disponibles
        classes_q = """
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            SELECT DISTINCT ?class WHERE { ?class a owl:Class . FILTER(isIRI(?class)) }
        """
        classes_r = fuseki_client.query(classes_q)
        classes = [b['class']['value'] for b in classes_r['results']['bindings']]

        if not classes:
            return {'success': False, 'error': 'No classes found', 'count': 0, 'triples': []}

        # Recuperer les proprietes avec domaine/range
        props_q = """
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX owl:  <http://www.w3.org/2002/07/owl#>
            SELECT DISTINCT ?prop ?domain ?range WHERE {
                ?prop a owl:ObjectProperty .
                OPTIONAL { ?prop rdfs:domain ?domain }
                OPTIONAL { ?prop rdfs:range  ?range  }
            }
        """
        props_r = fuseki_client.query(props_q)
        props_by_domain: Dict[str, list] = {}
        for b in props_r['results']['bindings']:
            d = b.get('domain', {}).get('value')
            if d:
                props_by_domain.setdefault(d, []).append({
                    'uri':   b['prop']['value'],
                    'range': b.get('range', {}).get('value'),
                })

        all_triples = []
        sparql_parts = ["INSERT DATA {"]

        for _ in range(count):
            cls = random.choice(classes)
            uid = str(uuid.uuid4())[:8]
            local = cls.split('#')[-1].split('/')[-1]
            ind_uri = f"{BASE_URI}{local}_{uid}"

            sparql_parts.append(f"  <{ind_uri}> <{RDF_TYPE}> <{OWL_NI}> .")
            sparql_parts.append(f"  <{ind_uri}> <{RDF_TYPE}> <{cls}> .")
            all_triples += [
                {'s': ind_uri, 'p': RDF_TYPE, 'o': OWL_NI,  'isLiteral': False},
                {'s': ind_uri, 'p': RDF_TYPE, 'o': cls,     'isLiteral': False},
            ]

            for prop in props_by_domain.get(cls, []):
                rng = prop.get('range')
                if rng and not any(x in rng for x in ('string', 'integer', 'float', 'XMLSchema')):
                    # Object property — pointer vers un individu existant ou URI fictif
                    target = f"{BASE_URI}{rng.split('#')[-1].split('/')[-1]}_{str(uuid.uuid4())[:6]}"
                    sparql_parts.append(f"  <{ind_uri}> <{prop['uri']}> <{target}> .")
                    all_triples.append({'s': ind_uri, 'p': prop['uri'], 'o': target, 'isLiteral': False})
                else:
                    # Datatype property — valeur litterale generique
                    val = f"value_{str(uuid.uuid4())[:6]}"
                    sparql_parts.append(f'  <{ind_uri}> <{prop["uri"]}> "{val}" .')
                    all_triples.append({'s': ind_uri, 'p': prop['uri'], 'o': val, 'isLiteral': True})

        sparql_parts.append("}")
        fuseki_client.update("\n".join(sparql_parts))

        return {'success': True, 'count': count, 'triples': all_triples}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_dataset() -> Dict[str, Any]:
    """
    Vide le dataset et recharge les ontologies depuis les fichiers OWL sources.
    Equivalent du initializeStore() de l'ancien backend Node.js.
    """
    import sys
    import os
    import subprocess
    import platform
    from pathlib import Path

    try:
        # Vider le dataset via SPARQL
        fuseki_client.update("CLEAR ALL")

        # Recharger via tdbloader si disponible, sinon via HTTP
        root = Path(__file__).parent.parent.parent.parent
        sys.path.insert(0, str(root))
        from config import cfg

        owl_files = sorted(cfg.ontologies.owl_dir.rglob("*.owl"))
        if not owl_files:
            return {'success': False, 'error': 'No OWL files found'}

        # Essayer tdbloader (acces direct TDB2)
        is_win = platform.system() == "Windows"
        loader = cfg.jena.dir / ("bat/tdb2_tdbloader.bat" if is_win else "bin/tdb2.tdbloader")
        tdb_loc = cfg.jena.run_dir / "databases" / cfg.fuseki.dataset

        if loader.exists():
            env = os.environ.copy()
            env["JENA_HOME"] = str(cfg.jena.dir)
            cmd = ["cmd", "/c", str(loader)] if is_win else [str(loader)]
            subprocess.run(
                cmd + ["--loc", str(tdb_loc)] + [str(f) for f in owl_files],
                env=env, capture_output=True, timeout=120
            )
        else:
            # Fallback : POST HTTP vers /data
            import requests as req
            for owl in owl_files:
                content = owl.read_bytes()
                req.post(
                    cfg.fuseki.data_url,
                    data=content,
                    headers={"Content-Type": "application/rdf+xml"},
                    timeout=60
                )

        # Compter les triplets
        stats = fuseki_client.get_stats()
        return {'success': True, 'size': stats.get('triples', 0)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
