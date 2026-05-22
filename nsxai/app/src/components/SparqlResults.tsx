import React, { useState } from 'react';
import { Table, Code, Share2 } from 'lucide-react';
import { SparqlGraphViewer } from './SparqlGraphViewer';

export default function SparqlResults({ results }: { results: any }) {
  const [viewMode, setViewMode] = useState<'table' | 'json' | 'graph'>('table');

  const getOrigin = (uri: string) => {
    if (!uri) return null;
    const match = uri.match(/\/ontologies\/([^#]+)#/);
    if (match) {
        const parts = match[1].split('/');
        return parts[parts.length - 1];
    }
    return null;
  };

  if (!results) return null;

  if (results.error) {
    return (
      <div className="mt-4 bg-red-500/10 p-4 rounded-md border border-red-500/30">
        <p className="text-red-400 font-mono text-xs">{results.error}</p>
      </div>
    );
  }

  const isBindings = results?.head?.vars && results?.results?.bindings;
  const isBoolean = typeof results?.boolean === 'boolean';

  return (
    <div className="mt-8 border border-neutral-800/70 rounded-2xl overflow-hidden bg-neutral-900/30">
      <div className="bg-transparent px-6 py-4 border-b border-neutral-800/70 flex items-center justify-between">
        <span className="text-sm font-medium text-neutral-300">Résultats</span>
        <div className="flex bg-neutral-900/50 p-1 rounded-lg border border-neutral-800/50">
          <button 
            onClick={() => setViewMode('table')}
            className={`px-4 py-1.5 text-xs font-medium rounded-md flex items-center gap-2 transition-colors ${viewMode === 'table' ? 'bg-neutral-800 text-neutral-100' : 'text-neutral-500 hover:text-neutral-300 hover:bg-neutral-800/50'}`}
          >
             <Table className="w-3.5 h-3.5" /> Table
          </button>
          {isBindings && (
             <button 
                onClick={() => setViewMode('graph')}
                className={`px-4 py-1.5 text-xs font-medium rounded-md flex items-center gap-2 transition-colors ${viewMode === 'graph' ? 'bg-neutral-800 text-neutral-100' : 'text-neutral-500 hover:text-neutral-300 hover:bg-neutral-800/50'}`}
             >
                <Share2 className="w-3.5 h-3.5" /> Graphe
             </button>
          )}
          <button 
             onClick={() => setViewMode('json')}
            className={`px-4 py-1.5 text-xs font-medium rounded-md flex items-center gap-2 transition-colors ${viewMode === 'json' ? 'bg-neutral-800 text-neutral-100' : 'text-neutral-500 hover:text-neutral-300 hover:bg-neutral-800/50'}`}
          >
             <Code className="w-3.5 h-3.5" /> JSON
          </button>
        </div>
      </div>

      <div className="max-h-[600px] overflow-auto custom-scrollbar">
        {viewMode === 'json' ? (
           <div className="p-6">
             <pre className="text-xs font-mono text-neutral-400 bg-neutral-950 p-6 rounded-xl border border-neutral-800/50">
               {JSON.stringify(results, null, 2)}
             </pre>
           </div>
        ) : viewMode === 'graph' ? (
          <div className="w-full flex-1">
            <SparqlGraphViewer data={results} />
          </div>
        ) : (
          <div>
            {isBoolean ? (
              <div className="text-lg font-mono font-medium text-center py-16">
                 {results.boolean ? <span className="text-neutral-300">Vrai</span> : <span className="text-neutral-500">Faux</span>}
              </div>
            ) : isBindings ? (
               <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-neutral-900/50 border-b border-neutral-800/70 text-neutral-500 font-medium text-xs tracking-wider uppercase">
                    <tr>
                      {results.head.vars.map((v: string) => (
                        <th key={v} className="px-6 py-4">?{v}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-800/50">
                     {results.results.bindings.length === 0 ? (
                        <tr>
                          <td colSpan={results.head.vars.length} className="px-6 py-8 text-center text-neutral-500 italic">Aucun résultat pour cette requête</td>
                        </tr>
                     ) : (
                        results.results.bindings.map((row: any, i: number) => (
                          <tr key={i} className="hover:bg-neutral-800/20 transition-colors">
                            {results.head.vars.map((v: string) => {
                              const cell = row[v];
                              if (!cell) return <td key={v} className="px-6 py-4 text-neutral-600">-</td>;
                              
                              if (cell.type === 'uri') {
                                const origin = getOrigin(cell.value);
                                return (
                                  <td key={v} className="px-6 py-4">
                                     <a href={cell.value} target="_blank" className="text-neutral-300 hover:text-white transition-colors font-mono text-xs max-w-[300px] truncate block" title={cell.value}>
                                       {cell.value.split(/[/#]/).pop()}
                                     </a>
                                     {origin && <span className="text-[10px] font-mono text-neutral-500 mt-1.5 inline-block border-b border-neutral-800" title="Fichier source">{origin}</span>}
                                  </td>
                                );
                              } else if (cell.type === 'BlankNode' || cell.type === 'bnode') {
                                return (
                                  <td key={v} className="px-6 py-4">
                                     <span className="text-neutral-500 font-mono text-xs cursor-help" title="Blank Node (Noeud Anonyme)">
                                       _:{cell.value.substring(0, 8)}...
                                     </span>
                                  </td>
                                );
                              } else {
                                return (
                                  <td key={v} className="px-6 py-4 font-mono text-xs max-w-sm truncate">
                                     <span className="text-neutral-400">"{cell.value}"</span>
                                     {cell.datatype && <span className="text-neutral-600 text-[10px] ml-2" title={cell.datatype.split(/[/#]/).pop()}>^^{cell.datatype.split(/[/#]/).pop()?.substring(0,8)}</span>}
                                     {cell.language && <span className="text-neutral-600 text-[10px] ml-2">@{cell.language}</span>}
                                  </td>
                                );
                              }
                            })}
                          </tr>
                        ))
                     )}
                  </tbody>
               </table>
            ) : (
              <div className="p-6">
                <pre className="text-xs font-mono text-neutral-400 bg-neutral-950 p-6 rounded-xl border border-neutral-800/50">
                  {JSON.stringify(results, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
