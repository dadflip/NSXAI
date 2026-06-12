import React, { useState, useEffect } from 'react';
import { Network, Search, Layers, Box, Link as LinkIcon, Circle, Loader2, Maximize2, Minimize2, ArrowLeft, ArrowRight, RotateCcw, BrainCircuit, CheckCircle, Brain, Target, Library, Database } from 'lucide-react';
import { fetchEntityDetails, fetchLocalGraph, fetchAllEntities, executeQuery } from '../lib/sparqlQueries';
import { fetchApi } from '../lib/apiClient';
import { LocalGraph } from './LocalGraph';
import { AgnosticTree } from './AgnosticTree';

// --- Main Explorer Component ---
export const OntologyExplorer: React.FC = () => {
  const [selectedUri, setSelectedUri] = useState<string | null>(null);
  const [expandedPanel, setExpandedPanel] = useState<'none' | 'tree' | 'wiki' | 'graph'>('none');
  const [isProcessing, setIsProcessing] = useState(false);

  // Navigation History
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const [inferenceMode, setInferenceMode] = useState(false);

  const navigateTo = (uri: string) => {
    if (uri === selectedUri) return;
    
    // Si on navigue alors qu'on est revenu en arrière, on tronque le futur
    const newHistory = history.slice(0, historyIndex + 1);
    newHistory.push(uri);
    
    setHistory(newHistory);
    setHistoryIndex(newHistory.length - 1);
    setSelectedUri(uri);
  };

  const goBack = () => {
    if (historyIndex > 0) {
      const prevIndex = historyIndex - 1;
      setHistoryIndex(prevIndex);
      setSelectedUri(history[prevIndex]);
    }
  };

  const goForward = () => {
    if (historyIndex < history.length - 1) {
      const nextIndex = historyIndex + 1;
      setHistoryIndex(nextIndex);
      setSelectedUri(history[nextIndex]);
    }
  };

  const handleReset = async () => {
    if (!confirm("Warning! This will clear the current graph and reload the original ontology. Continue?")) return;
    setIsProcessing(true);
    try {
      await fetchApi('reset', { method: 'POST' });
      await fetchAllEntities(true); // force refresh
      setSelectedUri(null);
      setHistory([]);
      setHistoryIndex(-1);
    } catch (e) {
      console.error(e);
      alert("Error during reset.");
    } finally {
      setIsProcessing(false);
    }
  };

  // Wiki state
  const [details, setDetails] = useState<any[]>([]);
  const [loadingDetails, setLoadingDetails] = useState(false);

  // Recommendations state
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [loadingRecs, setLoadingRecs] = useState(false);
  const [validating, setValidating] = useState<Set<number>>(new Set());

  // Graph state
  const [graphEdges, setGraphEdges] = useState<any[]>([]);
  const [graphDepth, setGraphDepth] = useState<number>(1);
  const [loadingGraph, setLoadingGraph] = useState(false);

  useEffect(() => {
    if (!selectedUri) return;

    setLoadingDetails(true);
    setLoadingRecs(true);
    
    const topic = selectedUri.split(/[/#]/).pop() || '';
    const endpoint = 'predict_new';

    fetchEntityDetails(selectedUri).then(async (d) => {
      setDetails(d);
      
      // Build node context by capturing all properties
      const nodeContext: Record<string, string> = {};
      d.forEach((x: any) => {
        const key = x.predicate.split(/[/#]/).pop();
        const value = x.isLiteral ? x.object : x.object.split(/[/#]/).pop();
        if (key && value) {
          if (key === 'type' || x.predicate === 'a' || x.predicate.includes('rdf-syntax-ns#type')) {
            nodeContext['type'] = value;
          } else {
            nodeContext[key] = value;
          }
        }
      });

      // Toujours utiliser predict_new (avec contexte) pour tous les nœuds
      try {
        const bodyNew = { node_name: topic, node_context: nodeContext, top_k: 5 };
        const rNew = await fetchApi('predict_new', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(bodyNew)
        });
        const dataNew = await rNew.json();
        setRecommendations(Array.isArray(dataNew) ? dataNew : []);
      } catch (err) {
        console.error("Inference error:", err);
        setRecommendations([{ error: "Error during inference." }]);
      }
    }).catch(console.error).finally(() => {
      setLoadingDetails(false);
      setLoadingRecs(false);
    });
  }, [selectedUri, inferenceMode]);

  const handleValidateRecommendation = async (rec: any, index: number) => {
    if (!selectedUri) return;
    try {
      setValidating(prev => new Set(prev).add(index));
      const predicateUri = rec.key_relation.startsWith('http') ? rec.key_relation : `http://nsxai.org/ontology#${rec.key_relation}`;
      const targetUri = rec.target.startsWith('http') ? rec.target : `http://nsxai.org/data/${rec.target}`;
      
      const insertQuery = `
        INSERT DATA {
          <${selectedUri}> <${predicateUri}> <${targetUri}> .
        }
      `;
      const res = await executeQuery(insertQuery);
      if (res.update) {
         fetchLocalGraph(selectedUri, graphDepth).then(setGraphEdges);
         fetchEntityDetails(selectedUri).then(setDetails);
         
         // Remove recommendation visually (or mark as validated)
         setRecommendations(prev => prev.filter((_, i) => i !== index));
      }
    } catch (e) {
      console.error(e);
      alert("Error during insertion");
    } finally {
      setValidating(prev => {
        const next = new Set(prev);
        next.delete(index);
        return next;
      });
    }
  };

  useEffect(() => {
    if (!selectedUri) return;

    setLoadingGraph(true);
    fetchLocalGraph(selectedUri, graphDepth)
      .then(edges => setGraphEdges(edges))
      .catch(console.error)
      .finally(() => setLoadingGraph(false));
  }, [selectedUri, graphDepth]);

  const toggleExpand = (panel: 'tree' | 'wiki' | 'graph') => {
    setExpandedPanel(prev => prev === panel ? 'none' : panel);
  };

  return (
    <div className="h-full flex gap-2">
      
      {/* LEFT PANEL: Tree */}
      <div className={`flex flex-col bg-slate-50 border border-slate-300 ${expandedPanel === 'tree' ? 'w-full' : expandedPanel === 'none' ? 'w-1/3' : 'hidden'}`}>
        <div className="p-2 border-b border-slate-300 flex flex-col gap-2 bg-slate-200">
          <div className="flex justify-between items-center">
            <h2 className="font-bold text-slate-800 flex items-center gap-2 text-sm tracking-tight">
              <Database className="w-4 h-4 text-slate-700" />
              Knowledge Base
            </h2>
            <div className="flex gap-1">
              <button onClick={handleReset} disabled={isProcessing} className="p-1.5 rounded-sm text-slate-600 hover:text-red-600 hover:bg-slate-300 transition-colors disabled:opacity-50" title="Reset Ontology">
                <RotateCcw className="w-4 h-4" />
              </button>
              <button onClick={() => toggleExpand('tree')} className="p-1.5 rounded-sm text-slate-600 hover:text-slate-900 hover:bg-slate-300 transition-colors">
                {expandedPanel === 'tree' ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-slate-600 font-medium">
          </div>
        </div>
        <div className="flex-1 min-h-0 overflow-hidden relative">
          {isProcessing && (
            <div className="absolute inset-0 z-10 bg-white/50 flex items-center justify-center">
              <Loader2 className="w-6 h-6 text-slate-600 animate-spin" />
            </div>
          )}
          <AgnosticTree onSelect={navigateTo} selectedUri={selectedUri} />
        </div>
      </div>

      {/* RIGHT AREA: Wiki & Graph */}
      <div className={`flex flex-col gap-2 min-h-0 ${expandedPanel === 'none' ? 'w-2/3' : expandedPanel === 'tree' ? 'hidden' : 'w-full'}`}>
        
        {/* WIKI PANEL */}
        <div className={`bg-slate-50 border border-slate-300 flex flex-col overflow-hidden ${expandedPanel === 'wiki' ? 'flex-1' : expandedPanel === 'graph' ? 'hidden' : 'flex-1'}`}>
          <div className="p-2 border-b border-slate-300 flex items-center justify-between bg-slate-200">
            <h2 className="font-bold text-slate-800 flex items-center gap-2 text-sm tracking-tight">
              Entity Details
            </h2>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 mr-2">
                <button 
                  onClick={goBack} 
                  disabled={historyIndex <= 0}
                  className="p-1.5 rounded-sm text-slate-600 hover:text-slate-900 hover:bg-slate-300 transition-colors disabled:opacity-30"
                  title="Previous"
                >
                  <ArrowLeft className="w-4 h-4" />
                </button>
                <button 
                  onClick={goForward} 
                  disabled={historyIndex >= history.length - 1}
                  className="p-1.5 rounded-sm text-slate-600 hover:text-slate-900 hover:bg-slate-300 transition-colors disabled:opacity-30"
                  title="Next"
                >
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
              {selectedUri && <span className="text-xs text-slate-700 font-mono bg-white px-2 py-0.5 border border-slate-300 rounded-sm truncate max-w-[200px]" title={selectedUri}>{selectedUri.split(/[/#]/).pop()}</span>}
              <button onClick={() => toggleExpand('wiki')} className="p-1.5 rounded-sm text-slate-600 hover:text-slate-900 hover:bg-slate-300 transition-colors">
                {expandedPanel === 'wiki' ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {!selectedUri ? (
              <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                Select an entity in the tree to view its details
              </div>
            ) : loadingDetails ? (
              <div className="h-full flex items-center justify-center text-slate-400">
                <Loader2 className="w-6 h-6 animate-spin" />
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {details.map((d, i) => (
                  <div key={i} className="p-2 bg-white border border-slate-300 hover:bg-slate-50 break-words group relative">
                    <div className="text-xs font-bold text-slate-600 mb-1 flex justify-between">
                      <span className="truncate pr-2" title={d.predicate}>{d.predicate.split(/[/#]/).pop()}</span>
                    </div>
                    {d.isLiteral ? (
                      <div className="text-sm text-slate-800 font-mono">"{d.object}"</div>
                    ) : (
                      <div className="text-sm text-blue-600 cursor-pointer hover:underline font-mono" onClick={() => navigateTo(d.object)}>
                        {d.object.split(/[/#]/).pop()}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {recommendations.length > 0 && (
                <div className="mt-4 border-t border-slate-300 pt-4">
                  <h3 className="font-bold text-slate-800 flex items-center gap-2 mb-4 text-sm">
                    Gamification Recommendations {recommendations.length > 0 && !recommendations[0].error && `(${recommendations.length})`}
                  </h3>
                  <div className="space-y-2">
                    {recommendations.map((rec, idx) => (
                      <div key={idx} className="bg-white border border-slate-300 rounded-sm">
                        <div className="p-3">
                          {rec.error ? (
                            <div className="text-red-700 text-sm bg-red-50 p-2 border border-red-200">
                              {rec.error}
                            </div>
                          ) : (
                            <>
                              <div className="flex items-start justify-between">
                                <div>
                                  <div className="flex items-center gap-2 mb-1">
                                    <span className="px-1.5 py-0.5 bg-slate-100 text-slate-700 text-xs font-bold border border-slate-300">
                                      {rec.key_relation}
                                    </span>
                                    <span className="text-slate-500 text-xs">→</span>
                                    <span className="text-slate-900 font-bold text-base">
                                      {rec.target?.split(/[/#]/).pop() || 'Unknown Target'}
                                    </span>
                                  </div>
                                </div>
                                <div className="flex flex-col items-end gap-1 text-xs">
                                  <span className="text-slate-600 font-mono">
                                    NS Score: {((rec.neurosymbolic_score || 0) * 100).toFixed(1)}%
                                  </span>
                                </div>
                              </div>

                              {rec.explanation_blocks && (
                                <div className="space-y-2 mt-3 text-sm text-slate-700 bg-slate-50 p-2 border border-slate-200">
                                  {rec.explanation_blocks.strength && (
                                    <p className="flex items-start gap-2">
                                      <Brain className="w-4 h-4 text-slate-500 mt-0.5 shrink-0" />
                                      <span>{String(rec.explanation_blocks.strength).replace(/\(rev\)/g, '← ')}</span>
                                    </p>
                                  )}
                                  
                                  {rec.explanation_blocks.target && (
                                    <p className="flex items-start gap-2">
                                      <span>{String(rec.explanation_blocks.target).replace(/\(rev\)/g, '← ')}</span>
                                    </p>
                                  )}
                                  
                                  {rec.explanation_blocks.ontology && (
                                    <p className="flex items-start gap-2">
                                      <span>{String(rec.explanation_blocks.ontology).replace(/\(rev\)/gi, '← ')}</span>
                                    </p>
                                  )}
                                  
                                  {Object.entries(rec.explanation_blocks).map(([key, text]) => {
                                    if (['strength', 'ontology', 'path', 'target'].includes(key)) return null;
                                    
                                    if (key === 'context') {
                                      return (
                                        <div key={key} className="mt-2 p-2 bg-blue-50 border border-blue-200 text-blue-900">
                                          <p className="flex items-start gap-2">
                                            <BrainCircuit className="w-4 h-4 text-blue-600 mt-0.5 shrink-0" />
                                            <span className="text-xs">
                                              <span className="font-bold uppercase block mb-0.5">Neural Pivot Reasoning</span>
                                              <span>{String(text).replace(/\(rev\)/gi, '← ')}</span>
                                            </span>
                                          </p>
                                        </div>
                                      );
                                    }
                                    
                                    if (key === 'pivot_reasoning') {
                                      return (
                                        <div key={key} className="mt-2 p-2 bg-indigo-50 border border-indigo-200 text-indigo-900">
                                          <p className="flex items-start gap-2">
                                            <Brain className="w-4 h-4 text-indigo-600 mt-0.5 shrink-0" />
                                            <span className="text-xs">
                                              <span className="font-bold uppercase block mb-0.5">Symbolic Pivot Selection</span>
                                              <span>{String(text).replace(/\(rev\)/gi, '← ')}</span>
                                            </span>
                                          </p>
                                        </div>
                                      );
                                    }
                                    
                                    if (key === 'numeric_boost') {
                                      return (
                                        <div key={key} className="mt-1 p-2 bg-green-50 border border-green-200 text-green-900">
                                          <p className="flex items-start gap-2">
                                            <span className="text-xs">
                                              <span className="font-bold uppercase block mb-0.5">Target Attractiveness</span>
                                              <span>{String(text).replace(/\(rev\)/gi, '← ')}</span>
                                            </span>
                                          </p>
                                        </div>
                                      );
                                    }

                                    return (
                                      <p key={key} className="flex items-start gap-2 mt-1">
                                        <span><span className="font-bold capitalize text-slate-600">{key}: </span>{String(text).replace(/\(rev\)/gi, '← ')}</span>
                                      </p>
                                    );
                                  })}
                                </div>
                              )}

                              {rec.ontology_path && rec.ontology_path !== 'no path found' && (
                                <div className="mt-3 pt-3 border-t border-slate-200">
                                  <span className="text-xs text-slate-500 font-bold uppercase mb-2 block">Ontological Path</span>
                                  <div className="flex flex-wrap items-center gap-1">
                                    {rec.ontology_path.split(/--(.+?)-->/).map((part: string, i: number) => {
                                      if (i % 2 === 0) {
                                        return (
                                          <div key={i} className="px-1.5 py-0.5 bg-slate-100 border border-slate-300 text-slate-800 text-xs font-mono">
                                            {part.trim()}
                                          </div>
                                        );
                                      } else {
                                        const isRev = part.includes('(rev)');
                                        const cleanPart = part.replace('(rev)', '').trim();
                                        return (
                                          <div key={i} className="flex items-center gap-1 text-slate-500 text-[10px] font-bold uppercase">
                                            {isRev ? <ArrowLeft className="w-3 h-3" /> : <ArrowRight className="w-3 h-3" />}
                                            {cleanPart}
                                            {isRev ? <ArrowLeft className="w-3 h-3" /> : <ArrowRight className="w-3 h-3" />}
                                          </div>
                                        );
                                      }
                                    })}
                                  </div>
                                </div>
                              )}

                              <div className="mt-3 pt-3 border-t border-slate-200 flex gap-4 text-xs text-slate-600 items-center justify-between">
                                <div className="flex gap-4">
                                  <span className="flex items-center gap-1">
                                    Confidence:
                                    <span className="font-bold text-slate-800">{rec.confidence_label}</span>
                                  </span>
                                  <span className="flex items-center gap-1">
                                    Neural:
                                    <span className="font-bold text-slate-800">{((rec.probability_mean || 0) * 100).toFixed(1)}%</span>
                                  </span>
                                </div>
                                <button
                                  onClick={() => handleValidateRecommendation(rec, idx)}
                                  disabled={validating.has(idx)}
                                  className="px-3 py-1 bg-white border border-slate-300 text-slate-800 hover:bg-slate-50 text-xs font-bold flex items-center gap-1 disabled:opacity-50"
                                >
                                  {validating.has(idx) ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
                                  Validate & Add
                                </button>
                              </div>
                            </>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              </>
            )}
          </div>
        </div>

        {/* GRAPH PANEL */}
        <div className={`bg-white border border-slate-300 flex flex-col overflow-hidden ${expandedPanel === 'graph' ? 'flex-1' : expandedPanel === 'wiki' ? 'hidden' : 'flex-1'}`}>
          <div className="p-2 border-b border-slate-300 flex items-center justify-between bg-slate-50">
            <h2 className="font-bold text-slate-800 flex items-center gap-2 text-sm">
              <Network className="w-4 h-4 text-slate-600" />
              Local Graph
            </h2>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-1 cursor-pointer text-xs text-slate-700">
                <input 
                  type="checkbox" 
                  checked={inferenceMode} 
                  onChange={e => setInferenceMode(e.target.checked)}
                  className="w-3 h-3 border-slate-300"
                />
                <BrainCircuit className="w-3 h-3 text-slate-500" />
                Inference Mode
              </label>
              <div className="flex items-center gap-1 bg-white border border-slate-300 p-0.5">
                <span className="text-xs text-slate-600 px-1">Depth</span>
                <select 
                  value={graphDepth} 
                  onChange={e => setGraphDepth(Number(e.target.value))}
                  className="bg-transparent text-xs text-slate-800 outline-none cursor-pointer"
                >
                  <option value={1}>1</option>
                  <option value={2}>2</option>
                  <option value={3}>3</option>
                  <option value={4}>4</option>
                  <option value={5}>5</option>
                  <option value={6}>6</option>
                  <option value={7}>7</option>
                  <option value={8}>8</option>
                  <option value={9}>9</option>
                  <option value={10}>10</option>
                </select>
              </div>
              <button onClick={() => toggleExpand('graph')} className="text-slate-600 hover:bg-slate-200 p-1 rounded-sm">
                {expandedPanel === 'graph' ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <div className="flex-1 relative bg-white">
            {!selectedUri ? (
              <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm font-medium">
                Select an entity to visualize its relations
              </div>
            ) : loadingGraph ? (
              <div className="absolute inset-0 flex items-center justify-center text-slate-400">
                <Loader2 className="w-6 h-6 animate-spin" />
              </div>
            ) : (
              <LocalGraph edges={graphEdges} centerUri={selectedUri} recommendations={recommendations} inferenceMode={inferenceMode} />
            )}
          </div>
        </div>

      </div>
    </div>
  );
};
