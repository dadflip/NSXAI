import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Database, Play, Server, ListTree, ChevronRight, ChevronDown, Layers, Box, Globe, Users, Network, Search, BrainCircuit, Download, PlugZap, Shield } from 'lucide-react';
import * as d3 from 'd3';
import OntologyGraph from './components/OntologyGraph';
import SparqlResultsView from './components/SparqlResults';
import { AgnosticTripleTree } from './components/AgnosticTripleTree';
import { AgnosticTreeVisualizer } from './components/AgnosticTreeVisualizer';
import { ExportStudio } from './components/ExportStudio';
import { PipelineStudio } from './components/PipelineStudio';
import { ShaclManager } from './components/ShaclManager';
import { RuleManager } from './components/RuleManager';
import { apiUrl } from './lib/api';

function TreeFolder({ title, subtitle, children, defaultOpen = false, icon, origin }: any) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  return (
    <div className="mb-1">
      <div 
        className="flex items-center gap-2 py-1.5 px-2 hover:bg-indigo-500/10 rounded-md cursor-pointer select-none transition-colors"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="text-neutral-400">
           {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </span>
        {icon && <span className="text-indigo-400">{icon}</span>}
        <span className="font-mono text-[13px] font-medium text-neutral-200">{title}</span>
        {origin && <span className="ml-auto text-[10px] font-mono text-neutral-400 bg-neutral-900 px-1.5 py-0.5 rounded border border-neutral-700" title="Fichier source">{origin}</span>}
        {subtitle && <span className="text-[11px] text-neutral-400 bg-neutral-900 px-1.5 rounded">{subtitle}</span>}
      </div>
      {isOpen && (
        <div className="ml-5 pl-3 border-l-2 border-indigo-500/30 my-1">
          {children}
        </div>
      )}
    </div>
  );
}

function TreeProperty({ p, getShortUri, getOrigin }: any) {
  const origin = getOrigin(p.uri);
  return (
    <div className="py-1.5 px-2 flex items-start gap-2 hover:bg-orange-500/10 rounded-md transition-colors group">
      <div className="mt-1">
         <div className="w-1.5 h-1.5 rounded-full bg-orange-500 shadow-sm" />
      </div>
      <div className="flex-1 leading-snug">
        <div className="flex items-center justify-between">
            <div className="font-mono text-[13px] text-neutral-300 group-hover:text-orange-300 transition-colors">
              {getShortUri(p.uri)}
            </div>
            {origin && <span className="text-[10px] font-mono text-neutral-400 bg-neutral-900/50 px-1 rounded border border-neutral-700" title="Fichier source">{origin}</span>}
        </div>
        <div className="text-[11px] font-mono text-neutral-400 mt-0.5 flex flex-col gap-0.5">
           {p.type && <div><span className="text-neutral-400">type:</span> {getShortUri(p.type)}</div>}
           {p.range && (
               <div className="flex items-center gap-1">
                   <span className="text-neutral-400">range:</span> 
                   <span className="text-indigo-400">{getShortUri(p.range)}</span>
                   {getOrigin(p.range) && <span className="text-[9px] bg-neutral-900 text-neutral-400 px-1 rounded border border-neutral-700 ml-1">ref: {getOrigin(p.range)}</span>}
               </div>
           )}
           {p.label && <div className="text-neutral-400 italic mt-0.5 font-sans">"{p.label}"</div>}
           {p.comment && <div className="text-orange-400/80 italic mt-0.5 max-w-sm font-sans">{p.comment}</div>}
        </div>
      </div>
    </div>
  );
}

type AppTab = 'ontology' | 'explorer' | 'sparql' | 'export' | 'etl' | 'shacl' | 'reasoner';

export default function App() {
  const nodeColorScale = useMemo(() => d3.scaleOrdinal(d3.schemeCategory10), []);
  const nodeShapeScale = useMemo(() => d3.scaleOrdinal(d3.symbols), []);
  const linkColorScale = useMemo(() => d3.scaleOrdinal(d3.schemeSet2), []);

  const [architecture, setArchitecture] = useState<{ 
    classes: any[]; 
    properties: any[]; 
    imports: any[]; 
    individuals: any[]; 
    individualLinks: any[];
  } | null>(null);
  const [triples, setTriples] = useState<any[]>([]);
  const [sparqlQuery, setSparqlQuery] = useState(
`# Exemples de requêtes SPARQL:

# 1. Lister toutes les classes
PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT ?class
WHERE {
  ?class a owl:Class .
}
LIMIT 10

# 2. Lister toutes les instances
# SELECT ?ind ?type WHERE { ?ind a ?type . FILTER(?type != owl:Class) }

# 3. Trouver les relations entre deux entités
# SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 50`
  );
  const [sparqlResults, setSparqlResults] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<AppTab>('ontology');
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const fetchData = useCallback(() => {
    fetch(apiUrl('/api/ontology/architecture'))
      .then(res => {
        if (!res.ok) throw new Error(`Architecture fetch failed: ${res.status}`);
        return res.json();
      })
      .then(data => setArchitecture(data))
      .catch(err => console.error(err));
      
    fetch(apiUrl('/api/ontology/triples'))
      .then(res => {
        if (!res.ok) throw new Error(`Triples fetch failed: ${res.status}`);
        return res.json();
      })
      .then(data => {
        if (data && data.triples) {
          setTriples(data.triples);
        } else {
          setTriples([]);
          console.error("No triples in response:", data);
        }
      })
      .catch(err => console.error(err));
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const runSparql = async () => {
    setLoading(true);
    try {
      const res = await fetch(apiUrl('/api/sparql'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/sparql-query',
        },
        body: sparqlQuery
      });
      const data = await res.json();
      setSparqlResults(data);
    } catch (e: any) {
      setSparqlResults({ error: e.message });
    }
    setLoading(false);
  };

  const getShortUri = useCallback((uri: string) => {
    if (!uri) return '';
    if (uri.startsWith('_:')) return `Blank Node (${uri.substring(2, 8)}...)`;
    const parts = uri.split(/[/#]/);
    return parts[parts.length - 1];
  }, []);

  const getOrigin = useCallback((uri: string) => {
    if (!uri) return null;
    const match = uri.match(/\/ontologies\/([^#]+)#/);
    if (match) {
        const parts = match[1].split('/');
        return parts[parts.length - 1];
    }
    return null;
  }, []);

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-neutral-200 font-sans selection:bg-neutral-800">
      <header className="sticky top-0 z-40 bg-[#0a0a0a]/80 backdrop-blur-xl border-b border-neutral-800/50">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-medium tracking-tight text-neutral-100">NSXAI</h1>
          </div>
          <div className="flex items-center gap-1 bg-transparent overflow-x-auto no-scrollbar">
             <button 
                onClick={() => setActiveTab('ontology')}
                className={`px-3 py-1.5 text-xs rounded-full flex items-center gap-2 transition-all duration-300 shrink-0 ${activeTab === 'ontology' ? 'bg-neutral-100 text-neutral-900 font-medium' : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-900/50'}`}
             >
               <Network className="w-3.5 h-3.5" /> <span className="hidden sm:inline">Ontologie</span>
             </button>
             <button 
                onClick={() => setActiveTab('explorer')}
                className={`px-3 py-1.5 text-xs rounded-full flex items-center gap-2 transition-all duration-300 shrink-0 ${activeTab === 'explorer' ? 'bg-neutral-100 text-neutral-900 font-medium' : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-900/50'}`}
             >
               <ListTree className="w-3.5 h-3.5" /> <span className="hidden sm:inline">Explorer</span>
             </button>
             <button 
                onClick={() => setActiveTab('sparql')}
                className={`px-3 py-1.5 text-xs rounded-full flex items-center gap-2 transition-all duration-300 shrink-0 ${activeTab === 'sparql' ? 'bg-neutral-100 text-neutral-900 font-medium' : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-900/50'}`}
             >
               <Search className="w-3.5 h-3.5" /> <span className="hidden sm:inline">SPARQL</span>
             </button>
             <button 
                onClick={() => setActiveTab('etl')}
                className={`px-3 py-1.5 text-xs rounded-full flex items-center gap-2 transition-all duration-300 shrink-0 ${activeTab === 'etl' ? 'bg-neutral-100 text-neutral-900 font-medium' : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-900/50'}`}
             >
               <Layers className="w-3.5 h-3.5" /> <span className="hidden sm:inline">ETL</span>
             </button>
             <button 
                onClick={() => setActiveTab('shacl')}
                className={`px-3 py-1.5 text-xs rounded-full flex items-center gap-2 transition-all duration-300 shrink-0 ${activeTab === 'shacl' ? 'bg-neutral-100 text-neutral-900 font-medium' : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-900/50'}`}
             >
                <Shield className="w-3.5 h-3.5" /> <span className="hidden sm:inline">SHACL</span>
             </button>
             <button 
                onClick={() => setActiveTab('reasoner')}
                className={`px-3 py-1.5 text-xs rounded-full flex items-center gap-2 transition-all duration-300 shrink-0 ${activeTab === 'reasoner' ? 'bg-neutral-100 text-neutral-900 font-medium' : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-900/50'}`}
             >
                <BrainCircuit className="w-3.5 h-3.5" /> <span className="hidden sm:inline">Inference</span>
             </button>
             <button 
                onClick={() => setActiveTab('export')}
                className={`px-3 py-1.5 text-xs rounded-full flex items-center gap-2 transition-all duration-300 shrink-0 ${activeTab === 'export' ? 'bg-neutral-100 text-neutral-900 font-medium' : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-900/50'}`}
             >
               <PlugZap className="w-3.5 h-3.5" /> <span className="hidden sm:inline">Export</span>
             </button>
          </div>
        </div>
      </header>

      <div className={`${activeTab === 'ontology' || activeTab === 'explorer' || activeTab === 'shacl' || activeTab === 'reasoner' ? 'w-full px-0' : 'max-w-6xl mx-auto p-4 md:p-8'}`}>
        
        {activeTab === 'etl' && (
           <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
               <PipelineStudio />
           </div>
        )}

        {activeTab === 'shacl' && (
           <div className="animate-in fade-in slide-in-from-bottom-2 duration-300 h-[calc(100vh-140px)]">
               <ShaclManager />
           </div>
        )}

        {activeTab === 'reasoner' && (
           <div className="animate-in fade-in slide-in-from-bottom-2 duration-300 h-[calc(100vh-140px)]">
               <RuleManager />
           </div>
        )}

        {activeTab === 'export' && (
           <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
               {architecture ? (
                   <ExportStudio />
               ) : (
                   <div className="text-neutral-400">Chargement...</div>
               )}
           </div>
        )}

        {activeTab === 'sparql' && (
           <div className="animate-in fade-in duration-500 py-4 space-y-12">
              <section className="space-y-4">
                <div className="flex items-center gap-3">
                  <Server className="w-6 h-6 text-neutral-500" />
                  <h2 className="text-2xl font-medium tracking-tight text-neutral-100">Requête SPARQL</h2>
                </div>
                <p className="text-neutral-400 leading-relaxed max-w-3xl">
                  Interrogez le triplestore Fuseki via l&apos;API. Explorez librement le modèle de données.
                </p>
              </section>

              <div className="space-y-6">
                <div className="flex flex-wrap gap-2">
                  {/* Presets */}
                  {[
                    { name: "Classes", q: "PREFIX owl: <http://www.w3.org/2002/07/owl#>\nSELECT ?class WHERE {\n  ?class a owl:Class .\n} LIMIT 50" },
                    { name: "Instances", q: "PREFIX owl: <http://www.w3.org/2002/07/owl#>\nPREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nSELECT ?ind ?type WHERE { \n  ?ind a ?type . \n  FILTER(?type != owl:Class && ?type != owl:ObjectProperty && ?type != owl:DatatypeProperty) \n} LIMIT 50" },
                    { name: "Relations", q: "SELECT ?s ?p ?o WHERE { \n  ?s ?p ?o .\n} LIMIT 100" },
                    { name: "Propriétés", q: "PREFIX owl: <http://www.w3.org/2002/07/owl#>\nPREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nSELECT ?prop ?type WHERE { \n  ?prop rdf:type ?type . \n  FILTER(?type IN (owl:ObjectProperty, owl:DatatypeProperty, owl:AnnotationProperty)) \n} LIMIT 50" },
                    { name: "Labels/Commentaires", q: "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nSELECT ?subject ?label ?comment WHERE { \n  OPTIONAL { ?subject rdfs:label ?label } . \n  OPTIONAL { ?subject rdfs:comment ?comment } . \n  FILTER(bound(?label) || bound(?comment)) \n} LIMIT 50" },
                    { name: "Méta-données & Imports", q: "PREFIX owl: <http://www.w3.org/2002/07/owl#>\nSELECT ?ontology ?imported WHERE { \n  ?ontology owl:imports ?imported .\n} LIMIT 10" },
                    { name: "Domaines & Ranges", q: "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nSELECT ?property ?domain ?range WHERE {\n  OPTIONAL { ?property rdfs:domain ?domain } .\n  OPTIONAL { ?property rdfs:range ?range } .\n  FILTER (bound(?domain) || bound(?range))\n} LIMIT 50" },
                    { name: "Hiérarchie de Classes", q: "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nSELECT ?subClass ?superClass WHERE {\n  ?subClass rdfs:subClassOf ?superClass .\n} LIMIT 100" },
                    { name: "Classes Orphelines", q: "PREFIX owl: <http://www.w3.org/2002/07/owl#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nSELECT ?class WHERE { \n  ?class a owl:Class . \n  FILTER NOT EXISTS { ?class rdfs:subClassOf ?super } \n} LIMIT 50" },
                    { name: "Propriétés par Instance", q: "SELECT ?instance ?prop ?val WHERE { \n  ?instance ?prop ?val . \n  FILTER isIRI(?instance) \n  FILTER (!STRSTARTS(STR(?prop), \"http://www.w3.org\")) \n} LIMIT 100" },
                    { name: "Littéraux", q: "SELECT ?s ?p ?value WHERE { \n  ?s ?p ?value .\n  FILTER(isLiteral(?value))\n} LIMIT 50" },
                    { name: "Compter les Types", q: "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nSELECT ?type (COUNT(?instance) AS ?count) WHERE { \n  ?instance rdf:type ?type .\n} GROUP BY ?type ORDER BY DESC(?count) LIMIT 20" },
                    { name: "Compter les Propriétés", q: "SELECT ?p (COUNT(?s) AS ?count) WHERE { \n  ?s ?p ?o .\n} GROUP BY ?p ORDER BY DESC(?count) LIMIT 20" },
                    { name: "Classes sans Instance", q: "PREFIX owl: <http://www.w3.org/2002/07/owl#>\nPREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nSELECT ?class WHERE { \n  ?class a owl:Class . \n  FILTER NOT EXISTS { ?ind rdf:type ?class } \n} LIMIT 50" },
                    { name: "Concepts les plus liés", q: "SELECT ?concept (COUNT(?rel) AS ?relations) WHERE { \n  { ?concept ?rel ?o } UNION { ?s ?rel ?concept } \n  FILTER isIRI(?concept) \n} GROUP BY ?concept ORDER BY DESC(?relations) LIMIT 20" },
                    { name: "Chemins de longueur 2", q: "SELECT ?a ?p1 ?b ?p2 ?c WHERE { \n  ?a ?p1 ?b . \n  ?b ?p2 ?c . \n  FILTER isIRI(?b) \n} LIMIT 50" },
                    { name: "Propriétés Objets Uniques", q: "PREFIX owl: <http://www.w3.org/2002/07/owl#>\nSELECT DISTINCT ?p WHERE {\n  ?s ?p ?o .\n  FILTER isIRI(?o) .\n  FILTER (!STRSTARTS(STR(?p), \"http://www.w3.org\"))\n} LIMIT 50" },
                    { name: "Types de Datatypes", q: "SELECT DISTINCT ?datatype WHERE { \n  ?s ?p ?o .\n  FILTER(isLiteral(?o))\n  BIND(datatype(?o) AS ?datatype)\n  FILTER(bound(?datatype))\n} LIMIT 20" }
                  ].map((preset, i) => (
                    <button
                      key={i}
                      onClick={() => setSparqlQuery(preset.q)}
                      className="text-xs bg-transparent hover:bg-neutral-900 border text-neutral-400 hover:text-neutral-200 px-4 py-2 rounded-full border-neutral-800 transition-colors duration-200"
                    >
                       {preset.name}
                    </button>
                  ))}
                </div>
                <div className="relative">
                  <textarea 
                    value={sparqlQuery}
                    onChange={e => setSparqlQuery(e.target.value)}
                    className="w-full h-48 p-6 font-mono text-sm bg-neutral-900/30 text-neutral-300 rounded-2xl border border-neutral-800/70 focus:outline-none focus:border-neutral-600 transition-colors resize-y custom-scrollbar"
                    style={{ lineHeight: '1.6' }}
                  />
                  <button 
                    onClick={runSparql}
                    disabled={loading}
                    className="absolute bottom-4 right-4 flex items-center justify-center gap-2 bg-neutral-100 text-neutral-900 px-6 py-2.5 rounded-lg font-medium text-sm hover:bg-white transition-colors disabled:opacity-50"
                  >
                    <Play className="w-4 h-4 fill-current" />
                    {loading ? 'Exécution...' : 'Exécuter'}
                  </button>
                </div>
                
                <SparqlResultsView results={sparqlResults} />
              </div>
           </div>
        )}

         {activeTab === 'explorer' && (
           <div className="flex flex-col animate-in fade-in slide-in-from-bottom-2 duration-300 h-[calc(100vh-64px)] bg-[#0a0a0a]">
               {architecture ? (
                    <div className="flex-1 overflow-y-auto custom-scrollbar bg-[#050505] p-6 lg:p-10 border-t border-neutral-800/50">
                        <div className="max-w-6xl mx-auto space-y-6">
                            <h3 className="text-xl font-medium text-neutral-100 flex items-center gap-3">
                                <ListTree className="w-6 h-6 text-indigo-400" />
                                Explorateur Agnostique des Triplets
                            </h3>
                            <AgnosticTripleTree 
                                triples={triples} 
                                getShortUri={getShortUri} 
                                architecture={architecture} 
                                onSelectNode={(nodeId) => {
                                    setSelectedNodeId(nodeId);
                                    setActiveTab('ontology');
                                }}
                                onRefresh={fetchData}
                            />
                        </div>
                    </div>
               ) : (
                   <div className="flex items-center justify-center h-full text-neutral-400">Chargement...</div>
               )}
           </div>
        )}

        {activeTab === 'ontology' && (
           <div className="animate-in fade-in duration-500 relative h-[calc(100vh-64px)] bg-[#0a0a0a]">
              {/* Full page graph */}
              <div className="w-full h-full">
                 {triples.length > 0 ? (
                    triples.length > 5000 ? (
                        <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-6 bg-[#050505]">
                            <div className="p-8 bg-neutral-900 border border-neutral-800 rounded-[2.5rem] max-w-md space-y-6 shadow-2xl">
                                <Network className="w-12 h-12 text-neutral-500 mx-auto" />
                                <div className="space-y-2">
                                    <h3 className="text-xl font-bold text-white tracking-tight">Graphe Saturé</h3>
                                    <p className="text-sm text-neutral-400 leading-relaxed">
                                        L'ontologie contient <span className="text-white font-mono">{triples.length}</span> triplets. 
                                        Le rendu graphique est suspendu pour garantir la fluidité.
                                    </p>
                                </div>
                                <button 
                                    onClick={() => setActiveTab('explorer')}
                                    className="w-full px-6 py-3 bg-white text-neutral-900 rounded-2xl text-[10px] font-black uppercase tracking-[0.2em] hover:bg-neutral-200 transition-all active:scale-95 shadow-xl shadow-white/5"
                                >
                                    Utiliser l'Explorateur Arborescent
                                </button>
                            </div>
                        </div>
                    ) : (
                        <OntologyGraph 
                           triples={triples} 
                           getShortUri={getShortUri} 
                           nodeColorScale={nodeColorScale}
                           nodeShapeScale={nodeShapeScale}
                           linkColorScale={linkColorScale}
                           selectedNodeId={selectedNodeId}
                           setSelectedNodeId={setSelectedNodeId}
                        />
                    )
                 ) : (
                    <div className="absolute inset-0 flex items-center justify-center text-sm text-neutral-400">
                       Chargement du graphe...
                    </div>
                 )}
              </div>
           </div>
        )}

      </div>
    </div>
  );
}
