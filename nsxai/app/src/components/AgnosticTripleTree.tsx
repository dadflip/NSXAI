import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { X, Loader2, Plus, Edit3, Check, Trash2, ChevronRight } from 'lucide-react';
import {
  type Triple,
  type PredicateSuggestion,
  buildSubjectsMap,
  resolveAllSubjects,
  sortSubjects,
  collectKnownTypeUris,
  collectAncestorSubjects,
  subjectMatchesSearch,
  findUsedBy,
  filterUsedByTriples,
  countUsages,
  NS,
  URIS,
  META_TYPES,
  getShortUri,
  isLiteralRange,
  getPrimaryTypeUris,
  isLiteralType,
  isNativePred,
  computeApplicablePredicates
} from '../lib/core';
import { fetchApi } from '../lib/apiClient';
import { CONFIG } from '../config';
import { SubjectTreeNode, type TreeNodeContext } from './TripletTreeShared';
import { StudioCard } from './studio/StudioPrimitives';
import { WikiLayout } from './WikiLayout';

interface AgnosticTripleTreeProps {
  triples: Triple[];
  architecture?: {
    classes?: { uri: string }[];
    properties?: { uri: string }[];
    individuals?: { uri: string }[];
  } | null;
  onRefresh?: () => void;
  search: string;
  editMode: boolean;
  creatingNew: boolean;
  onSetCreatingNew: (v: boolean) => void;
  onCancelCreate: () => void;
  onSelectNode?: (id: string) => void;
}

import { NewEntityForm } from './tree/NewEntityForm';
import { NodeEditPanel } from './tree/NodeEditPanel';

export function AgnosticTripleTree({
  triples,
  architecture,
  onRefresh,
  search,
  editMode,
  creatingNew,
  onSetCreatingNew,
  onCancelCreate,
  onSelectNode,
}: AgnosticTripleTreeProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [usedByFilter, setUsedByFilter] = useState<string | null>(null);
  const [creationStack, setCreationStack] = useState<Array<{ predicate: PredicateSuggestion; subject: string }>>([]);
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set());

  const toggleType = (typeUri: string) => {
    setExpandedTypes((prev) => {
      const n = new Set(prev);
      if (n.has(typeUri)) n.delete(typeUri);
      else n.add(typeUri);
      return n;
    });
  };

  const handleCreateNew = async () => {
    const uriInput = document.getElementById('new-uri') as HTMLInputElement;
    const labelInput = document.getElementById('new-label') as HTMLInputElement;

    const localUri = uriInput?.value || '';
    const label = labelInput?.value || '';

    if (!localUri) {
      alert('Veuillez spécifier une URI ou un nom.');
      return;
    }

    const fullUri = `${CONFIG.ontology.defaultBaseUri}${localUri}`;

    try {
      const response = await fetchApi('create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'individual',
          uri: fullUri,
          label,
          comment: '',
        }),
      });

      if (response.ok) {
        // If there's a stack context, automatically add the created entity as the value
        if (creationStack.length > 0) {
          const stackItem = creationStack[creationStack.length - 1];
          await handleAddProperty(stackItem.subject, stackItem.predicate.uri, fullUri, false);
          // Pop from stack
          setCreationStack(prev => prev.slice(0, -1));
        }

        // On refresh pour que tout soit d'équerre
        if (onRefresh) await onRefresh();
        setCreatingNew(false);
        setSelectedNode(fullUri);
      } else {
        alert('Erreur lors de la création');
      }
    } catch (e) {
      console.error(e);
      alert('Erreur lors de la création');
    }
  };

  const handleCreateEntity = (classUri: string, predicate: PredicateSuggestion) => {
    if (selectedNode) {
      setCreationStack(prev => [...prev, { predicate, subject: selectedNode }]);
    }
    onSetCreatingNew(true);
    setTimeout(() => {
      const typeSelect = document.getElementById('new-type') as HTMLSelectElement;
      if (typeSelect) typeSelect.value = classUri;
    }, 0);
  };

  const handleBackFromStack = () => {
    setCreationStack(prev => prev.slice(0, -1));
  };

  const handleAddProperty = async (subject: string, predicate: string, value: string, isLiteral: boolean) => {
    if (!predicate || !value) {
      alert('Veuillez sélectionner une propriété et entrer une valeur');
      return;
    }
    const triplesToInsert = [{
      s: subject,
      p: predicate,
      o: value,
      isLiteral,
    }];

    try {
      const response = await fetchApi('triples', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ triples: triplesToInsert }),
      });

      if (response.ok) {
        if (onRefresh) onRefresh();
      } else {
        alert('Erreur lors de l\'ajout');
      }
    } catch (error) {
      console.error('Error adding property:', error);
      alert('Erreur lors de l\'ajout');
    }
  };

  const handleDeleteTriple = async (subject: string, predicate: string, value: string, isLiteral: boolean) => {
    try {
      const response = await fetchApi('triples', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ s: subject, p: predicate, o: value, isLiteral }),
      });
      if (response.ok) {
        if (onRefresh) onRefresh();
      } else {
        alert('Erreur lors de la suppression');
      }
    } catch (error) {
      console.error('Error deleting triple:', error);
      alert('Erreur lors de la suppression');
    }
  };

  const handleDeleteEntity = async (subject: string) => {
    if (!window.confirm(`Voulez-vous vraiment supprimer "${getShortUri(subject)}" et toutes ses relations ?`)) return;

    // Find all triples where subject is S or object is S
    const toDelete = triples.filter(t => t.subject === subject || (!isLiteralType(t.objectType) && t.object === subject));

    try {
      // Execute sequential deletions
      for (const t of toDelete) {
         await fetchApi('triples', {
           method: 'DELETE',
           headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify({ s: t.subject, p: t.predicate, o: t.object, isLiteral: isLiteralType(t.objectType) }),
         });
      }
      setSelectedNode(null);
      if (onRefresh) onRefresh();
    } catch (error) {
       console.error('Error deleting entity:', error);
       alert('Erreur lors de la suppression de l\'entité');
    }
  };

  const subjectsMap = useMemo(() => buildSubjectsMap(triples), [triples]);

  const availablePredicates = useMemo(() => {
    if (!selectedNode) return [];
    return computeApplicablePredicates(selectedNode, triples, architecture);
  }, [selectedNode, triples, architecture]);

  const knownTypeUris = useMemo(
    () => collectKnownTypeUris(triples, architecture),
    [triples, architecture]
  );
  const allSubjectIds = useMemo(() => Array.from(subjectsMap.keys()), [subjectsMap]);

  const visibleRoots = useMemo(() => {
    const raw = resolveAllSubjects(subjectsMap);
    const sorted = sortSubjects(raw, getShortUri);
    let filtered = sorted;

    if (search.trim()) {
      filtered = filtered.filter((r) => subjectMatchesSearch(r, subjectsMap, search, getShortUri));
    }

    if (typeFilter) {
      filtered = filtered.filter((subject) => {
        const properties = subjectsMap.get(subject) || [];
        return properties.some(
          (t) => t.predicate === URIS.RDF_TYPE && t.object === typeFilter
        );
      });
    }

    if (usedByFilter) {
      const usedBySubjects = findUsedBy(usedByFilter, triples);
      filtered = filtered.filter((subject) => usedBySubjects.includes(subject));
    }

    return filtered;
  }, [subjectsMap, search, typeFilter, usedByFilter, triples, getShortUri]);

  const displayRoots = visibleRoots;

  useEffect(() => {
    if (!search.trim()) return;
    const next = new Set<string>();
    const visited = new Set<string>();
    for (const s of allSubjectIds) {
      if (subjectMatchesSearch(s, subjectsMap, search, getShortUri)) {
        next.add(s);
        collectAncestorSubjects(s, triples, visited).forEach((a) => next.add(a));
      }
    }
    setExpanded(next);
  }, [search, triples, allSubjectIds, subjectsMap, getShortUri]);

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  };

  const handleSelectNode = (id: string) => {
    setSelectedNode(id);
    if (onSelectNode) onSelectNode(id);
  };

  const collapseAll = () => setExpandedTypes(new Set());
  const expandAll = () => {
    const types = new Set<string>();
    for (const sub of displayRoots) {
      const ts = getPrimaryTypeUris(subjectsMap.get(sub) || []);
      if (ts.length === 0) types.add('Sans type');
      else ts.forEach(t => types.add(t));
    }
    setExpandedTypes(types);
  };

  const treeCtx: TreeNodeContext = useMemo(
    () => ({
      subjectsMap,
      getShortUri,
      maxDepth: 50,
      expanded,
      onToggle: toggleExpand,
      onSelectNode: handleSelectNode,
      searchQuery: search,
      renderEditSlot: undefined,
    }),
    [
      subjectsMap,
      getShortUri,
      expanded,
      handleSelectNode,
      search,
    ]
  );


  return (
    <WikiLayout
      sidebarTitle={selectedNode ? getShortUri(selectedNode) : 'Édition'}
      navigation={
        <div className="flex flex-col h-full">
          <div className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar">
            <div className="font-sans text-[13.5px] py-2 px-1">
              {displayRoots.length === 0 ? (
                <p className="text-neutral-600 text-center py-6 text-xs font-sans">Aucun élément</p>
              ) : (
                (() => {
                  const groups = new Map<string, string[]>();
                  for (const sub of displayRoots) {
                    const types = getPrimaryTypeUris(subjectsMap.get(sub) || []);
                    if (types.length === 0) {
                      if (!groups.has('Sans type')) groups.set('Sans type', []);
                      groups.get('Sans type')!.push(sub);
                    } else {
                      for (const typeUri of types) {
                        if (!groups.has(typeUri)) groups.set(typeUri, []);
                        groups.get(typeUri)!.push(sub);
                      }
                    }
                  }
                  const sortedKeys = Array.from(groups.keys()).sort((a, b) => getShortUri(a).localeCompare(getShortUri(b)));
                  return sortedKeys.map(typeUri => (
                    <div key={typeUri} className="mb-2">
                      <div 
                        className="flex items-center gap-2 py-1 px-2 mb-1 cursor-pointer hover:bg-white/5 transition-colors group"
                        onClick={() => toggleType(typeUri)}
                      >
                        <ChevronRight className={`w-3.5 h-3.5 text-neutral-500 transition-transform ${expandedTypes.has(typeUri) ? 'rotate-90' : ''}`} />
                        <span className="text-[11px] uppercase tracking-widest font-semibold text-neutral-400 group-hover:text-white transition-colors">{getShortUri(typeUri)}</span>
                        <span className="text-[10px] text-neutral-600">({groups.get(typeUri)?.length})</span>
                      </div>
                      {expandedTypes.has(typeUri) && (
                        <div className="pl-2 border-l border-white/5 ml-[11px]">
                          {groups.get(typeUri)!.map((sub, idx) => (
                            <React.Fragment key={`${sub}-${idx}`}>
                              <SubjectTreeNode subject={sub} level={0} ctx={treeCtx} />
                            </React.Fragment>
                          ))}
                        </div>
                      )}
                    </div>
                  ));
                })()
              )}
            </div>
          </div>
          <div className="m-3 p-1 bg-white/5 border border-white/5 rounded-full flex-shrink-0 flex gap-1 items-center shadow-sm mt-auto">
            <button type="button" onClick={expandAll}
              className="flex-1 text-[10px] px-3 py-1.5 uppercase font-semibold tracking-wider text-neutral-400 hover:text-white hover:bg-white/10 transition-all duration-300 rounded-full">Tout déplier</button>
            <button type="button" onClick={collapseAll}
              className="flex-1 text-[10px] px-3 py-1.5 uppercase font-semibold tracking-wider text-neutral-400 hover:text-white hover:bg-white/10 transition-all duration-300 rounded-full">Tout replier</button>
          </div>
        </div>
      }
      mainContent={
        <div className="h-full flex flex-col">
          {creatingNew && editMode ? (
            <div className="flex-1 overflow-y-auto p-4">
              <NewEntityForm
                getShortUri={getShortUri}
                onCancel={onCancelCreate}
                onCreate={(uri) => {
                  handleCreateNew();
                  // We can auto-select the new node here, wait for handleCreateNew to finish maybe?
                  // Currently handleCreateNew is in AgnosticTripleTree.tsx
                }}
              />
            </div>
          ) : selectedNode ? (
            <div className="flex-1 overflow-y-auto p-4">
              {/* En-tête du nœud centralisé ici, ou géré dans NodeEditPanel ?
                  Nous allons déléguer l'affichage complet à NodeEditPanel pour avoir un design cohérent. */}
              <NodeEditPanel
                node={selectedNode}
                subjectsMap={subjectsMap}
                predicates={availablePredicates}
                knownTypeUris={knownTypeUris}
                getShortUri={getShortUri}
                editMode={editMode}
                onAddTriple={(p, v, lit) => handleAddProperty(selectedNode, p, v, lit)}
                onDeleteTriple={(p, v, lit) => handleDeleteTriple(selectedNode, p, v, lit)}
                onDeleteEntity={() => handleDeleteEntity(selectedNode)}
                onRefresh={onRefresh}
                onCreateEntity={handleCreateEntity}
                creationStack={creationStack}
                onBackFromStack={handleBackFromStack}
                onNavigate={(uri) => handleSelectNode(uri)}
                triples={triples}
                allProperties={architecture?.properties || []}
              />
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-neutral-600 text-sm border border-white/10 bg-[#0a0a0a]/80 backdrop-blur-2xl rounded-[2rem] shadow-2xl ring-1 ring-white/5">
              Sélectionnez un élément dans l'arborescence pour voir ses détails.
            </div>
          )}
        </div>
      }
    />
  );
}
