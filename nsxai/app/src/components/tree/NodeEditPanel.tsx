import React, { useState, useMemo } from 'react';
import { X, Plus, Check, Trash2, ArrowRight, Link as LinkIcon, ChevronDown, ChevronRight, Sparkles, Loader2 } from 'lucide-react';
import {
  type Triple,
  type PredicateSuggestion,
  isLiteralRange,
  isNativePred,
  URIS,
  NS,
  getShortUri as shortLocal,
  filterUsedByTriples,
  countUsages,
  literalColorClass,
  typeColorClass,
  getPrimaryTypeUris,
  shortTypeName,
  isLiteralType
} from '../../lib/core';
import { ObjectSelectorModal } from './ObjectSelectorModal';
import { GraphMinimap } from './GraphMinimap';
import { fetchApi } from '../../lib/apiClient';

const RDFS_NS = NS.RDFS;

export interface NodeEditPanelProps {
  node: string;
  subjectsMap: Map<string, Triple[]>;
  predicates: PredicateSuggestion[];
  knownTypeUris: string[];
  getShortUri: (u: string) => string;
  editMode: boolean;
  onAddTriple: (predicate: string, value: string, isLiteral: boolean) => void;
  onDeleteTriple: (predicate: string, value: string, isLiteral: boolean) => void;
  onDeleteEntity: () => void;
  onRefresh?: () => void;
  onCreateEntity?: (classUri: string, predicate: PredicateSuggestion) => void;
  creationStack?: Array<{ predicate: PredicateSuggestion; subject: string }>;
  onBackFromStack?: () => void;
  onNavigate: (uri: string) => void;
  triples: Triple[];
  allProperties?: { uri: string; label?: string; range?: string }[];
}

// Composant interne pour afficher les types à la suite du nom de l'objet
function TypeSuffix({ typeUri, getShortUri }: { typeUri: string; getShortUri: (u: string) => string }) {
  const short = shortTypeName(typeUri) || getShortUri(typeUri);
  return (
    <span className="text-[11px] text-neutral-500 font-normal ml-1">
      <span className="text-neutral-600">a</span>{' '}
      <span className={`font-medium ${typeColorClass(typeUri)}`}>{short}</span>
    </span>
  );
}

export function NodeEditPanel({
  node, subjectsMap, predicates, getShortUri,
  editMode, onAddTriple, onDeleteTriple, onDeleteEntity, onCreateEntity, creationStack, onBackFromStack, onNavigate, triples, allProperties = []
}: NodeEditPanelProps) {
  const nodeTriples = subjectsMap.get(node) ?? [];
  const usagesCount = countUsages(node, triples);

  // Pour la section "Utilisé par"
  const [showUsages, setShowUsages] = useState(false);

  // IA Suggestions
  const [suggestions, setSuggestions] = useState<Array<{target_uri: string, probability: number}>>([]);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);

  const fetchSuggestions = async () => {
    setIsSuggesting(true);
    setSuggestionError(null);
    try {
      const res = await fetchApi('predict/recommendations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_uri: node, top_k: 5 }),
      });
      if (res.ok) {
        const data = await res.json();
        setSuggestions(data.recommendations || []);
      } else {
        const errorData = await res.json();
        setSuggestionError(errorData.detail || "Erreur de prédiction");
      }
    } catch (e) {
      setSuggestionError("Impossible de contacter le service ML.");
    } finally {
      setIsSuggesting(false);
    }
  };

  // State for object selection modal
  const [selectedPred, setSelectedPred] = useState<PredicateSuggestion | null>(null);
  const [showObjectModal, setShowObjectModal] = useState(false);
  const [literalValue, setLiteralValue] = useState('');
  const [propertySearch, setPropertySearch] = useState('');

  const handleObjectSelect = (value: string, isLiteral: boolean) => {
    if (!selectedPred) return;
    onAddTriple(selectedPred.uri, value, isLiteral);
    setSelectedPred(null);
    setShowObjectModal(false);
    setLiteralValue('');
  };

  const handleLiteralSubmit = () => {
    if (!selectedPred || !literalValue.trim()) return;
    onAddTriple(selectedPred.uri, literalValue.trim(), true);
    setSelectedPred(null);
    setLiteralValue('');
  };

  const handleCreateEntity = (classUri: string) => {
    if (!selectedPred) return;
    if (onCreateEntity) onCreateEntity(classUri, selectedPred);
    setShowObjectModal(false);
    setSelectedPred(null);
  };

  const baseUri = node.split('#')[0] || node.split('/')[0];

  const existingByPred = useMemo(() => {
    const map = new Map<string, Triple[]>();
    for (const t of nodeTriples) {
      if (!map.has(t.predicate)) map.set(t.predicate, []);
      map.get(t.predicate)!.push(t);
    }
    return map;
  }, [nodeTriples]);

  const [showAllProps, setShowAllProps] = useState(false);

  const otherPropertiesList = useMemo(() => {
    const existingUris = new Set(predicates.map(p => p.uri));
    for (const t of nodeTriples) existingUris.add(t.predicate);
    
    const list: Array<{ pred: PredicateSuggestion; domain: string | null; isNative: boolean }> = [];
    
    const architectureUris = new Set(allProperties.map(p => p.uri));

    for (const t of triples) {
      if (!existingUris.has(t.predicate) && !isNativePred(t.predicate) && !architectureUris.has(t.predicate)) {
        existingUris.add(t.predicate);
        list.push({
          pred: { uri: t.predicate, label: shortLocal(t.predicate), range: `${RDFS_NS}Resource`, source: 'assertion', domains: [] },
          domain: 'Utilisée dans le graphe (inconnue)',
          isNative: false
        });
      }
    }

    return list.sort((a, b) => (a.pred.label || shortLocal(a.pred.uri)).localeCompare(b.pred.label || shortLocal(b.pred.uri)));
  }, [allProperties, predicates, nodeTriples, triples]);

  // Aplatir et trier les prédicats
  const allPredicatesList = useMemo(() => {
    const list: Array<{ pred: PredicateSuggestion; domain: string | null; isNative: boolean }> = [];
    const nativesMap = new Map<string, PredicateSuggestion>();

    // 1. Collecter les propriétés existantes natives (ex: rdfs:label qui ne serait pas dans predicates)
    for (const t of nodeTriples) {
      if (isNativePred(t.predicate) && t.predicate !== URIS.RDF_TYPE && !nativesMap.has(t.predicate)) {
        nativesMap.set(t.predicate, {
          uri: t.predicate, label: shortLocal(t.predicate), domains: [], range: `${RDFS_NS}Literal`, source: 'assertion',
        });
      }
    }

    // 2. Assigner les domaines
    for (const pred of predicates) {
      if (isNativePred(pred.uri)) {
        if (pred.uri !== URIS.RDF_TYPE) nativesMap.set(pred.uri, pred);
        continue;
      }
      const domains = pred.domains ?? [];
      const domainGrp = domains.length > 0 ? domains[0] : null;
      list.push({ pred, domain: domainGrp ? shortLocal(domainGrp) : 'Autre', isNative: false });
    }

    // Ajouter rdf:type manuellement pour qu'il soit toujours premier
    const typePred = predicates.find(p => p.uri === URIS.RDF_TYPE);
    if (typePred) {
      list.push({ pred: typePred, domain: 'Natif', isNative: true });
    }

    for (const p of nativesMap.values()) {
      list.push({ pred: p, domain: 'Natif', isNative: true });
    }

    // 3. Trier
    return list.sort((a, b) => {
      // rdf:type toujours en premier
      if (a.pred.uri === URIS.RDF_TYPE) return -1;
      if (b.pred.uri === URIS.RDF_TYPE) return 1;
      
      // Natifs en suite
      if (a.isNative && !b.isNative) return -1;
      if (!a.isNative && b.isNative) return 1;

      // Sinon ordre alphabétique
      return (a.pred.label || shortLocal(a.pred.uri)).localeCompare(b.pred.label || shortLocal(b.pred.uri));
    });
  }, [predicates, nodeTriples]);

  const renderTreeProp = (item: { pred: PredicateSuggestion; domain: string | null; isNative: boolean }) => {
    const { pred, domain, isNative } = item;
    
    // Filtre de recherche
    if (propertySearch.trim()) {
      const searchLower = propertySearch.toLowerCase();
      const labelMatch = (pred.label || shortLocal(pred.uri)).toLowerCase().includes(searchLower);
      const uriMatch = shortLocal(pred.uri).toLowerCase().includes(searchLower);
      if (!labelMatch && !uriMatch) return null;
    }

    const existing = existingByPred.get(pred.uri) ?? [];
    const litRange = isLiteralRange(pred.range);
    const name = pred.label || shortLocal(pred.uri);
    const hasValues = existing.length > 0;

    return (
      <div key={pred.uri} className="flex flex-col mt-2 first:mt-0 relative group">
        {/* Propriété (Prédicat) */}
        <div className="flex items-center gap-1.5 w-full">
          <div className="py-1.5 px-2 text-sm flex items-center gap-2 hover:bg-neutral-800/40 rounded transition-colors group/pred w-fit">
            <LinkIcon className="w-4 h-4 text-neutral-500/50 shrink-0" />
            <span className="font-medium text-neutral-400 group-hover/pred:text-neutral-200 transition-colors cursor-default">
              {name}
            </span>
            
            {/* Tag Domaine */}
            {domain && !isNative && domain !== 'Autre' && (
              <span className="text-[9px] text-neutral-400 ml-1 font-mono tracking-wide uppercase">
                {domain}
              </span>
            )}

            {/* Hint du Type Attendu (Range) visible seulement en édition s'il n'y a pas de valeur */}
            {pred.range && !hasValues && editMode && (
              <span className="text-[11px] text-neutral-600 font-mono ml-1">→ {shortLocal(pred.range)}</span>
            )}
          </div>

          {/* Bouton Ajouter (visible au survol de la ligne entière si en édition) */}
          {editMode && !selectedPred && (
             <button
               onClick={() => {
                 setSelectedPred(pred);
                 if (!litRange) setShowObjectModal(true);
                 else setLiteralValue('');
               }}
               className="opacity-0 group-hover:opacity-100 transition-all duration-300 text-[11px] font-medium flex items-center gap-1.5 bg-white/5 border border-white/5 text-neutral-300 px-3 py-1 rounded-full hover:bg-white/10 hover:text-white hover:border-white/10 shadow-sm"
             >
               <Plus className="w-3.5 h-3.5" /> Ajouter
             </button>
          )}
        </div>

        {/* Valeurs (Objets) */}
        <div className={`space-y-1.5 ml-[17px] border-l ${editMode && !hasValues ? 'border-dashed border-neutral-700' : 'border-neutral-800/60'} pl-4 mt-1.5`}>
          {existing.length === 0 && !editMode && (
            <div className="py-1 px-2 text-xs italic text-neutral-600">Aucune valeur</div>
          )}
          
          {existing.length === 0 && editMode && selectedPred?.uri !== pred.uri && (
            <div className="py-1 px-2 text-xs italic text-neutral-500">Saisir une valeur...</div>
          )}

          {existing.map((t, vi) => {
            const objTypes = subjectsMap.has(t.object) ? getPrimaryTypeUris(subjectsMap.get(t.object) || []) : [];
            const displayObjLabel = subjectsMap.has(t.object) 
               ? (subjectsMap.get(t.object)?.find(p => p.predicate === URIS.RDFS_LABEL)?.object || shortLocal(t.object))
               : shortLocal(t.object);

            return (
              <div key={vi} className="py-1.5 px-2 text-sm flex items-baseline flex-wrap gap-1.5 hover:bg-neutral-800/40 rounded group/val relative">
                 {isLiteralType(t.objectType) ? (
                    <span className={literalColorClass()}>"{t.object}"</span>
                 ) : (
                    <div className="flex items-baseline gap-1">
                      <button onClick={() => onNavigate(t.object)} className="text-neutral-300 hover:text-white hover:underline cursor-pointer">
                        {displayObjLabel}
                      </button>
                      {/* Affichage des types du nœud objet s'il est dans la map */}
                      {objTypes.map((tu) => (
                         <TypeSuffix key={tu} typeUri={tu} getShortUri={getShortUri} />
                      ))}
                    </div>
                 )}

                 {editMode && (
                   <button
                     onClick={() => onDeleteTriple(t.predicate, t.object, isLiteralType(t.objectType))}
                     className="opacity-0 group-hover/val:opacity-100 text-neutral-400 bg-white/5 border border-white/5 hover:bg-red-500/20 hover:text-red-400 hover:border-red-500/30 transition-all duration-300 ml-2 focus:opacity-100 p-1 rounded-full shadow-sm"
                     title="Supprimer la valeur"
                   >
                     <X className="w-3.5 h-3.5" />
                   </button>
                 )}
              </div>
            );
          })}

          {/* Champ de saisie Inline (pour les littéraux) */}
          {editMode && selectedPred?.uri === pred.uri && litRange && (
            <div className="mt-1.5 mb-1 flex items-center gap-2 w-full max-w-sm">
              <input
                autoFocus
                type="text"
                value={literalValue}
                onChange={e => setLiteralValue(e.target.value)}
                placeholder="Saisir la valeur..."
                className="flex-1 bg-transparent px-2 py-1.5 text-sm text-neutral-100 placeholder:text-neutral-600 focus:outline-none font-mono"
                onKeyDown={e => {
                  if (e.key === 'Enter') handleLiteralSubmit();
                  if (e.key === 'Escape') { setSelectedPred(null); setLiteralValue(''); }
                }}
              />
              <button
                onClick={handleLiteralSubmit}
                disabled={!literalValue.trim()}
                className="p-1 text-blue-400 hover:text-blue-300 transition-colors disabled:opacity-50"
              >
                <Check className="w-4 h-4" />
              </button>
              <button
                onClick={() => { setSelectedPred(null); setLiteralValue(''); }}
                className="p-1 text-neutral-500 hover:text-neutral-300 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </div>
    );
  };

  // Label du nœud courant
  const nodeLabel = nodeTriples.find(t => t.predicate === URIS.RDFS_LABEL)?.object || shortLocal(node);
  const nodeTypes = getPrimaryTypeUris(nodeTriples);

  return (
    <div className="h-full flex flex-col border border-white/10 bg-[#0a0a0a]/80 backdrop-blur-2xl rounded-[2rem] shadow-2xl ring-1 ring-white/5 animate-in fade-in duration-200 overflow-hidden relative">
      
      {/* HEADER : Titre Racine style Arbre */}
      <div className="shrink-0 p-6 border-b border-neutral-800/80 bg-neutral-900/20">
        {creationStack && creationStack.length > 0 && (
          <button
            onClick={onBackFromStack}
            className="mb-4 text-sm text-neutral-400 hover:text-neutral-200 transition-colors flex items-center gap-2 w-fit"
          >
            ← Retour à {creationStack[creationStack.length - 1]?.predicate.label || shortLocal(creationStack[creationStack.length - 1]?.predicate.uri || '')}
          </button>
        )}
        
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div>
            {/* Ligne Titre et Types */}
            <div className="flex items-baseline gap-2 flex-wrap">
               <h2 className="text-3xl font-bold tracking-tight text-neutral-100">{nodeLabel}</h2>
               {nodeTypes.map((tu) => (
                 <TypeSuffix key={tu} typeUri={tu} getShortUri={getShortUri} />
               ))}
            </div>
            {/* Ligne URI */}
            <div className="mt-2 text-xs text-neutral-500/70 font-mono">
              {node}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {editMode && (
              <button
                onClick={fetchSuggestions}
                disabled={isSuggesting}
                className="text-[11px] font-medium flex items-center gap-1.5 text-indigo-300 bg-indigo-500/10 border border-indigo-500/20 hover:bg-indigo-500/20 px-4 py-1.5 rounded-full transition-all duration-300 shadow-sm disabled:opacity-50"
              >
                {isSuggesting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                Suggérer relations (IA)
              </button>
            )}

            {editMode && (
              <button
                onClick={onDeleteEntity}
                className="text-[11px] font-medium flex items-center gap-2 text-neutral-300 bg-white/5 border border-white/5 hover:bg-red-500/20 hover:text-red-400 hover:border-red-500/30 px-4 py-1.5 rounded-full transition-all duration-300 shadow-sm"
              >
                <Trash2 className="w-3.5 h-3.5" /> Supprimer
              </button>
            )}
          </div>
        </div>

        {/* Suggestions IA */}
        {(suggestions.length > 0 || suggestionError) && (
          <div className="mt-4 p-3 bg-indigo-950/20 border border-indigo-500/20 rounded-xl">
             <div className="flex items-center justify-between mb-2">
               <h3 className="text-xs font-semibold text-indigo-300 flex items-center gap-1.5 uppercase tracking-wider">
                 <Sparkles className="w-3.5 h-3.5" /> Recommandations du Modèle
               </h3>
               <button onClick={() => { setSuggestions([]); setSuggestionError(null); }} className="text-neutral-500 hover:text-neutral-300">
                 <X className="w-3.5 h-3.5" />
               </button>
             </div>
             
             {suggestionError ? (
               <p className="text-xs text-red-400">{suggestionError}</p>
             ) : (
               <div className="space-y-1.5">
                 {suggestions.map((sug, i) => (
                   <div key={i} className="flex flex-wrap items-center justify-between bg-black/20 p-2 rounded-lg border border-white/5 text-sm">
                      <div className="flex items-center gap-2">
                         <button onClick={() => onNavigate(sug.target_uri)} className="text-neutral-200 hover:text-white hover:underline cursor-pointer font-medium">
                           {subjectsMap.get(sug.target_uri)?.find(t => t.predicate === URIS.RDFS_LABEL)?.object || shortLocal(sug.target_uri)}
                         </button>
                         <span className="text-[10px] text-neutral-500 font-mono">{shortLocal(sug.target_uri)}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-indigo-400 font-mono bg-indigo-500/10 px-1.5 py-0.5 rounded">
                          {(sug.probability * 100).toFixed(1)}%
                        </span>
                        <button
                          onClick={() => {
                             // Assuming we don't know the exact predicate, but often it's 'hasFeature' or 'containsGameElement'
                             // The user can add it manually, or we can prompt for the predicate.
                             // For now we just copy the target_uri to clipboard or show modal.
                             navigator.clipboard.writeText(sug.target_uri);
                             alert("URI copiée. Vous pouvez l'ajouter via le bouton '+ Ajouter' d'une propriété.");
                          }}
                          className="text-[10px] bg-white/5 hover:bg-white/10 px-2 py-1 rounded text-neutral-300 transition-colors"
                        >
                          Copier l'URI
                        </button>
                      </div>
                   </div>
                 ))}
               </div>
             )}
          </div>
        )}
      </div>

      {/* BARRE DE RECHERCHE */}
      <div className="shrink-0 px-6 py-3 border-b border-neutral-800/50 flex flex-col sm:flex-row gap-4 items-center justify-between">
        {editMode ? (
           <div className="relative w-full sm:w-96">
            <input
              type="text"
              value={propertySearch}
              onChange={e => setPropertySearch(e.target.value)}
              placeholder="Rechercher une propriété..."
              className="w-full bg-white/5 border border-transparent focus:bg-white/10 focus:border-white/20 rounded-full pl-4 pr-10 py-2 text-sm text-neutral-200 placeholder:text-neutral-500 focus:outline-none transition-all duration-300"
            />
            {propertySearch && (
              <button onClick={() => setPropertySearch('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-500 hover:text-neutral-300">
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        ) : (
          <div className="text-sm text-neutral-500 italic">
            Mode visualisation. Activez l'édition pour modifier les propriétés.
          </div>
        )}
      </div>

      {/* CONTENU : L'Arborescence des Propriétés */}
      <div className="flex-1 overflow-y-auto px-6 py-4 custom-scrollbar">
        {selectedPred && !isLiteralRange(selectedPred.range) && (
          <ObjectSelectorModal
            isOpen={showObjectModal}
            onClose={() => { setShowObjectModal(false); setSelectedPred(null); }}
            predicate={selectedPred}
            subject={node}
            baseUri={baseUri}
            onSelect={handleObjectSelect}
            onCreateEntity={handleCreateEntity}
            triples={triples}
            subjectsMap={subjectsMap}
          />
        )}
        
        <div className="pl-4">
           {allPredicatesList.map(item => renderTreeProp(item))}
           
           {editMode && otherPropertiesList.length > 0 && (
             <div className="mt-6 border-t border-white/5 pt-4">
               {!propertySearch.trim() && (
                 <button 
                   onClick={() => setShowAllProps(!showAllProps)}
                   className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-neutral-500 hover:text-neutral-300 transition-colors mb-2"
                 >
                   <ChevronRight className={`w-4 h-4 transition-transform ${showAllProps ? 'rotate-90' : ''}`} />
                   Autres propriétés ({otherPropertiesList.length})
                 </button>
               )}
               
               {(showAllProps || propertySearch.trim()) && (
                 <div className="pl-4 border-l border-white/5 ml-2 mt-2">
                   {otherPropertiesList.map(item => renderTreeProp(item))}
                 </div>
               )}
             </div>
           )}
        </div>

        {/* SECTION UTILISÉ PAR */}
        {usagesCount > 0 && (
          <div className="mt-8 mb-6 pl-4">
             {!propertySearch.trim() && (
               <button onClick={() => setShowUsages(!showUsages)} className="flex items-center gap-2 group w-fit">
                  {showUsages ? <ChevronDown className="w-4 h-4 text-emerald-500" /> : <ChevronRight className="w-4 h-4 text-emerald-500" />}
                  <span className="text-[12px] font-medium text-emerald-500 group-hover:text-emerald-400 transition-colors uppercase tracking-wider">
                    Utilisé par ({usagesCount} relations)
                  </span>
                </button>
             )}
              
              {(showUsages || propertySearch.trim()) && (
                <div className="pl-6 border-l border-emerald-900/30 ml-[7px] mt-2 space-y-1.5">
                  {filterUsedByTriples(node, triples)
                    .filter(triple => !propertySearch.trim() || shortLocal(triple.predicate).toLowerCase().includes(propertySearch.trim().toLowerCase()))
                    .map((triple, idx) => (
                    <div key={idx} className="py-1 px-2 text-[12px] flex items-center gap-2 text-neutral-400 hover:bg-neutral-800/30 rounded w-fit">
                       <button onClick={() => onNavigate(triple.subject)} className="text-neutral-300 hover:text-white hover:underline cursor-pointer">
                          {getShortUri(triple.subject)}
                       </button>
                       <span className="text-neutral-600 font-mono text-[10px] mx-1 bg-neutral-900 px-1 py-0.5 rounded border border-neutral-800">
                         {getShortUri(triple.predicate)}
                       </span>
                       <span className="text-emerald-400/80">{getShortUri(node)}</span>
                    </div>
                  ))}
                </div>
              )}
          </div>
        )}
      </div>

      <GraphMinimap
        nodeUri={node}
        triples={triples}
        subjectsMap={subjectsMap}
        shortLocal={shortLocal}
        onNavigate={onNavigate}
      />
    </div>
  );
}
