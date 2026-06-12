import { fetchApi } from './apiClient';

export interface SparqlBinding {
  type: string;
  value: string;
  datatype?: string;
  'xml:lang'?: string;
}

export interface SparqlResult {
  update?: boolean;
  message?: string;
  head?: { vars: string[] };
  results?: {
    bindings: Record<string, SparqlBinding>[];
  };
}

export async function executeQuery(query: string): Promise<SparqlResult> {
  const res = await fetchApi('sparql', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/sparql-results+json',
    },
    body: JSON.stringify({ query }),
  });
  return res.json();
}

let _cachedAllEntities: any[] | null = null;

/**
 * Fetch all distinct entities (Subjects, Predicates, Objects) to ensure NOTHING is missed
 * Also fetches their rdf:type for visual categorization
 */
export async function fetchAllEntities(forceRefresh: boolean = false) {
  if (_cachedAllEntities && !forceRefresh) {
    return _cachedAllEntities;
  }

  const query = `
    SELECT ?uri (GROUP_CONCAT(DISTINCT ?t; separator=",") AS ?types) WHERE {
      {
        { ?uri ?p ?o . }
        UNION
        { ?s ?uri ?o . }
        UNION
        { ?s ?p ?uri . }
        FILTER(isIRI(?uri))
      }
      OPTIONAL { ?uri <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?t . FILTER(isIRI(?t)) }
    }
    GROUP BY ?uri
    ORDER BY ?uri
  `;
  const data = await executeQuery(query);
  _cachedAllEntities = data.results?.bindings?.map(b => ({
    uri: b.uri.value,
    label: b.uri.value.split(/[/#]/).pop() || b.uri.value,
    types: b.types && b.types.value ? b.types.value.split(',') : [],
  })) || [];
  return _cachedAllEntities;
}

// --- Matrix Cache ---
let _cachedMatrixColumns: string[] | null = null;
let _cachedMatrixRows: Record<string, { rows: string[], total: number }> = {};
let _cachedMatrixCells: Record<string, string> = {}; // key: "s_p"

export function clearMatrixCache() {
  _cachedMatrixColumns = null;
  _cachedMatrixRows = {};
  _cachedMatrixCells = {};
}

/**
 * Fetch all unique predicates used in the ontology (for Matrix columns)
 */
export async function fetchMatrixColumns(forceRefresh: boolean = false) {
  if (_cachedMatrixColumns && !forceRefresh) return _cachedMatrixColumns;

  const query = `
    SELECT DISTINCT ?p WHERE {
      ?s ?p ?o .
    }
    ORDER BY ?p
  `;
  const data = await executeQuery(query);
  _cachedMatrixColumns = data.results?.bindings?.map(b => b.p.value) || [];
  return _cachedMatrixColumns;
}

/**
 * Fetch unique subjects (rows) with pagination and optional search
 */
export async function fetchMatrixRows(page: number, pageSize: number, search: string = '', forceRefresh: boolean = false) {
  const cacheKey = `${page}_${pageSize}_${search}`;
  if (_cachedMatrixRows[cacheKey] && !forceRefresh) return _cachedMatrixRows[cacheKey];

  const offset = page * pageSize;
  const filter = search ? `FILTER(regex(str(?s), "${search}", "i"))` : '';
  
  const query = `
    SELECT DISTINCT ?s WHERE {
      ?s ?p ?o .
      FILTER(isIRI(?s))
      ${filter}
    }
    ORDER BY ?s
    LIMIT ${pageSize}
    OFFSET ${offset}
  `;
  
  const countQuery = `
    SELECT (COUNT(DISTINCT ?s) AS ?total) WHERE {
      {
        SELECT DISTINCT ?s WHERE {
          ?s ?p ?o .
          FILTER(isIRI(?s))
          ${filter}
        }
      }
    }
  `;
  
  const [data, countData] = await Promise.all([
    executeQuery(query),
    executeQuery(countQuery)
  ]);
  
  const total = parseInt(countData.results?.bindings?.[0]?.total?.value || '0', 10);
  const rows = data.results?.bindings?.map(b => b.s.value) || [];
  
  _cachedMatrixRows[cacheKey] = { rows, total };
  return _cachedMatrixRows[cacheKey];
}

/**
 * Fetch matrix cells for given rows (subjects)
 */
export async function fetchMatrixCells(subjects: string[], forceRefresh: boolean = false) {
  if (subjects.length === 0) return [];
  
  // Find which subjects we need to fetch
  const missingSubjects = forceRefresh ? subjects : subjects.filter(s => 
    // If we don't have ANY cell cached for this subject, we assume it's missing.
    // A better approach is caching by subject. We'll fetch all missing ones.
    !Object.keys(_cachedMatrixCells).some(key => key.startsWith(`${s}_`))
  );

  if (missingSubjects.length > 0) {
    const urisStr = missingSubjects.map(u => `<${u}>`).join(' ');
    const query = `
      SELECT ?s ?p (GROUP_CONCAT(?o; separator="|") AS ?values) WHERE {
        VALUES ?s { ${urisStr} }
        ?s ?p ?o .
      }
      GROUP BY ?s ?p
    `;
    
    const data = await executeQuery(query);
    data.results?.bindings?.forEach(b => {
      _cachedMatrixCells[`${b.s.value}_${b.p.value}`] = b.values ? b.values.value : '';
    });

    // Mark missing subjects as fetched even if they have no properties
    missingSubjects.forEach(s => {
      // Just to have at least one key so it's not fetched again, we can add a dummy
      if (!Object.keys(_cachedMatrixCells).some(key => key.startsWith(`${s}_`))) {
        _cachedMatrixCells[`${s}___fetched`] = '1';
      }
    });
  }

  // Return formatted array from cache
  const result: any[] = [];
  subjects.forEach(s => {
    Object.keys(_cachedMatrixCells).forEach(key => {
      if (key.startsWith(`${s}_`) && !key.endsWith('__fetched')) {
        const p = key.substring(s.length + 1);
        result.push({ s, p, values: _cachedMatrixCells[key] });
      }
    });
  });
  
  return result;
}

/**
 * Update a matrix cell (delete old values and insert new values)
 */
export async function updateMatrixCell(s: string, p: string, newValuesStr: string) {
  const deleteQuery = `
    DELETE { <${s}> <${p}> ?o }
    WHERE { <${s}> <${p}> ?o }
  `;
  await executeQuery(deleteQuery);
  
  // Update cache locally
  _cachedMatrixCells[`${s}_${p}`] = newValuesStr;

  if (!newValuesStr.trim()) return true;
  
  const values = newValuesStr.split('|').map(v => v.trim()).filter(v => v.length > 0);
  if (values.length === 0) return true;
  
  const insertTriples = values.map(v => {
    if (v.startsWith('http://') || v.startsWith('https://')) {
      return `<${s}> <${p}> <${v}> .`;
    } else {
      const safeVal = v.replace(/"/g, '\\"');
      return `<${s}> <${p}> "${safeVal}" .`;
    }
  }).join('\n      ');
  
  const insertQuery = `
    INSERT DATA {
      ${insertTriples}
    }
  `;
  
  await executeQuery(insertQuery);
  return true;
}

/**
 * Add a new entity
 */
export async function addEntity(uri: string, typeUri: string) {
  const insertQuery = `
    INSERT DATA {
      <${uri}> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <${typeUri}> .
    }
  `;
  await executeQuery(insertQuery);
  
  // Invalidate rows cache since a new row is added
  _cachedMatrixRows = {};
  
  return true;
}

/**
 * Fetch agnostic children (all IRI objects of a subject)
 */
export async function fetchAgnosticChildren(subjectUri: string) {
  const query = `
    SELECT DISTINCT ?p ?o WHERE {
      <${subjectUri}> ?p ?o .
      FILTER(isIRI(?o))
    }
    ORDER BY ?p ?o
  `;
  const data = await executeQuery(query);
  return data.results?.bindings?.map(b => ({
    uri: b.o.value,
    predicate: b.p.value,
    label: `${b.p.value.split(/[/#]/).pop()} ➝ ${b.o.value.split(/[/#]/).pop() || b.o.value}`,
    type: 'subject'
  })) || [];
}

/**
 * Fetch all properties for a given URI (Wiki view)
 */
export async function fetchEntityDetails(uri: string) {
  const query = `
    SELECT ?p ?o WHERE {
      <${uri}> ?p ?o .
    }
    ORDER BY ?p
  `;
  const data = await executeQuery(query);
  return data.results?.bindings?.map(b => ({
    predicate: b.p.value,
    object: b.o.value,
    isLiteral: b.o.type === 'literal' || b.o.type === 'typed-literal',
    datatype: b.o.datatype,
    lang: b.o['xml:lang'],
  })) || [];
}

/**
 * Fetch local graph for D3 iteratively to handle any depth without SPARQL explosion.
 */
export async function fetchLocalGraph(centerUri: string, maxDepth: number = 1) {
  const visitedNodes = new Set<string>();
  const edgesMap = new Map<string, any>();
  
  let currentFrontier = [centerUri];
  visitedNodes.add(centerUri);

  for (let currentDepth = 1; currentDepth <= maxDepth; currentDepth++) {
      if (currentFrontier.length === 0) break;
      
      // Batch nodes to avoid URL/Query length limits
      const batchSize = 50;
      const newFrontier = new Set<string>();
      
      for (let i = 0; i < currentFrontier.length; i += batchSize) {
          const batch = currentFrontier.slice(i, i + batchSize);
          const urisStr = batch.map(u => `<${u}>`).join(' ');
          
          const query = `
            SELECT DISTINCT ?s ?p ?o WHERE {
              VALUES ?center { ${urisStr} }
              { ?center ?p ?o . FILTER(isIRI(?o)) BIND(?center AS ?s) }
              UNION
              { ?s ?p ?center . FILTER(isIRI(?s)) BIND(?center AS ?o) }
            }
            LIMIT 2000
          `;
          
          try {
              const data = await executeQuery(query);
              data.results?.bindings?.forEach(b => {
                  const s = b.s.value;
                  const p = b.p.value;
                  const o = b.o.value;
                  const edgeKey = `${s}|${p}|${o}`;
                  
                  if (!edgesMap.has(edgeKey)) {
                      edgesMap.set(edgeKey, { source: s, predicate: p, target: o });
                  }
                  
                  if (!visitedNodes.has(s)) {
                      visitedNodes.add(s);
                      newFrontier.add(s);
                  }
                  if (!visitedNodes.has(o)) {
                      visitedNodes.add(o);
                      newFrontier.add(o);
                  }
              });
          } catch (e) {
              console.error("Error fetching graph depth batch", e);
          }
      }
      
      currentFrontier = Array.from(newFrontier);
      // Failsafe limit
      if (edgesMap.size > 5000) break;
  }
  
  return Array.from(edgesMap.values());
}

/**
 * Fetch suggested predicates for a subject based on:
 * 1. Predicates it already uses
 * 2. Predicates used by siblings (instances of the same class)
 * 3. Schema domains (if defined)
 * 4. Schema domains of superclasses
 */
export async function fetchSuggestedPredicates(subjectUri: string) {
  const query = `
    SELECT DISTINCT ?p WHERE {
      {
        # 1. Properties it already has
        <${subjectUri}> ?p [] .
      }
      UNION
      {
        # 2. Properties used by siblings
        <${subjectUri}> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?class .
        [] <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?class ;
           ?p [] .
      }
      UNION
      {
        # 3. Schema domains
        <${subjectUri}> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?class .
        ?p <http://www.w3.org/2000/01/rdf-schema#domain> ?class .
      }
      UNION
      {
        # 4. Properties based on superclasses
        <${subjectUri}> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?class .
        ?class <http://www.w3.org/2000/01/rdf-schema#subClassOf>+ ?superClass .
        ?p <http://www.w3.org/2000/01/rdf-schema#domain> ?superClass .
      }
      FILTER(isIRI(?p))
    }
  `;
  const data = await executeQuery(query);
  return data.results?.bindings?.map(b => ({
    uri: b.p.value,
    label: b.p.value.split(/[/#]/).pop() || b.p.value
  })) || [];
}

/**
 * Fetch suggested objects (links) for a given subject and predicate based on:
 * 1. Existing objects for this exact subject and predicate
 * 2. Objects used by siblings for this predicate
 * 3. Instances of the range class of this predicate
 */
export async function fetchSuggestedObjects(subjectUri: string, predicateUri: string) {
  const query = `
    SELECT DISTINCT ?o WHERE {
      {
        # 1. Existing objects for this exact subject and predicate
        <${subjectUri}> <${predicateUri}> ?o .
        FILTER(isIRI(?o))
      }
      UNION
      {
        # 2. Objects used by siblings for this predicate
        <${subjectUri}> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?class .
        ?s <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?class ;
           <${predicateUri}> ?o .
        FILTER(isIRI(?o))
      }
      UNION
      {
        # 3. Instances of the range class of this predicate
        <${predicateUri}> <http://www.w3.org/2000/01/rdf-schema#range> ?rangeClass .
        ?o <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?rangeClass .
        FILTER(isIRI(?o))
      }
    }
    LIMIT 50
  `;
  const data = await executeQuery(query);
  return data.results?.bindings?.map(b => ({
    uri: b.o.value,
    label: b.o.value.split(/[/#]/).pop() || b.o.value
  })) || [];
}

/**
 * Fetch all classes in the ontology
 */
export async function fetchOntologyClasses() {
  const query = `
    SELECT DISTINCT ?class WHERE {
      { ?class a <http://www.w3.org/2002/07/owl#Class> }
      UNION
      { ?class a <http://www.w3.org/2000/01/rdf-schema#Class> }
      UNION
      { [] a ?class }
      FILTER(isIRI(?class))
    }
    ORDER BY ?class
  `;
  const data = await executeQuery(query);
  return data.results?.bindings?.map(b => ({
    uri: b.class.value,
    label: b.class.value.split(/[/#]/).pop() || b.class.value
  })) || [];
}

/**
 * Fetch the schema (properties and their ranges) for a given class
 */
export async function fetchClassSchema(classUri: string) {
  const query = `
    SELECT DISTINCT ?p ?range WHERE {
      {
        ?p <http://www.w3.org/2000/01/rdf-schema#domain> <${classUri}> .
      }
      UNION
      {
        <${classUri}> <http://www.w3.org/2000/01/rdf-schema#subClassOf>+ ?superClass .
        ?p <http://www.w3.org/2000/01/rdf-schema#domain> ?superClass .
      }
      OPTIONAL { ?p <http://www.w3.org/2000/01/rdf-schema#range> ?range . }
      FILTER(isIRI(?p))
    }
  `;
  const data = await executeQuery(query);
  return data.results?.bindings?.map(b => ({
    propertyUri: b.p.value,
    propertyLabel: b.p.value.split(/[/#]/).pop() || b.p.value,
    rangeUri: b.range ? b.range.value : null
  })) || [];
}

/**
 * Fetch existing instances of a given class
 */
export async function fetchInstancesOfClass(classUri: string) {
  const query = `
    SELECT DISTINCT ?instance WHERE {
      ?instance a <${classUri}> .
      FILTER(isIRI(?instance))
    }
    LIMIT 1000
  `;
  const data = await executeQuery(query);
  return data.results?.bindings?.map(b => b.instance.value) || [];
}

/**
 * 20 pre-configured SPARQL query presets for the Explorer UI
 */
export const SPARQL_PRESETS = [
  {
    name: "Tout lister (10 résultats)",
    query: "SELECT * WHERE {\n  ?s ?p ?o .\n}\nLIMIT 10"
  },
  {
    name: "Lister tous les GameElements",
    query: "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nPREFIX nsxai: <http://nsxai.org/ontology#>\nSELECT ?ge WHERE {\n  ?ge rdf:type nsxai:GameElementResource .\n}\nLIMIT 50"
  },
  {
    name: "Lister toutes les GamifiedResources",
    query: "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nPREFIX nsxai: <http://nsxai.org/ontology#>\nSELECT ?gr WHERE {\n  ?gr rdf:type nsxai:GamifiedResource .\n}\nLIMIT 50"
  },
  {
    name: "Statistiques : Nombre de triplets",
    query: "SELECT (COUNT(*) AS ?count) WHERE {\n  ?s ?p ?o .\n}"
  },
  {
    name: "Statistiques : Propriétés les plus utilisées",
    query: "SELECT ?p (COUNT(?p) AS ?count) WHERE {\n  ?s ?p ?o .\n}\nGROUP BY ?p\nORDER BY DESC(?count)\nLIMIT 10"
  },
  {
    name: "Génération de Masse (Exemple : Points)",
    query: "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nPREFIX nsxai: <http://nsxai.org/ontology#>\nINSERT DATA {\n  <http://nsxai.org/data/GeneratedPoint_1> rdf:type nsxai:Points .\n  <http://nsxai.org/data/GeneratedPoint_2> rdf:type nsxai:Points .\n  <http://nsxai.org/data/GeneratedPoint_3> rdf:type nsxai:Points .\n}"
  },
  {
    name: "Nettoyer les données générées (Data Namespace)",
    query: "DELETE WHERE {\n  ?s ?p ?o .\n  FILTER(STRSTARTS(STR(?s), \"http://nsxai.org/data/Generated\"))\n}"
  },
  {
    name: "Rechercher par DataProperty (Downloads > 1000)",
    query: "PREFIX nsxai: <http://nsxai.org/ontology#>\nSELECT ?ge ?downloads WHERE {\n  ?ge nsxai:has_totalDownloads ?downloads .\n  FILTER(xsd:integer(?downloads) > 1000)\n}"
  },
  {
    name: "Classes et Nombre d'instances",
    query: "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nSELECT ?class (COUNT(?s) AS ?count) WHERE {\n  ?s rdf:type ?class .\n  FILTER(isIRI(?class))\n}\nGROUP BY ?class\nORDER BY DESC(?count)"
  },
  {
    name: "Profil Utilisateur (Sara)",
    query: "PREFIX nsxai: <http://nsxai.org/ontology#>\nSELECT * WHERE {\n  <http://nsxai.org/data/Sara> ?p ?o .\n}"
  },
  {
    name: "GamifiedResources à but d'Assessment",
    query: "PREFIX nsxai: <http://nsxai.org/ontology#>\nSELECT ?gr WHERE {\n  ?gr nsxai:has_Purpose \"Assessment\" .\n}"
  },
  {
    name: "GamifiedResources avec priorité Essential",
    query: "PREFIX nsxai: <http://nsxai.org/ontology#>\nSELECT ?gr WHERE {\n  ?gr nsxai:has_Priority \"Essential\" .\n}"
  },
  {
    name: "GameElements : Type Badge",
    query: "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nPREFIX nsxai: <http://nsxai.org/ontology#>\nSELECT ?badge WHERE {\n  ?badge rdf:type nsxai:Badge .\n}"
  },
  {
    name: "Lien GamifiedResource -> GameElement",
    query: "PREFIX nsxai: <http://nsxai.org/ontology#>\nSELECT ?gr ?ge WHERE {\n  ?gr nsxai:can_be_gamified_with ?ge .\n}"
  },
  {
    name: "Supprimer tout (DANGEREUX)",
    query: "CLEAR DEFAULT"
  },
  {
    name: "Ajouter un Joueur Test",
    query: "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nPREFIX nsxai: <http://nsxai.org/ontology#>\nINSERT DATA {\n  <http://nsxai.org/data/TestPlayer> rdf:type nsxai:Learner ;\n    nsxai:has_PlayingStyle \"Achiever\" ;\n    nsxai:experienceLevel \"1\" .\n}"
  },
  {
    name: "GameElements sans Downloads",
    query: "PREFIX nsxai: <http://nsxai.org/ontology#>\nSELECT ?ge WHERE {\n  ?ge a nsxai:GameElementResource .\n  FILTER NOT EXISTS { ?ge nsxai:has_totalDownloads ?d }\n}"
  },
  {
    name: "Top 5 GameElements par Likes",
    query: "PREFIX nsxai: <http://nsxai.org/ontology#>\nSELECT ?ge ?likes WHERE {\n  ?ge nsxai:has_totalLikes ?likes .\n}\nORDER BY DESC(xsd:integer(?likes))\nLIMIT 5"
  },
  {
    name: "GamifiedResources avec durée > 1h",
    query: "PREFIX nsxai: <http://nsxai.org/ontology#>\nSELECT ?gr ?dur WHERE {\n  ?gr nsxai:has_duration ?dur .\n  FILTER(xsd:integer(?dur) > 60)\n}"
  },
  {
    name: "Mettre à jour la priorité d'une GR",
    query: "PREFIX nsxai: <http://nsxai.org/ontology#>\nDELETE { ?gr nsxai:has_Priority ?old }\nINSERT { ?gr nsxai:has_Priority \"Essential\" }\nWHERE {\n  ?gr nsxai:has_Priority ?old .\n  FILTER(?gr = <http://nsxai.org/data/SomeResource>)\n}"
  }
];
