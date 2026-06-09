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
            SELECT DISTINCT ?prop ?range ?label ?comment ?propType
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
                OPTIONAL {{ ?prop a ?propType }}
                FILTER(?prop != rdf:type)
            }}
        """
        result = fuseki_client.query(query)
        # Collect data per prop to handle multiple types
        prop_data: dict = {}
        for b in result['results']['bindings']:
            uri = b['prop']['value']
            if uri not in prop_data:
                prop_data[uri] = {
                    'uri':     uri,
                    'range':   b.get('range', {}).get('value'),
                    'label':   b.get('label', {}).get('value'),
                    'comment': b.get('comment', {}).get('value'),
                    'type':    None,
                }
            prop_type_val = b.get('propType', {}).get('value')
            if prop_type_val and not prop_data[uri]['type']:
                prop_data[uri]['type'] = prop_type_val
        suggestions = list(prop_data.values())
        return {'suggestions': suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predicates/{subject_uri:path}")
async def get_predicates_for_subject(subject_uri: str) -> Dict[str, Any]:
    """
    Prédicats applicables à un sujet (parcours triplet agnostique).
    Combine schéma (domain/range), assertions existantes sur le type, et propriétés du graphe.
    """
    try:
        query = f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX owl:  <http://www.w3.org/2002/07/owl#>
            PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT DISTINCT ?prop ?domain ?range ?label ?comment ?source ?propType
            WHERE {{
                BIND(<{subject_uri}> AS ?sub)
                OPTIONAL {{ ?sub rdf:type ?type . FILTER(?type != owl:Class && ?type != owl:ObjectProperty && ?type != owl:DatatypeProperty) }}
                {{
                    ?prop rdfs:domain ?dom .
                    FILTER(!BOUND(?type) || ?dom = ?type || EXISTS {{ ?type rdfs:subClassOf+ ?dom }})
                    BIND(?dom AS ?domain)
                    BIND("schema" AS ?source)
                }} UNION {{
                    ?other rdf:type ?type .
                    ?other ?prop ?o .
                    FILTER(?other != ?sub)
                    OPTIONAL {{ ?prop rdfs:domain ?dom2 }} BIND(?dom2 AS ?domain)
                    BIND("topology" AS ?source)
                }} UNION {{
                    ?sub ?prop ?existing .
                    FILTER(?prop != rdf:type)
                    OPTIONAL {{ ?prop rdfs:domain ?dom3 }} BIND(?dom3 AS ?domain)
                    BIND("assertion" AS ?source)
                }} UNION {{
                    ?prop a ?pt .
                    FILTER(?pt IN (owl:ObjectProperty, owl:DatatypeProperty))
                    OPTIONAL {{ ?prop rdfs:domain ?dom4 }} BIND(?dom4 AS ?domain)
                    BIND("graph" AS ?source)
                }}
                OPTIONAL {{ ?prop rdfs:range ?range }}
                OPTIONAL {{ ?prop rdfs:label ?label }}
                OPTIONAL {{ ?prop rdfs:comment ?comment }}
                OPTIONAL {{ ?prop a ?propType }}
                FILTER(?prop != rdf:type)
            }}
            ORDER BY ?prop
            LIMIT 200
        """
        result = fuseki_client.query(query)
        # Collect all domains per prop (a prop can have multiple domains)
        prop_data: dict = {}
        for b in result['results']['bindings']:
            uri = b['prop']['value']
            if uri not in prop_data:
                prop_data[uri] = {
                    'uri':     uri,
                    'domains': set(),
                    'range':   b.get('range', {}).get('value'),
                    'label':   b.get('label', {}).get('value'),
                    'comment': b.get('comment', {}).get('value'),
                    'source':  b.get('source', {}).get('value', 'graph'),
                    'type':    None,
                }
            domain_val = b.get('domain', {}).get('value')
            if domain_val:
                prop_data[uri]['domains'].add(domain_val)
            prop_type_val = b.get('propType', {}).get('value')
            if prop_type_val and not prop_data[uri]['type']:
                # Only set the first type we find (a prop can have multiple types but we want the primary one)
                prop_data[uri]['type'] = prop_type_val
        predicates = []
        for p in prop_data.values():
            predicates.append({
                'uri':     p['uri'],
                'domains': list(p['domains']),
                'range':   p['range'],
                'label':   p['label'],
                'comment': p['comment'],
                'source':  p['source'],
                'type':    p['type'],
            })
        return {'predicates': predicates, 'subject': subject_uri}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/objects")
async def get_objects_for_predicate(subject_uri: str, predicate_uri: str, range_uri: str = None) -> Dict[str, Any]:
    """
    Objets candidats pour un prédicat donné (sélection ou instanciation).
    """
    try:
        if not range_uri:
            range_q = f"""
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                SELECT ?range WHERE {{
                    OPTIONAL {{ <{predicate_uri}> rdfs:range ?range }}
                }} LIMIT 1
            """
            range_r = fuseki_client.query(range_q)
            if range_r['results']['bindings']:
                range_uri = range_r['results']['bindings'][0].get('range', {}).get('value')

        is_datatype = range_uri and any(
            x in range_uri.lower() for x in ('xmlschema', 'literal', 'string', 'integer', 'float', 'boolean', 'date')
        )

        candidates: List[Dict[str, Any]] = []
        if is_datatype:
            candidates.append({
                'uri': '',
                'label': 'Valeur littérale',
                'kind': 'literal',
                'datatype': range_uri,
            })
        elif range_uri:
            is_any_resource = any(x in range_uri.lower() for x in ('#resource', '/resource', '#thing', '/thing'))
            if is_any_resource:
                inst_q = f"""
                    PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                    PREFIX owl:  <http://www.w3.org/2002/07/owl#>
                    SELECT DISTINCT ?s ?label WHERE {{
                        ?s rdf:type ?type .
                        FILTER(?type NOT IN (owl:Class, owl:ObjectProperty, owl:DatatypeProperty, owl:AnnotationProperty, owl:Ontology))
                        OPTIONAL {{ ?s rdfs:label ?label }}
                    }} LIMIT 300
                """
            else:
                inst_q = f"""
                    PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                    SELECT DISTINCT ?s ?label WHERE {{
                        ?s rdf:type <{range_uri}> .
                        OPTIONAL {{ ?s rdfs:label ?label }}
                    }} LIMIT 100
                """
            inst_r = fuseki_client.query(inst_q)
            for b in inst_r['results']['bindings']:
                candidates.append({
                    'uri':   b['s']['value'],
                    'label': b.get('label', {}).get('value'),
                    'kind':  'instance',
                })
            candidates.append({
                'uri':   '',
                'label': f'Instancier nouveau ({range_uri.split("#")[-1].split("/")[-1]})',
                'kind':  'new_instance',
                'classUri': range_uri,
            })
        else:
            obj_q = f"""
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                SELECT DISTINCT ?o ?label WHERE {{
                    ?s <{predicate_uri}> ?o .
                    FILTER(isIRI(?o))
                    OPTIONAL {{ ?o rdfs:label ?label }}
                }} LIMIT 80
            """
            obj_r = fuseki_client.query(obj_q)
            for b in obj_r['results']['bindings']:
                candidates.append({
                    'uri':   b['o']['value'],
                    'label': b.get('label', {}).get('value'),
                    'kind':  'iri',
                })
            candidates.append({
                'uri':   '',
                'label': 'Nouvelle ressource (URI)',
                'kind':  'new_uri',
            })

        return {
            'subject': subject_uri,
            'predicate': predicate_uri,
            'range': range_uri,
            'isLiteral': is_datatype,
            'candidates': candidates,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/triples")
async def delete_triple(request: Request) -> Dict[str, Any]:
    """
    Supprime un triplet S-P-O du dataset.
    Body: { "s": "uri", "p": "uri", "o": "value", "isLiteral": bool }
    """
    try:
        body = await request.json()
        s = body.get('s', '')
        p = body.get('p', '')
        o = body.get('o', '')
        is_literal = body.get('isLiteral', False)

        if not s or not p or not o:
            raise HTTPException(status_code=400, detail="s, p, o are required")

        s_str = f"<{s}>"
        p_str = f"<{p}>"
        
        # Escape quotes in literal values
        if is_literal:
            escaped_o = o.replace('\\', '\\\\').replace('"', '\\"')
            sparql = f"""
                DELETE {{ {s_str} {p_str} ?o . }}
                WHERE {{
                    {s_str} {p_str} ?o .
                    FILTER(isLiteral(?o) && str(?o) = "{escaped_o}")
                }}
            """
        else:
            o_str = f"<{o}>"
            sparql = f"DELETE WHERE {{ {s_str} {p_str} {o_str} . }}"
            
        success = fuseki_client.update(sparql)
        return {'success': success}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        print(f"DELETE triple error: {error_detail}")
        raise HTTPException(status_code=500, detail=error_detail)


@router.post("/path")
async def create_triplet_path(request: Request) -> Dict[str, Any]:
    """
    Persiste un parcours S-P-O (chaîne de triplets).
    Body: {{ "steps": [{{ "subject", "predicate", "object", "isLiteral"?, "datatype"? }}], "root"? }}
    """
    try:
        body = await request.json()
        steps = body.get('steps', [])
        if not steps:
            raise HTTPException(status_code=400, detail="steps is required")

        parts = ["INSERT DATA {"]
        inserted = []
        for step in steps:
            s = step.get('subject', '')
            p = step.get('predicate', '')
            o = step.get('object', '')
            if not s or not p or not o:
                continue
            is_lit = step.get('isLiteral', False)
            if is_lit:
                dt = step.get('datatype')
                o_str = f'"{o}"' + (f"^^{dt}" if dt else '')
            else:
                o_str = f'<{o}>'
            parts.append(f'  <{s}> <{p}> {o_str} .')
            inserted.append({
                's': s, 'p': p, 'o': o,
                'isLiteral': is_lit,
            })
        parts.append("}")
        if len(inserted) == 0:
            raise HTTPException(status_code=400, detail="no valid steps")
        fuseki_client.update("\n".join(parts))
        return {'success': True, 'count': len(inserted), 'triples': inserted}
    except HTTPException:
        raise
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
    Peuplement en cascade S-P-O (racines typées + chaînes de prédicats).
    Body: { count: int, chainDepth?: int (0-5), reuseProbability?: float }
    """
    try:
        from ..services.ontology_populate import populate_triplet_cascade

        try:
            body = await request.json()
        except Exception:
            body = {}
        count = int(body.get("count", 50))
        chain_depth = int(body.get("chainDepth", body.get("depth", 2)))
        reuse = float(body.get("reuseProbability", 0.35))
        chain_depth = max(0, min(chain_depth, 5))
        count = max(1, min(count, 500))

        result = populate_triplet_cascade(
            count=count,
            chain_depth=chain_depth,
            reuse_probability=reuse,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "populate failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_dataset() -> Dict[str, Any]:
    """
    Vide le dataset et recharge les ontologies OWL/TTL (HTTP GSP, comme load_ontologies.py).
    """
    try:
        from ..services.ontology_store import reload_ontology_store

        result = reload_ontology_store()
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "reset failed"),
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
