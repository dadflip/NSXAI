export const CONFIG = {
  app: {
    name: import.meta.env.VITE_APP_NAME || 'NSXAI',
    description: import.meta.env.VITE_APP_DESC || '',
  },
  model: {
    defaultEndpoint: import.meta.env.VITE_DEFAULT_MODEL_ENDPOINT || 'http://localhost:5000/predict'
  },
  api: {
    base:
      import.meta.env.VITE_API_BASE ||
      (import.meta.env.DEV ? '' : import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'),
    endpoints: {
      architecture: import.meta.env.VITE_API_ENDPOINT_ARCHITECTURE || '/api/ontology/architecture',
      triples: import.meta.env.VITE_API_ENDPOINT_TRIPLES || '/api/ontology/triples',
      sparql: import.meta.env.VITE_API_ENDPOINT_SPARQL || '/api/sparql',
      suggestions: import.meta.env.VITE_API_ENDPOINT_SUGGESTIONS || '/api/ontology/suggestions',
      instances: import.meta.env.VITE_API_ENDPOINT_INSTANCES || '/api/ontology/instances',
      objects: import.meta.env.VITE_API_ENDPOINT_OBJECTS || '/api/ontology/objects',
      create: import.meta.env.VITE_API_ENDPOINT_CREATE || '/api/ontology/create',
      predicates: import.meta.env.VITE_API_ENDPOINT_PREDICATES || '/api/ontology/predicates',
      reset: import.meta.env.VITE_API_ENDPOINT_RESET || '/api/ontology/reset',
    }
  },
  ontology: {
    defaultBaseUri: import.meta.env.VITE_DEFAULT_BASE_URI || 'https://lms.flipova.fr/nsxai/v1/ontologies/data#',
    generatedLocalPrefix: import.meta.env.VITE_GENERATED_LOCAL_PREFIX || 'Generated',
  },
  explorer: {
    defaultMaxDepth: parseInt(import.meta.env.VITE_DEFAULT_MAX_DEPTH || '5', 10),
    refreshIntervalMs: parseInt(import.meta.env.VITE_REFRESH_INTERVAL_MS || '15000', 10),
  },
  sparql: {
    defaultQuery: `PREFIX owl: <http://www.w3.org/2002/07/owl#>\nSELECT ?class WHERE {\n  ?class a owl:Class .\n}\nLIMIT ${import.meta.env.VITE_SPARQL_DEFAULT_LIMIT || '20'}`,
  },
};

export function apiUrl(path: string): string {
  return `${CONFIG.api.base}${path}`;
}
