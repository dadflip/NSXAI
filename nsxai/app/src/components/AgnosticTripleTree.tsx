import React, { useState, useMemo } from 'react';
import * as d3 from 'd3';
import { ChevronRight, ChevronDown, Link as LinkIcon, Info, Plus, Sparkles, Loader2, RotateCcw, Trash2 } from 'lucide-react';
import { SmartCreateModal } from './SmartCreateModal';
import { apiUrl } from '../lib/api';

interface Triple {
  subject: string;
  predicate: string;
  object: string;
  objectType: string;
  datatype?: string;
}

interface AgnosticTripleTreeProps {
  triples: Triple[];
  getShortUri: (uri: string) => string;
  architecture?: any;
  onSelectNode: (id: string) => void;
  onRefresh?: () => void;
}

const TYPE_PREDICATE = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type';
const LABEL_PREDICATE = 'http://www.w3.org/2000/01/rdf-schema#label';
const SUBCLASS_PREDICATE = 'http://www.w3.org/2000/01/rdf-schema#subClassOf';

export function AgnosticTripleTree({ 
  triples, 
  getShortUri, 
  architecture,
  onSelectNode,
  onRefresh
}: AgnosticTripleTreeProps) {
  const [maxDepth, setMaxDepth] = useState<number>(5); 
  const [inferences, setInferences] = useState<Set<string>>(new Set());
  const [populationCount, setPopulationCount] = useState<number>(100);
  const [isResetting, setIsResetting] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [validationReport, setValidationReport] = useState<{ conforms: boolean, results: any[] } | null>(null);

  const handleValidate = async () => {
    setIsValidating(true);
    setValidationReport(null);
    try {
        const res = await fetch(apiUrl('/api/ontology/validate'), { method: 'POST' });
        if (res.ok) {
            const report = await res.json();
            setValidationReport(report);
            if (!report.conforms) {
                setPopulateStatus({ type: 'error', message: `${report.results.length} violations SHACL trouvées.` });
            } else {
                setPopulateStatus({ type: 'success', message: `Graphe conforme aux contraintes SHACL.` });
                setTimeout(() => setPopulateStatus(null), 3000);
            }
        }
    } catch (e: any) {
        console.error(e);
        setPopulateStatus({ type: 'error', message: "Erreur validation: " + e.message });
    } finally {
        setIsValidating(false);
    }
  };

  const [createModalState, setCreateModalState] = useState<{ isOpen: boolean, type: 'class' | 'individual' | 'property' | 'unknown' }>({
      isOpen: false,
      type: 'unknown'
  });

  const fetchInferences = () => {
    fetch(apiUrl('/api/reasoner/inferences'))
      .then(r => {
        if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`);
        return r.json();
      })
      .then(d => setInferences(new Set(d)))
      .catch(err => console.error("Error fetching inferences:", err));
  };

  const [isPopulating, setIsPopulating] = useState(false);
  const [populateStatus, setPopulateStatus] = useState<{ type: 'success' | 'error', message: string } | null>(null);

  const handlePopulate = async () => {
    setIsPopulating(true);
    setPopulateStatus(null);
    try {
        const res = await fetch(apiUrl('/api/ontology/populate'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ count: populationCount })
        });
        if (res.ok) {
            const data = await res.json();
            if (onRefresh) onRefresh();
            setPopulateStatus({ type: 'success', message: `${data.count || populationCount} individus créés.` });
            setTimeout(() => setPopulateStatus(null), 3000);
        } else {
            const error = await res.json();
            setPopulateStatus({ type: 'error', message: "Erreur: " + (error.error || res.statusText) });
        }
    } catch (e: any) {
        console.error(e);
        setPopulateStatus({ type: 'error', message: "Erreur réseau: " + e.message });
    } finally {
        setIsPopulating(false);
    }
  };

  const handleReset = async () => {
    if (!confirmReset) {
      setConfirmReset(true);
      setTimeout(() => setConfirmReset(false), 3000);
      return;
    }
    
    setIsResetting(true);
    setConfirmReset(false);
    setPopulateStatus({ type: 'success', message: "Réinitialisation en cours..." });
    
    try {
        const res = await fetch(apiUrl('/api/ontology/reset'), { method: 'POST' });
        if (res.ok) {
            // Re-sync SHACL shapes from local storage
            const savedShapes = localStorage.getItem('nsxai_shacl_shapes');
            if (savedShapes) {
              try {
                const shapes = JSON.parse(savedShapes);
                const triples = shapes.flatMap((s: any) => [
                  { s: s.uri, p: 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type', o: 'http://www.w3.org/ns/shacl#NodeShape', isLiteral: false },
                  { s: s.uri, p: 'http://www.w3.org/ns/shacl#targetClass', o: s.targetClass, isLiteral: false },
                  ...(s.label ? [{ s: s.uri, p: 'http://www.w3.org/2000/01/rdf-schema#label', o: s.label, isLiteral: true }] : [])
                ]);
                await fetch(apiUrl('/api/ontology/triples'), {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ triples })
                });
              } catch (e) {
                console.error("Failed to re-sync shacl shapes after reset:", e);
              }
            }

            // Sync Rules
            const savedRules = localStorage.getItem('nsxai_reasoner_rules');
            if (savedRules) {
              try {
                await fetch(apiUrl('/api/reasoner/rules/sync'), {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ rules: JSON.parse(savedRules) })
                });
              } catch (e) {
                console.error("Failed to sync rules after reset:", e);
              }
            }

            if (onRefresh) onRefresh();
            setPopulateStatus({ type: 'success', message: `Base réinitialisée.` });
            setTimeout(() => setPopulateStatus(null), 5000);
        } else {
            const err = await res.json();
            setPopulateStatus({ type: 'error', message: "Erreur: " + (err.error || res.statusText) });
        }
    } catch (e: any) {
        console.error("Reset error:", e);
        setPopulateStatus({ type: 'error', message: "Erreur réseau: " + e.message });
    } finally {
        setIsResetting(false);
    }
  };

  React.useEffect(() => {
    fetchInferences();
  }, [architecture]);

  // Group triples by subject
  const subjectsMap = useMemo(() => {
    const map = new Map<string, Triple[]>();
    triples.forEach(t => {
      if (!map.has(t.subject)) {
        map.set(t.subject, []);
      }
      map.get(t.subject)!.push(t);
    });
    return map;
  }, [triples]);

  // Infer node types based on the exact same architecture as the header
  const nodeTypes = useMemo(() => {
      const types = new Map<string, string>();
      
      if (architecture) {
          architecture.classes.forEach((c: any) => types.set(c.uri, 'class'));
          architecture.properties.forEach((p: any) => types.set(p.uri, 'property'));
          architecture.individuals.forEach((i: any) => types.set(i.uri, 'individual'));
      }
      
      triples.forEach(t => {
          if (!types.has(t.subject)) types.set(t.subject, 'unknown');
          if (t.objectType !== 'Literal' && !types.has(t.object)) types.set(t.object, 'unknown');
      });
      return types;
  }, [triples, architecture]);

  // Group all subjects by their inferred type
  const { groupedSubjects, allNodeGroups } = useMemo(() => {
      const groups: Record<string, string[]> = {};
      const allGroups = new Set<string>();
      
      Array.from<string>(subjectsMap.keys()).forEach(s => {
          const t = nodeTypes.get(s) || 'Inconnu';
          if (!groups[t]) groups[t] = [];
          groups[t].push(s);
          allGroups.add(t);
      });

      // Sort alphabetically within each group
      Object.keys(groups).forEach(k => {
          groups[k].sort((a, b) => getShortUri(a).localeCompare(getShortUri(b)));
      });

      return { groupedSubjects: groups, allNodeGroups: allGroups };
  }, [subjectsMap, nodeTypes, getShortUri]);

  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

  const toggleGroup = (key: string) => {
      setExpandedGroups(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const openCreateModal = (e: React.MouseEvent, type: any) => {
      e.stopPropagation();
      setCreateModalState({ isOpen: true, type });
  };

  return (
    <div className="flex flex-col gap-4 text-sm font-mono pb-20">
        <SmartCreateModal 
          isOpen={createModalState.isOpen}
          type={createModalState.type}
          architecture={architecture}
          onClose={() => setCreateModalState(prev => ({ ...prev, isOpen: false }))}
          onSuccess={() => {
              if (onRefresh) onRefresh();
              fetchInferences();
          }}
        />
        <div className="text-xs text-neutral-400 bg-[#070707] p-4 border border-neutral-800/50 rounded-xl flex items-start gap-4 shadow-inner">
           <Info className="w-4 h-4 text-neutral-600 flex-shrink-0 mt-0.5" />
           <div className="flex flex-col gap-3 flex-1">
               <p className="leading-relaxed text-neutral-400">
                  Arborescence unifiée du Graphe de Connaissances. Tous les titres sont cliquables pour naviguer vers le graphe.
                  <span className="ml-2 px-1.5 py-0.5 bg-emerald-900/10 border border-emerald-500/20 text-emerald-400/80 rounded inline-flex items-center gap-1 shrink-0 text-[10px] font-bold tracking-tight uppercase">
                      Inféré
                  </span>
               </p>
               
               <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-3 p-3 bg-neutral-900/30 rounded-lg border border-neutral-800/30">
                    <div className="flex flex-wrap items-center gap-x-8 gap-y-2">
                        {['class', 'individual', 'property'].map((group: any) => (
                           <div key={group} className="flex items-center gap-2 group cursor-pointer" onClick={(e) => openCreateModal(e, group)}>
                               <span className="text-neutral-300 font-mono text-[11px] font-medium tracking-wider uppercase">{group}</span>
                               <Plus className="w-3 h-3 text-neutral-600 group-hover:text-neutral-200 transition-colors" />
                           </div>
                        ))}
                    </div>
                    <div className="flex items-center gap-4">
                        {populateStatus && (
                            <span className={`text-[10px] font-bold uppercase tracking-widest ${populateStatus.type === 'success' ? 'text-emerald-500' : 'text-red-500'} animate-pulse`}>
                                {populateStatus.message}
                            </span>
                        )}
                        
                        <div className="flex items-center bg-neutral-950 border border-neutral-800 rounded-lg p-1 gap-1">
                            <span className="text-[9px] text-neutral-500 font-mono px-2 uppercase tracking-tighter">Pas:</span>
                            <select 
                                value={populationCount}
                                onChange={(e) => setPopulationCount(parseInt(e.target.value))}
                                className="bg-neutral-900 text-neutral-300 text-[10px] font-bold px-2 py-0.5 rounded border-none focus:ring-0 cursor-pointer"
                            >
                                {[50, 100, 200, 300, 400, 500].map(v => (
                                    <option key={v} value={v}>{v}</option>
                                ))}
                            </select>
                        </div>

                        <div className="flex items-center gap-2">
                            <button 
                                onClick={handlePopulate}
                                disabled={isPopulating}
                                className="flex items-center gap-2 px-3 py-1.5 bg-white text-neutral-900 border border-transparent hover:bg-neutral-200 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all active:scale-95 group"
                            >
                                {isPopulating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3 group-hover:animate-pulse" />}
                                {isPopulating ? 'Traitement...' : 'Peuplement Auto'}
                            </button>
                            
                            <button 
                                onClick={handleReset}
                                disabled={isResetting}
                                title="Réinitialiser le Graphe"
                                className={`flex items-center gap-2 p-1.5 border rounded-lg transition-all active:scale-90 ${confirmReset ? 'bg-red-500/20 border-red-500/50 text-red-500 hover:bg-red-500/30' : 'bg-neutral-950 border-neutral-800 hover:border-red-900/50 hover:bg-red-950/10 text-neutral-500 hover:text-red-400'}`}
                            >
                                {isResetting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : (confirmReset ? <span className="text-[10px] font-bold px-1 whitespace-nowrap">CONFIRMER ?</span> : <RotateCcw className="w-3.5 h-3.5" />)}
                            </button>

                            <button 
                                onClick={handleValidate}
                                disabled={isValidating}
                                title="Valider SHACL"
                                className={`flex items-center gap-2 px-3 py-1.5 border rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all active:scale-95 ${
                                    validationReport && !validationReport.conforms 
                                    ? 'bg-red-900/20 border-red-500/50 text-red-400 hover:bg-red-900/30' 
                                    : 'bg-neutral-950 border-neutral-800 text-neutral-400 hover:border-neutral-700 hover:bg-neutral-900'
                                }`}
                            >
                                {isValidating ? <Loader2 className="w-3 h-3 animate-spin" /> : <span className="w-3 h-3 flex items-center justify-center">✓</span>}
                                {isValidating ? 'Validation...' : 'SHACL'}
                            </button>
                        </div>
                    </div>
               </div>
               {validationReport && !validationReport.conforms && (
                   <div className="bg-red-950/10 border border-red-900/30 rounded-lg p-3 space-y-2">
                       <div className="flex items-center justify-between">
                           <h4 className="text-[10px] font-bold text-red-500 uppercase tracking-widest flex items-center gap-2">
                               <Info className="w-3 h-3" />
                               Violations de Contraintes ({validationReport.results.length})
                           </h4>
                           <button onClick={() => setValidationReport(null)} className="text-[9px] text-red-700 hover:text-red-500 uppercase font-bold">Masquer</button>
                       </div>
                       <div className="max-h-40 overflow-y-auto space-y-1 pr-2 custom-scrollbar">
                           {validationReport.results.map((res: any, idx: number) => (
                               <div key={idx} className="text-[11px] p-2 bg-red-950/20 rounded border border-red-900/20 flex flex-col gap-1">
                                   <div className="flex items-center gap-2">
                                       <span className="text-red-400 font-bold truncate flex-1" title={res.focusNode}>{getShortUri(res.focusNode)}</span>
                                       <span className="text-[9px] px-1 bg-red-900/40 rounded text-red-300">{res.severity}</span>
                                   </div>
                                   <div className="text-neutral-400 leading-tight">
                                       {res.message}
                                   </div>
                                   {res.path && (
                                       <div className="text-[9px] text-neutral-500 italic truncate">
                                           Path: {getShortUri(res.path)}
                                       </div>
                                   )}
                               </div>
                           ))}
                       </div>
                   </div>
               )}
           </div>
      </div>

       {Object.keys(groupedSubjects).sort().map(groupKey => {
           const count = groupedSubjects[groupKey].length;
           if (count === 0) return null;
           const isExpanded = expandedGroups[groupKey];

           return (
             <div key={groupKey} className="bg-transparent border border-neutral-800/70 rounded-xl overflow-hidden">
                <div 
                   className="px-4 py-3 bg-neutral-900/40 border-b border-neutral-800/70 font-medium text-neutral-200 flex items-center justify-between cursor-pointer hover:bg-neutral-900/60 transition-colors"
                   onClick={() => toggleGroup(groupKey)}
                >
                   <div className="flex items-center gap-2">
                       {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                       <span className="uppercase tracking-widest text-[11px] opacity-80">{groupKey}</span>
                       {(groupKey === 'class' || groupKey === 'individual' || groupKey === 'property') && (
                           <button 
                               onClick={(e) => openCreateModal(e, groupKey)}
                               className="ml-2 p-1 hover:bg-neutral-800 rounded text-neutral-400 opacity-0 group-hover:opacity-100 transition-all active:scale-90"
                           >
                               <Plus className="w-3 h-3" />
                           </button>
                       )}
                   </div>
                   <div className="text-xs text-neutral-500 bg-neutral-950 px-2 py-0.5 rounded-full">{count}</div>
                </div>
                {isExpanded && (
                   <div className="p-2 space-y-1 bg-neutral-950/50">
                     {groupedSubjects[groupKey].map(sub => (
                       <SubjectNode 
                          key={sub} 
                          subject={sub} 
                          subjectsMap={subjectsMap} 
                          getShortUri={getShortUri} 
                          level={0}
                          maxDepth={maxDepth}
                          nodeTypes={nodeTypes}
                          
                          inferences={inferences}
                          onSelectNode={onSelectNode}
                       />
                     ))}
                   </div>
                )}
             </div>
           );
       })}
    </div>
  );
}

function SubjectNode({ 
  subject, 
  subjectsMap, 
  getShortUri, 
  level,
  maxDepth,
  nodeTypes,
  isObjectOpen = false,
  inferences,
  onSelectNode
}: { 
  key?: React.Key,
  subject: string, 
  subjectsMap: Map<string, Triple[]>, 
  getShortUri: (uri: string) => string, 
  level: number,
  maxDepth: number,
  nodeTypes: Map<string, string>,
  isObjectOpen?: boolean,
  inferences: Set<string>,
  onSelectNode: (id: string) => void
}) {
  const [isOpen, setIsOpen] = useState(isObjectOpen);
  
  const properties = subjectsMap.get(subject) || [];
  
  // Try to find a label or type for display purposes
  const labelObj = properties.find(t => t.predicate === LABEL_PREDICATE);
  const typeObj = properties.find(t => t.predicate === TYPE_PREDICATE);
  
  const displayLabel = labelObj ? labelObj.object : getShortUri(subject);
  const nodeType = nodeTypes.get(subject) || 'unknown';

  // Group properties by predicate
  const groupedProps = useMemo(() => {
     const map = new Map<string, Triple[]>();
     properties.forEach(t => {
        if (!map.has(t.predicate)) map.set(t.predicate, []);
        map.get(t.predicate)!.push(t);
     });
     return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [properties]);

  return (
    <div className="flex flex-col w-full text-[12px] md:text-[13px]">
       <div 
         className="flex items-start gap-2 py-1.5 px-2 hover:bg-neutral-800/30 rounded select-none group transition-colors"
       >
          <div 
            className="mt-0.5 text-neutral-500 group-hover:text-neutral-300 shrink-0 cursor-pointer p-1"
            onClick={(e) => {
                e.stopPropagation();
                setIsOpen(!isOpen);
            }}
          >
             {isOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          </div>
          <div 
            className="flex flex-col flex-1 min-w-0"
            onClick={() => onSelectNode(subject)}
          >
             <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-neutral-200 truncate group-hover:text-white transition-colors">{displayLabel}</span>
                {typeObj && (
                    <span 
                        className="px-1.5 py-0.5 rounded text-[10px] bg-neutral-800/50 text-neutral-400 border border-neutral-700/50 truncate max-w-[200px] hover:bg-neutral-700/50 hover:text-neutral-200 transition-colors"
                        onClick={(e) => {
                            e.stopPropagation();
                            onSelectNode(typeObj.object);
                        }}
                    >
                        {getShortUri(typeObj.object)}
                    </span>
                )}
             </div>
             {isOpen && labelObj && subject !== displayLabel && <div className="text-[10px] text-neutral-500 mt-0.5 truncate">{subject}</div>}
             {!isOpen && !labelObj && <div className="text-[10px] text-neutral-500 mt-0.5 truncate">{subject}</div>}
          </div>
          <div className="text-[10px] text-neutral-600 font-sans mt-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
             {properties.length} triples
          </div>
       </div>

       {isOpen && (
          <div className="ml-5 pl-4 border-l border-neutral-800/50 my-1 space-y-1">
             {groupedProps.length === 0 && (
                <div className="text-neutral-500 italic py-1 px-2 text-[11px]">Aucune propriété</div>
             )}
             {groupedProps.map(([predicate, entries]) => (
                <div key={predicate} className="flex flex-col mt-2 first:mt-0">
                   <div 
                    className="py-1 px-2 text-[11px] text-neutral-400 flex items-center gap-1.5 break-all leading-tight max-w-[90%] font-medium cursor-pointer hover:text-neutral-200 transition-colors px-1"
                    onClick={() => onSelectNode(predicate)}
                   >
                      <LinkIcon className="w-3 h-3 text-neutral-500/50 flex-shrink-0" />
                      {getShortUri(predicate)}
                   </div>
                   <div className="space-y-1 ml-4 border-l border-neutral-800/30 pl-2 mt-1 relative">
                      {entries.map((t, idx) => (
                         <ObjectNode 
                           key={idx} 
                           triple={t} 
                           subjectsMap={subjectsMap} 
                           getShortUri={getShortUri} 
                           level={level + 1} 
                           maxDepth={maxDepth}
                           nodeTypes={nodeTypes}
                           inferences={inferences}
                           onSelectNode={onSelectNode}
                         />
                      ))}
                   </div>
                </div>
             ))}
          </div>
       )}
    </div>
  );
};

function ObjectNode({ 
  triple, 
  subjectsMap, 
  getShortUri, 
  level,
  maxDepth,
  nodeTypes,
  inferences,
  onSelectNode
}: { 
  key?: React.Key,
  triple: Triple, 
  subjectsMap: Map<string, Triple[]>, 
  getShortUri: (uri: string) => string, 
  level: number,
  maxDepth: number,
  nodeTypes: Map<string, string>,
  inferences?: Set<string>,
  onSelectNode: (id: string) => void
}) {
   // Limit recursion depth to avoid infinite loops and performance issues
   const MAX_DEPTH = maxDepth;

   let oStr = triple.object;
   if (triple.objectType === 'Literal') {
      if (triple.datatype && triple.datatype !== 'http://www.w3.org/2001/XMLSchema#string') {
          oStr = `"${triple.object}"^^<${triple.datatype}>`;
      } else {
          oStr = `"${triple.object}"`;
      }
   }
   const isInferred = inferences?.has(`${triple.subject}|${triple.predicate}|${oStr}`) || inferences?.has(`${triple.subject}|${triple.predicate}|${triple.object}`);


   if (triple.objectType === 'Literal') {
      return (
         <div className="py-1.5 px-2 flex items-start gap-2 text-neutral-400 relative group border-l border-neutral-800/20 ml-2">
            <div className="break-all whitespace-pre-wrap leading-tight text-[11.5px]">
               "{triple.object}"
               {triple.datatype && <span className="text-[9px] text-neutral-500 ml-2 bg-neutral-900 border border-neutral-800 px-1 py-0.5 rounded inline-block">_{triple.datatype.split(/[/#]/).pop()}</span>}
               {isInferred && <span className="text-[9px] ml-2 px-1.5 py-0.5 bg-emerald-900/10 border border-emerald-500/20 text-emerald-400 rounded inline-flex items-center gap-1 shrink-0 font-bold">Inféré</span>}
            </div>
         </div>
      );
   }

   const objectHasProperties = subjectsMap.has(triple.object);

   if (objectHasProperties && level < MAX_DEPTH) {
      return (
         <div className="relative">
            {isInferred && (
                <div className="absolute top-1.5 right-2 z-10 text-[9px] px-1.5 py-0.5 bg-emerald-900/10 border border-emerald-500/20 text-emerald-400 rounded flex items-center gap-1 shrink-0 font-bold">
                    Inféré
                </div>
            )}
            <SubjectNode 
               subject={triple.object} 
               subjectsMap={subjectsMap} 
               getShortUri={getShortUri} 
               level={level}
               maxDepth={maxDepth}
               nodeTypes={nodeTypes}
               inferences={inferences || new Set()}
               onSelectNode={onSelectNode}
            />
         </div>
      );
   }

   // Fallback for URIs that we can't or won't expand further
   const objType = nodeTypes.get(triple.object) || 'unknown';
   
   return (
      <div className="py-1 px-3 flex items-center gap-2 text-neutral-300 border border-transparent hover:bg-neutral-800/40 rounded-md transition-all group relative cursor-pointer active:scale-[0.98] ml-2" onClick={() => onSelectNode(triple.object)}>
         <div className="truncate group-hover:text-white group-hover:underline transition-colors" title={triple.object}>
            {getShortUri(triple.object)}
         </div>
         {objectHasProperties && level >= MAX_DEPTH && <span className="text-[9px] text-neutral-500 ml-2 border border-neutral-800 px-1 py-0.5 rounded">...</span>}
         {isInferred && <span className="ml-2 text-[9px] px-1.5 py-0.5 bg-emerald-900/10 border border-emerald-500/20 text-emerald-400 rounded flex items-center gap-1 shrink-0 font-bold">Inféré</span>}
      </div>
   );
}
