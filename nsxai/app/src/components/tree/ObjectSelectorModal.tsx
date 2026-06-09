import React, { useState, useEffect, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { X, Loader2, Plus, ChevronRight } from 'lucide-react';
import { type PredicateSuggestion, isLiteralRange, getShortUri as shortLocal, NS, type Triple, getPrimaryTypeUris } from '../../lib/core';
import { fetchApi } from '../../lib/apiClient';
import { CascadeForm } from './CascadeForm';
import { SubjectTreeNode, type TreeNodeContext } from '../TripletTreeShared';

export interface CandidateObj {
  uri: string; label?: string;
  kind: 'instance' | 'literal' | 'iri' | 'new_instance' | 'new_uri';
  classUri?: string; datatype?: string;
}

export interface ObjectSelectorModalProps {
  isOpen: boolean;
  onClose: () => void;
  predicate: PredicateSuggestion;
  subject: string;
  baseUri: string;
  onSelect: (value: string, isLiteral: boolean) => void;
  onCreateEntity?: (classUri: string) => void;
  triples: Triple[];
  subjectsMap: Map<string, Triple[]>;
}

export function ObjectSelectorModal({ isOpen, onClose, predicate, subject, baseUri, onSelect, onCreateEntity, triples, subjectsMap }: ObjectSelectorModalProps) {
  const [candidates, setCandidates] = useState<CandidateObj[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedValue, setSelectedValue] = useState('');
  const [freeInput, setFreeInput] = useState('');
  const [showCascade, setShowCascade] = useState(false);
  const [cascadeClassUri, setCascadeClassUri] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set());
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

  const treeCtx: TreeNodeContext = useMemo(() => ({
    subjectsMap,
    getShortUri: shortLocal,
    maxDepth: 5,
    expanded: expandedNodes,
    onToggle: (id) => setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    }),
    onSelectNode: (id) => setSelectedValue(id),
    searchQuery,
  }), [subjectsMap, expandedNodes, searchQuery]);

  const RDF_NS = NS.RDF;

  useEffect(() => {
    if (!isOpen || !predicate) return;
    const isLiteral = isLiteralRange(predicate.range);
    if (isLiteral) {
      setCandidates([]);
      return;
    }
    setLoading(true);
    const rangeParam = predicate.range ? `&range_uri=${encodeURIComponent(predicate.range)}` : '';
    fetchApi(`objects?subject_uri=${encodeURIComponent(subject)}&predicate_uri=${encodeURIComponent(predicate.uri)}${rangeParam}`)
      .then(r => r.ok ? r.json() : { candidates: [] })
      .then(data => setCandidates(data.candidates ?? []))
      .catch(() => setCandidates([]))
      .finally(() => setLoading(false));
  }, [isOpen, predicate, subject]);

  const isLiteral = isLiteralRange(predicate?.range);
  const instanceCandidates = candidates.filter(c => c.kind === 'instance');
  const newInstanceCandidate = candidates.find(c => c.kind === 'new_instance');
  
  const filteredCandidates = useMemo(() => {
    const map = new Map<string, CandidateObj>();
    
    // Add API candidates
    for (const c of instanceCandidates) {
      map.set(c.uri, c);
    }
    
    // Add local subjects from the graph
    const localSubjects = Array.from(subjectsMap.keys());
    for (const sub of localSubjects) {
      if (!map.has(sub)) {
        // Enforce range if it's not generic Resource/Thing
        if (predicate.range && predicate.range !== `${NS.RDFS}Resource` && predicate.range !== `${NS.OWL}Thing`) {
          const types = getPrimaryTypeUris(subjectsMap.get(sub) || []);
          if (!types.includes(predicate.range)) continue;
        }
        
        map.set(sub, {
          uri: sub,
          kind: 'instance',
          label: subjectsMap.get(sub)?.find(t => t.predicate === NS.RDFS + 'label')?.object || shortLocal(sub)
        });
      }
    }
    
    let result = Array.from(map.values());
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter(c => {
        const lbl = (c.label || '').toLowerCase();
        const uri = shortLocal(c.uri).toLowerCase();
        return lbl.includes(q) || uri.includes(q);
      });
    }
    return result;
  }, [instanceCandidates, subjectsMap, predicate, searchQuery]);

  const toggleType = (typeUri: string) => {
    setExpandedTypes((prev) => {
      const n = new Set(prev);
      if (n.has(typeUri)) n.delete(typeUri);
      else n.add(typeUri);
      return n;
    });
  };

  const groupedCandidates = useMemo(() => {
    const groups = new Map<string, CandidateObj[]>();
    for (const c of filteredCandidates) {
      const types = getPrimaryTypeUris(subjectsMap.get(c.uri) || []);
      if (types.length === 0) {
        if (!groups.has('Sans type')) groups.set('Sans type', []);
        groups.get('Sans type')!.push(c);
      } else {
        for (const typeUri of types) {
          if (!groups.has(typeUri)) groups.set(typeUri, []);
          groups.get(typeUri)!.push(c);
        }
      }
    }
    return groups;
  }, [filteredCandidates, subjectsMap]);

  const sortedGroupKeys = useMemo(() => {
    return Array.from(groupedCandidates.keys()).sort((a, b) => shortLocal(a).localeCompare(shortLocal(b)));
  }, [groupedCandidates]);

  const handleSubmit = () => {
    const val = isLiteral ? freeInput.trim() : (selectedValue || freeInput.trim());
    if (!val) return;
    onSelect(val, isLiteral);
    handleClose();
  };

  const handleCascadeConfirm = async (newUri: string, newLabel: string) => {
    try {
      await fetchApi('create', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'individual', uri: newUri, label: newLabel,
          additionalTriples: cascadeClassUri ? [{ p: `${RDF_NS}type`, o: cascadeClassUri, isLiteral: false }] : [],
        }),
      });
    } catch (e) { console.error(e); }
    onSelect(newUri, false);
    handleClose();
  };

  const handleClose = () => {
    setSelectedValue('');
    setFreeInput('');
    setShowCascade(false);
    setCascadeClassUri('');
    setSearchQuery('');
    onClose();
  };

  if (!isOpen || !predicate) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-neutral-900 border border-neutral-700 rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-800 shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-neutral-200">
              {predicate.label || shortLocal(predicate.uri)}
            </span>
            {predicate.range && (
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${isLiteral ? 'bg-amber-900/30 text-amber-400' : 'bg-blue-900/30 text-blue-400'}`}>
                → {shortLocal(predicate.range)}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="text-neutral-500 hover:text-neutral-200 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1 custom-scrollbar">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-neutral-600" />
            </div>
          ) : showCascade ? (
            <CascadeForm
              classUri={cascadeClassUri}
              baseUri={baseUri}
              onConfirm={handleCascadeConfirm}
              onCancel={() => setShowCascade(false)}
            />
          ) : isLiteral ? (
            <div>
              <label className="block text-[10px] uppercase tracking-widest text-neutral-500 mb-2">Valeur</label>
              <input
                autoFocus
                type="text"
                value={freeInput}
                onChange={e => setFreeInput(e.target.value)}
                placeholder="Entrez une valeur..."
                className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-3 text-sm text-neutral-100 placeholder:text-neutral-600 focus:outline-none focus:border-neutral-600 transition-colors"
                onKeyDown={e => {
                  if (e.key === 'Enter') handleSubmit();
                  if (e.key === 'Escape') handleClose();
                }}
              />
            </div>
          ) : (
            <div className="space-y-4">
              {/* Search */}
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-neutral-500 mb-2">Rechercher</label>
                <input
                  autoFocus
                  type="text"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  placeholder="Rechercher une instance..."
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-2.5 text-sm text-neutral-100 placeholder:text-neutral-600 focus:outline-none focus:border-neutral-600 transition-colors"
                />
              </div>

              {/* Instance list (Hierarchical) */}
              {filteredCandidates.length > 0 && (
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-neutral-500 mb-2">
                    Instances existantes ({filteredCandidates.length})
                  </label>
                  <div className="bg-neutral-950 border border-neutral-800 rounded-lg overflow-hidden">
                    <div className="max-h-64 overflow-y-auto custom-scrollbar p-2">
                      {sortedGroupKeys.map(typeUri => (
                        <div key={typeUri} className="mb-2">
                          <div 
                            className="flex items-center gap-2 py-1.5 px-2 mb-1 cursor-pointer hover:bg-neutral-800/50 rounded transition-colors group"
                            onClick={() => toggleType(typeUri)}
                          >
                            <ChevronRight className={`w-4 h-4 text-neutral-500 transition-transform ${expandedTypes.has(typeUri) ? 'rotate-90' : ''}`} />
                            <span className="text-xs uppercase tracking-widest font-semibold text-neutral-400 group-hover:text-neutral-200 transition-colors">
                              {shortLocal(typeUri)}
                            </span>
                            <span className="text-[10px] text-neutral-600">({groupedCandidates.get(typeUri)?.length})</span>
                          </div>
                          {expandedTypes.has(typeUri) && (
                            <div className="pl-6 space-y-1 mt-1">
                              {groupedCandidates.get(typeUri)!.map((c) => (
                                <div
                                  key={c.uri}
                                  className={`flex items-start gap-2 pl-2 pr-2 py-0.5 transition-colors rounded ${
                                    selectedValue === c.uri ? 'bg-blue-900/30 ring-1 ring-blue-500/50' : 'hover:bg-neutral-800/30'
                                  }`}
                                >
                                  <div className="pt-2 cursor-pointer shrink-0" onClick={() => setSelectedValue(c.uri)}>
                                    <input 
                                      type="radio" 
                                      name="object-selection"
                                      checked={selectedValue === c.uri} 
                                      onChange={() => setSelectedValue(c.uri)}
                                      className="cursor-pointer mt-0.5 accent-blue-500"
                                    />
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <SubjectTreeNode subject={c.uri} level={0} ctx={treeCtx} />
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Divider */}
              {filteredCandidates.length > 0 && newInstanceCandidate && (
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-px bg-neutral-800" />
                  <span className="text-[10px] text-neutral-600">ou</span>
                  <div className="flex-1 h-px bg-neutral-800" />
                </div>
              )}

              {/* Create new */}
              {newInstanceCandidate && (
                <button
                  type="button"
                  onClick={() => {
                    if (onCreateEntity) {
                      onCreateEntity(newInstanceCandidate.classUri ?? '');
                    } else {
                      setShowCascade(true);
                      setCascadeClassUri(newInstanceCandidate.classUri ?? '');
                      setSelectedValue('');
                    }
                  }}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-900/20 hover:bg-blue-900/30 border border-blue-800/50 rounded-lg text-blue-400 text-sm font-medium transition-colors"
                >
                  <Plus className="w-4 h-4" />
                  Créer un nouveau {shortLocal(newInstanceCandidate.classUri ?? '')}
                </button>
              )}

              {/* Manual URI input */}
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-neutral-500 mb-2">
                  {filteredCandidates.length > 0 ? 'Ou entrer une URI manuellement' : 'URI'}
                </label>
                <input
                  type="text"
                  value={freeInput}
                  onChange={e => setFreeInput(e.target.value)}
                  placeholder="http://..."
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-2.5 text-sm text-neutral-100 placeholder:text-neutral-600 focus:outline-none focus:border-neutral-600 transition-colors font-mono"
                  onKeyDown={e => {
                    if (e.key === 'Enter') handleSubmit();
                    if (e.key === 'Escape') handleClose();
                  }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        {!showCascade && (
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-neutral-800 bg-neutral-900/50 shrink-0">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 text-sm text-neutral-400 hover:text-neutral-200 transition-colors"
            >
              Annuler
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={isLiteral ? !freeInput.trim() : (!selectedValue && !freeInput.trim())}
              className="px-4 py-2 text-sm bg-neutral-800 hover:bg-neutral-700 text-neutral-200 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Ajouter
            </button>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
