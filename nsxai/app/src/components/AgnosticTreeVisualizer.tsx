import React, { useEffect, useState, useMemo } from 'react';
import { Network, Database, ChevronRight, ChevronDown, Activity, Sparkles, User, Key, Layers, Search, Code, Link, Download, Info, Waypoints } from 'lucide-react';
import { apiUrl } from '../lib/api';

interface OntologyArchitecture {
  classes: any[];
  properties: any[];
  imports: any[];
  individuals: any[];
  individualLinks: any[];
}

interface AgnosticTreeVisualizerProps {
  architecture: OntologyArchitecture;
}

export const AgnosticTreeVisualizer: React.FC<AgnosticTreeVisualizerProps> = ({ architecture }) => {
  const [inferences, setInferences] = useState<Set<string>>(new Set());
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<'hierarchy' | 'domain-range'>('hierarchy');

  useEffect(() => {
    fetch(apiUrl('/api/reasoner/inferences'))
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const ct = r.headers.get("content-type");
        if (ct && ct.includes("application/json")) return r.json();
        return [];
      })
      .then(d => setInferences(new Set(d)))
      .catch(err => console.error("Error fetching inferences in tree visualizer:", err));
  }, [architecture]);

  const toggleNode = (id: string, forceExpand?: boolean) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (forceExpand) next.add(id);
      else if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const shortName = (uri: string) => uri ? uri.split('#').pop()?.split('/').pop() : 'Unknown';

  // Build class hierarchy
  const hierarchyRoots = useMemo(() => {
    const clsMap = new Map<string, any>();
    architecture.classes.forEach(c => clsMap.set(c.uri, { ...c, children: [], individuals: [], propertiesDomain: [], propertiesRange: [] }));

    const rootClasses: string[] = [];
    architecture.classes.forEach(c => {
      let isRoot = true;
      if (c.subClassOfs && c.subClassOfs.length > 0) {
        c.subClassOfs.forEach((parentUri: string) => {
          if (clsMap.has(parentUri)) {
            clsMap.get(parentUri).children.push(clsMap.get(c.uri));
            isRoot = false;
          }
        });
      }
      if (isRoot) rootClasses.push(c.uri);
    });

    architecture.individuals.forEach(ind => {
      if (clsMap.has(ind.type)) {
        clsMap.get(ind.type).individuals.push(ind);
      }
    });

    architecture.properties.forEach(prop => {
      const domains = prop.domains || (prop.domain ? [prop.domain] : []);
      const ranges = prop.ranges || (prop.range ? [prop.range] : []);
      
      const addedToDomain = new Set<string>();
      domains.forEach((domainUri: string) => {
        if (clsMap.has(domainUri) && !addedToDomain.has(domainUri)) {
          addedToDomain.add(domainUri);
          clsMap.get(domainUri).propertiesDomain.push({
             ...prop,
             domain: domainUri, 
             range: ranges[0] || prop.range
          });
        }
      });
    });

    return rootClasses.map(uri => clsMap.get(uri));
  }, [architecture]);

  // Build domain-range relationship roots
  const domainRangeRoots = useMemo(() => {
    const clsMap = new Map<string, any>();
    architecture.classes.forEach(c => clsMap.set(c.uri, { ...c, individuals: [], propertiesDomain: [] }));

    architecture.individuals.forEach(ind => {
      if (clsMap.has(ind.type)) {
        clsMap.get(ind.type).individuals.push(ind);
      }
    });

    const isRangeOf = new Set<string>();

    architecture.properties.forEach(prop => {
      const domains = prop.domains || (prop.domain ? [prop.domain] : []);
      const ranges = prop.ranges || (prop.range ? [prop.range] : []);
      
      ranges.forEach((r: string) => isRangeOf.add(r));

      domains.forEach((domainUri: string) => {
        if (clsMap.has(domainUri)) {
            // Find if already pushed to avoid dupes if domains array has it
            const existing = clsMap.get(domainUri).propertiesDomain.find((p: any) => p.uri === prop.uri);
            if (!existing) {
                clsMap.get(domainUri).propertiesDomain.push({
                    ...prop,
                    domain: domainUri,
                    ranges: ranges
                });
            }
        }
      });
    });

    const roots: string[] = [];
    architecture.classes.forEach(c => {
        if (!isRangeOf.has(c.uri)) roots.push(c.uri);
    });
    
    // If all classes are in a cycle or lack any properties, fallback to all as roots.
    if (roots.length === 0) {
        return architecture.classes.map(c => clsMap.get(c.uri));
    }

    return roots.map(uri => clsMap.get(uri)).filter(Boolean);
  }, [architecture]);

  const isTripleInferred = (s: string, p: string, o: string) => inferences.has(`${s}|${p}|${o}`);

  const checkInferenceReason = (ind: any, classUri: string) => {
     // Explicitly look why an individual 'ind' is of type 'classUri'
     // 1. Through rdfs:domain
     for (const p of architecture.properties) {
        const domains = p.domains || (p.domain ? [p.domain] : []);
        if (domains.includes(classUri)) {
           // Does ind have this property going out?
           const hasOut = architecture.individualLinks.some(l => l.s === ind.uri && l.p === p.uri);
           if (hasOut) return `Inféré car il possède la propriété sortante "${shortName(p.uri)}" (domaine: ${shortName(classUri)})`;
        }
     }
     // 2. Through rdfs:range
     for (const p of architecture.properties) {
        const ranges = p.ranges || (p.range ? [p.range] : []);
        if (ranges.includes(classUri)) {
           // Is ind the object of this property?
           const hasIn = architecture.individualLinks.some(l => l.o === ind.uri && l.p === p.uri);
           if (hasIn) return `Inféré car il est la cible de la propriété "${shortName(p.uri)}" (range: ${shortName(classUri)})`;
        }
     }
     // 3. Through rdfs:subClassOf
     const explicitType = ind.type;
     if (explicitType !== classUri) {
         // See if explicitType is subClassOf classUri
         let curr = architecture.classes.find(c => c.uri === explicitType);
         while(curr) {
             if (curr.subClassOfs && curr.subClassOfs.includes(classUri)) {
                 return `Inféré par transitivité (la classe ${shortName(explicitType)} est une sous-classe de ${shortName(classUri)})`;
             }
             // For simplicity, just check direct subClassOf for the reason string (deep search might be longer, but usually sufficient)
             curr = architecture.classes.find(c => c.uri === (curr.subClassOfs && curr.subClassOfs[0]));
         }
         return `Inféré par transitivité depuis sa classe parente ${shortName(explicitType)}`;
     }
     
     return "Inféré automatiquement (règle experte)";
  };

  const renderAssertions = (ind: any) => {
    const assertions = architecture.individualLinks.filter(l => l.s === ind.uri);
    if (assertions.length === 0) return null;

    return (
      <div className="ml-6 mt-1 border-l border-neutral-800 pl-4 space-y-1">
        {assertions.map((a, i) => {
          let oStr = a.o;
          if (a.o_type === 'Literal') {
              oStr = a.o;
          }
          const inferred = isTripleInferred(a.s, a.p, a.o_type === 'Literal' ? `"${a.o}"` : a.o);
          
          return (
            <div key={i} className={`flex items-center gap-2 text-xs py-1 ${inferred ? 'text-emerald-400' : 'text-neutral-400'}`}>
              <div className="flex items-center gap-1">
                 <Link className="w-3 h-3 opacity-50" />
                 <span className="font-mono text-neutral-500">{shortName(a.p)}</span>
              </div>
              <ArrowRight className="w-3 h-3 text-neutral-600" />
              <span 
                className={`font-medium ${a.o_type === 'Literal' ? 'text-blue-400' : 'text-indigo-300 hover:text-indigo-200 cursor-pointer underline decoration-indigo-500/30 underline-offset-2'}`}
                onClick={(e) => {
                  if (a.o_type !== 'Literal') {
                    e.stopPropagation();
                    toggleNode(a.o, true);
                    setTimeout(() => {
                      const el = document.getElementById(`node-${a.o}`);
                      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }, 100);
                  }
                }}
              >
                {a.o_type === 'Literal' ? `"${a.o}"` : shortName(a.o)}
              </span>
              {inferred && (
                <span className="ml-2 text-[10px] px-1.5 py-0.5 bg-emerald-900/30 border border-emerald-500/20 text-emerald-400 rounded flex items-center gap-1">
                   <Sparkles className="w-3 h-3" /> Inféré
                </span>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  const renderIndividuals = (cls: any) => {
      if (!cls.individuals || cls.individuals.length === 0) return null;
      return cls.individuals.map((ind: any) => {
           const indExpanded = expandedNodes.has(ind.uri);
           const isTypeInferred = isTripleInferred(ind.uri, 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type', cls.uri);
           const reason = isTypeInferred ? checkInferenceReason(ind, cls.uri) : '';

           return (
             <div key={ind.uri} id={`node-${ind.uri}`} className="mt-1">
                <div 
                    className="flex flex-col cursor-pointer hover:bg-neutral-800/50 p-1.5 rounded-lg transition-colors group"
                    onClick={() => toggleNode(ind.uri)}
                >
                    <div className="flex items-center gap-2">
                      {indExpanded ? <ChevronDown className="w-3 h-3 text-neutral-500" /> : <ChevronRight className="w-3 h-3 text-neutral-500" />}
                      <User className="w-4 h-4 text-teal-400" />
                      <span className={`text-sm ${isTypeInferred ? 'text-emerald-300' : 'text-neutral-300'}`}>
                         {shortName(ind.uri)}
                      </span>
                      {isTypeInferred && (
                          <span className="ml-2 text-[10px] px-1.5 py-0.5 bg-emerald-900/30 border border-emerald-500/20 text-emerald-400 rounded flex items-center gap-1">
                             <Sparkles className="w-3 h-3" /> Type Inféré
                          </span>
                      )}
                    </div>
                    {isTypeInferred && (
                      <div className="ml-9 text-[10px] text-emerald-500/70 font-mono italic mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                        &gt; {reason}
                      </div>
                    )}
                </div>
                {indExpanded && renderAssertions(ind)}
             </div>
           );
      });
  };

  // ---------------- HIERARCHY RENDERER ----------------
  const renderHierarchyClass = (cls: any, depth: number = 0) => {
    const isExpanded = expandedNodes.has(cls.uri);
    const hasChildren = cls.children.length > 0 || cls.individuals.length > 0 || cls.propertiesDomain.length > 0;

    return (
      <div key={cls.uri} className="ml-4 mt-2">
        <div 
           className="flex items-center gap-2 cursor-pointer hover:bg-neutral-800/50 p-1.5 rounded-lg transition-colors group"
           onClick={() => toggleNode(cls.uri)}
        >
          {hasChildren ? (
            isExpanded ? <ChevronDown className="w-4 h-4 text-neutral-500" /> : <ChevronRight className="w-4 h-4 text-neutral-500" />
          ) : (
            <div className="w-4 h-4" />
          )}
          <Layers className="w-5 h-5 text-indigo-400" />
          <span className="text-sm font-medium text-neutral-200">{shortName(cls.uri)}</span>
          <span className="text-xs text-neutral-600 font-mono ml-2 hidden group-hover:inline-block">{cls.uri}</span>
        </div>

        {isExpanded && (
          <div className="ml-5 border-l border-neutral-800/50 pl-3 mt-1 space-y-1">
            
            {/* Properties (Domain) */}
            {cls.propertiesDomain.map((p: any, idx: number) => {
               const propExpanded = expandedNodes.has(`prop-${p.uri}`);
               const targets = p.ranges || (p.range ? [p.range] : []);
               return (
                 <div key={`d-${idx}`} className="flex flex-col">
                   <div 
                     className="flex items-center gap-2 text-xs py-1 px-2 text-amber-200/80 cursor-pointer hover:bg-neutral-800/50 rounded-lg group"
                     onClick={() => toggleNode(`prop-${p.uri}`)}
                   >
                      <Key className="w-3 h-3 text-amber-500" />
                      <span className="font-mono font-medium">DOMAINE :</span>
                      <span>{shortName(p.uri)}</span>
                      <ArrowRight className="w-3 h-3 opacity-50 mx-1" />
                      <span className="font-mono font-medium text-emerald-300">RANGE (Cible) :</span>
                      <span className="text-emerald-200">{targets.map((t: string) => shortName(t)).join(', ') || 'Inconnu'}</span>
                      <div className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity">
                         <Info className="w-3.5 h-3.5 text-neutral-500" />
                      </div>
                   </div>
                   {propExpanded && (
                       <div className="ml-6 mr-4 mt-1 mb-2 p-3 bg-neutral-900 border border-neutral-800 rounded-lg text-xs leading-relaxed text-neutral-300">
                          <p><strong className="text-amber-400">Domaine ({shortName(cls.uri)})</strong> : Cette propriété part d'ici. Si vous ou l'application dites que <em>"A {shortName(p.uri)} B"</em>, le raisonneur inférera automatiquement que A est un(e) <strong>{shortName(cls.uri)}</strong>.</p>
                          <p className="mt-1.5"><strong className="text-emerald-400">Range ({targets.map((t: string) => shortName(t)).join(', ') || 'Inconnu'})</strong> : La propriété pointe vers cette ou ces cibles. Si <em>"A {shortName(p.uri)} B"</em>, le raisonneur inférera que B est de ce(s) type(s).</p>
                       </div>
                   )}
                 </div>
               );
            })}

            {renderIndividuals(cls)}
            {cls.children.map((child: any) => renderHierarchyClass(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  // ---------------- DOMAIN-RANGE RENDERER ----------------
  const renderDomainRangeClass = (clsUri: string, visited: Set<string>) => {
    const cls = architecture.classes.find(c => c.uri === clsUri);
    if (!cls) return null;

    // To prevent infinite loops with domain->range cycles
    const newVisited = new Set(visited);
    const loopDetected = newVisited.has(clsUri);
    newVisited.add(clsUri);

    const isExpanded = expandedNodes.has(`dr-${clsUri}`);
    
    // Find all properties going out of this class
    const propertiesDomain: any[] = [];
    architecture.properties.forEach(prop => {
      const domains = prop.domains || (prop.domain ? [prop.domain] : []);
      if (domains.includes(clsUri)) {
          propertiesDomain.push(prop);
      }
    });

    const hasChildren = propertiesDomain.length > 0 || architecture.individuals.some(i => i.type === clsUri);

    return (
      <div key={`dr-${clsUri}-${visited.size}`} className="ml-4 mt-2">
        <div 
           className="flex items-center gap-2 cursor-pointer hover:bg-neutral-800/50 p-1.5 rounded-lg transition-colors group"
           onClick={() => !loopDetected && toggleNode(`dr-${clsUri}`)}
        >
          {!loopDetected && hasChildren ? (
            isExpanded ? <ChevronDown className="w-4 h-4 text-neutral-500" /> : <ChevronRight className="w-4 h-4 text-neutral-500" />
          ) : (
            <div className="w-4 h-4" />
          )}
          <Layers className={`w-5 h-5 ${loopDetected ? 'text-neutral-500' : 'text-indigo-400'}`} />
          <span className={`text-sm font-medium ${loopDetected ? 'text-neutral-500' : 'text-neutral-200'}`}>
              {shortName(clsUri)} {loopDetected && " (Cycle / Retour)"}
          </span>
        </div>

        {isExpanded && !loopDetected && (
          <div className="ml-5 border-l border-neutral-800/50 pl-3 mt-1 space-y-2">
            
            {/* Find properties, then for each property, show its ranges */}
            {propertiesDomain.map((p: any, idx: number) => {
               const propExpanded = expandedNodes.has(`dr-p-${clsUri}-${p.uri}`);
               const targets = p.ranges || (p.range ? [p.range] : []);
               
               return (
                 <div key={`dr-prop-${idx}`} className="flex flex-col">
                   <div 
                     className="flex items-center gap-2 text-xs py-1 px-2 text-amber-200/80 cursor-pointer hover:bg-neutral-800/50 rounded-lg group"
                     onClick={() => toggleNode(`dr-p-${clsUri}-${p.uri}`)}
                   >
                      {propExpanded ? <ChevronDown className="w-3 h-3 text-amber-500/50" /> : <ChevronRight className="w-3 h-3 text-amber-500/50" />}
                      <Key className="w-3 h-3 text-amber-500" />
                      <span>{shortName(p.uri)}</span>
                      <ArrowRight className="w-3 h-3 opacity-50 mx-1" />
                      <span className="font-mono font-medium text-emerald-300">Cible(s) :</span>
                   </div>
                   
                   {/* Render the ranges under this property! */}
                   {propExpanded && (
                       <div className="ml-6 border-l border-dashed border-neutral-700/50 pl-3">
                           {targets.length === 0 ? (
                               <div className="text-xs text-neutral-500 py-1 ml-4 italic">Cible littérale ou inconnue</div>
                           ) : (
                               targets.map((tUri: string) => renderDomainRangeClass(tUri, newVisited))
                           )}
                       </div>
                   )}
                 </div>
               );
            })}

            {/* Render direct individuals here to give life if desired */}
            {/* But usually in DR view we might just want structural. Let's add them wrapped. */}
            <div className="pt-2">
              {renderIndividuals({ individuals: architecture.individuals.filter(i => i.type === clsUri), uri: clsUri })}
            </div>
            
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="bg-neutral-900/30 border border-neutral-800 rounded-2xl p-6">
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
          <div className="flex items-center gap-3">
              <Network className="w-5 h-5 text-indigo-400" />
              <h3 className="text-lg font-medium text-neutral-200">Explorateur Arborescent (TBox & ABox)</h3>
          </div>
          
          <div className="flex bg-neutral-950 rounded-lg p-1 border border-neutral-800">
             <button 
                onClick={() => setViewMode('hierarchy')}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors flex items-center gap-2 ${viewMode === 'hierarchy' ? 'bg-neutral-800 text-white' : 'text-neutral-400 hover:text-neutral-200'}`}
             >
                <Layers className="w-3.5 h-3.5" />
                Hiérarchie (Standard)
             </button>
             <button 
                onClick={() => setViewMode('domain-range')}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors flex items-center gap-2 ${viewMode === 'domain-range' ? 'bg-neutral-800 text-white' : 'text-neutral-400 hover:text-neutral-200'}`}
             >
                <Waypoints className="w-3.5 h-3.5" />
                Suivi Domain → Range
             </button>
          </div>
      </div>

      <div className="p-4 bg-neutral-950 rounded-xl border border-neutral-800 overflow-x-auto min-h-[400px]">
         {viewMode === 'hierarchy' ? (
             hierarchyRoots.map((r, i) => renderHierarchyClass(r, 0))
         ) : (
             domainRangeRoots.map((r, i) => renderDomainRangeClass(r.uri, new Set()))
         )}
      </div>
    </div>
  );
};

const ArrowRight = ({ className }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M5 12h14M12 5l7 7-7 7"/>
  </svg>
);

