import React, { useState, useEffect } from 'react';
import { GitBranch, Plus, Trash2, CheckCircle2, AlertCircle, Loader2, Save, Play, Edit3, X } from 'lucide-react';
import { apiUrl } from '../lib/api';

interface Rule {
  id: string;
  name: string;
  sparql: string;
}

export const RuleManager: React.FC = () => {
  const [rules, setRules] = useState<Rule[]>(() => {
    const saved = localStorage.getItem('nsxai_reasoner_rules');
    return saved ? JSON.parse(saved) : [];
  });
  
  const [loading, setLoading] = useState(false);
  const [editingRule, setEditingRule] = useState<Rule | null>(null);
  const [status, setStatus] = useState<{ type: 'success' | 'error', message: string } | null>(null);

  const [inferences, setInferences] = useState<string[]>([]);
  const [showInferences, setShowInferences] = useState(false);

  const syncRules = async (newRules: Rule[]) => {
    localStorage.setItem('nsxai_reasoner_rules', JSON.stringify(newRules));
    try {
      await fetch(apiUrl('/api/reasoner/rules/sync'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rules: newRules })
      });
    } catch (e) {
      console.error("Failed to sync rules:", e);
    }
  };

  const fetchInferences = async () => {
    try {
      const res = await fetch(apiUrl('/api/reasoner/inferences'));
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setInferences(data);
        }
      }
    } catch (e) {
      console.error("Error fetching inferences:", e);
    }
  };

  useEffect(() => {
    fetchInferences();
  }, []);

  const handleRunReasoner = async () => {
    setLoading(true);
    try {
      const res = await fetch(apiUrl('/api/reasoner/run'), { method: 'POST' });
      if (res.ok) {
        setStatus({ type: 'success', message: 'Reasoner run complete.' });
        fetchInferences();
      }
    } catch (e) {
      setStatus({ type: 'error', message: 'Failed to run reasoner.' });
    } finally {
      setLoading(false);
      setTimeout(() => setStatus(null), 3000);
    }
  };

  const handleSave = async (rule: Rule) => {
    setLoading(true);
    const existingIdx = rules.findIndex(r => r.id === rule.id);
    let newRules = [...rules];
    if (existingIdx >= 0) {
      newRules[existingIdx] = rule;
    } else {
      newRules.push(rule);
    }
    setRules(newRules);
    await syncRules(newRules);
    setStatus({ type: 'success', message: 'Rule updated.' });
    setEditingRule(null);
    handleRunReasoner();
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this inference rule?')) return;
    setLoading(true);
    const newRules = rules.filter(r => r.id !== id);
    setRules(newRules);
    await syncRules(newRules);
    setStatus({ type: 'success', message: 'Rule removed.' });
    setLoading(false);
    setTimeout(() => setStatus(null), 3000);
    handleRunReasoner();
  };

  const handleClearInferences = async () => {
    if (!confirm('Clear all inferred triples?')) return;
    setLoading(true);
    try {
      const res = await fetch(apiUrl('/api/reasoner/inferences'), { method: 'DELETE' });
      if (res.ok) {
        setInferences([]);
        setStatus({ type: 'success', message: 'Inferences cleared.' });
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
      setTimeout(() => setStatus(null), 3000);
    }
  };

  const handleDeleteInference = async (encodedTriple: string) => {
    try {
      const res = await fetch(apiUrl(`/api/reasoner/inferences/${encodeURIComponent(encodedTriple)}`), { method: 'DELETE' });
      if (res.ok) {
        setInferences(prev => prev.filter(t => t !== encodedTriple));
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="flex flex-col h-full bg-neutral-950 border-neutral-900 overflow-hidden">
      <div className="p-4 border-b border-neutral-900 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <GitBranch className="w-5 h-5 text-purple-500" />
          <h2 className="text-sm font-bold uppercase tracking-widest text-neutral-200">Inference Engine</h2>
        </div>
        <div className="flex gap-2">
          {inferences.length > 0 && (
            <button 
              onClick={handleClearInferences}
              className="p-1.5 hover:bg-red-900/10 rounded-lg text-neutral-600 hover:text-red-500 transition-colors"
              title="Clear all inferences"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
          <button 
            onClick={handleRunReasoner}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 bg-neutral-900 border border-neutral-800 rounded-lg text-[10px] font-bold text-neutral-400 hover:text-purple-400 hover:border-purple-900/50 transition-all active:scale-95 disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            RUN REASONER
          </button>
          <button 
            onClick={() => setEditingRule({ id: `rule_${Date.now()}`, name: 'New Rule', sparql: 'INSERT { ?s ?p ?o } WHERE { ?s ?p ?o }' })}
            className="flex items-center gap-2 px-3 py-1.5 bg-neutral-900 border border-neutral-800 rounded-lg text-[10px] font-bold text-neutral-400 hover:text-white hover:border-neutral-700 transition-all active:scale-95"
          >
            <Plus className="w-3.5 h-3.5" />
            NEW RULE
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
        {rules.length === 0 && !loading && (
          <div className="p-8 text-center text-xs text-neutral-600 border border-neutral-900 border-dashed rounded-2xl">
            No inference rules defined.
          </div>
        )}
        
        {rules.map(rule => (
          <div 
            key={rule.id}
            className="bg-neutral-950 border border-neutral-900 rounded-xl overflow-hidden hover:border-neutral-800 transition-all"
          >
            <div className="p-4 flex items-center justify-between border-b border-neutral-900 bg-neutral-900/10">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-neutral-900 flex items-center justify-center text-purple-500 font-mono text-xs border border-neutral-800">
                  {rule.id.substring(0, 2).toUpperCase()}
                </div>
                <div>
                  <div className="text-[11px] font-bold text-neutral-200">{rule.name}</div>
                  <div className="text-[9px] text-neutral-500 font-mono">{rule.id}</div>
                </div>
              </div>
              <div className="flex gap-2">
                <button 
                   onClick={() => setEditingRule(rule)}
                   className="p-1.5 hover:bg-neutral-900 rounded text-neutral-500 hover:text-neutral-200 transition-colors"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                </button>
                <button 
                  onClick={() => handleDelete(rule.id)}
                  className="p-1.5 hover:bg-neutral-900 rounded text-neutral-500 hover:text-red-500 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
            <div className="p-4">
              <pre className="text-[10px] text-neutral-500 font-mono bg-black/40 p-3 rounded-lg border border-neutral-900 overflow-x-auto whitespace-pre-wrap">
                {rule.sparql}
              </pre>
            </div>
          </div>
        ))}

        {inferences.length > 0 && (
          <div className="mt-8 space-y-3">
            <div 
              className="flex items-center justify-between p-3 bg-emerald-950/10 border border-emerald-900/30 rounded-xl cursor-pointer hover:bg-emerald-950/20 transition-colors"
              onClick={() => setShowInferences(!showInferences)}
            >
               <div className="flex items-center gap-3">
                 <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                 <span className="text-[10px] font-bold text-emerald-500 uppercase tracking-widest">Inferred Knowledge ({inferences.length} triples)</span>
               </div>
               <div className="text-emerald-500/50">
                 {showInferences ? <X className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
               </div>
            </div>
            
            {showInferences && (
              <div className="grid grid-cols-1 gap-1 max-h-96 overflow-y-auto pr-2 custom-scrollbar border border-neutral-900 rounded-xl p-2 bg-black/20">
                {inferences.map((inf, i) => {
                  const parts = inf.split('|');
                  return (
                    <div key={i} className="text-[10px] font-mono p-2 hover:bg-neutral-900 rounded border border-transparent hover:border-neutral-800 flex items-center gap-2 group">
                      <span className="text-neutral-500 shrink-0 w-4">{i+1}</span>
                      <span className="text-neutral-400 truncate max-w-[30%]" title={parts[0]}>{parts[0].split(/[/#]/).pop()}</span>
                      <span className="text-neutral-600 shrink-0">→</span>
                      <span className="text-purple-400/80 truncate max-w-[20%]" title={parts[1]}>{parts[1].split(/[/#]/).pop()}</span>
                      <span className="text-neutral-600 shrink-0">→</span>
                      <span className="text-emerald-400/80 truncate flex-1" title={parts[2]}>{parts[2].includes('http') ? parts[2].split(/[/#]/).pop() : parts[2]}</span>
                      <button 
                        onClick={(e) => { e.stopPropagation(); handleDeleteInference(inf); }}
                        className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-900/20 text-neutral-600 hover:text-red-500 rounded transition-all"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {editingRule && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-neutral-950 border border-neutral-800 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl">
            <div className="p-4 border-b border-neutral-900 flex items-center justify-between">
              <h3 className="text-sm font-bold text-neutral-200 flex items-center gap-2 uppercase tracking-widest">
                <Edit3 className="w-4 h-4 text-purple-500" />
                Edit Inference Rule
              </h3>
              <button 
                onClick={() => setEditingRule(null)}
                className="p-2 hover:bg-neutral-900 rounded-lg text-neutral-500"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-neutral-500 uppercase">Rule ID</label>
                  <input 
                    type="text" 
                    value={editingRule.id}
                    onChange={e => setEditingRule({...editingRule, id: e.target.value})}
                    className="w-full bg-neutral-900 border border-neutral-800 rounded-lg p-2.5 text-xs text-neutral-200 font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-neutral-500 uppercase">Rule Name</label>
                  <input 
                    type="text" 
                    value={editingRule.name}
                    onChange={e => setEditingRule({...editingRule, name: e.target.value})}
                    className="w-full bg-neutral-900 border border-neutral-800 rounded-lg p-2.5 text-xs text-neutral-200"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-[10px] font-bold text-neutral-500 uppercase">SPARQL UPDATE Rule</label>
                <textarea 
                  value={editingRule.sparql}
                  onChange={e => setEditingRule({...editingRule, sparql: e.target.value})}
                  rows={8}
                  className="w-full bg-neutral-900 border border-neutral-800 rounded-lg p-3 text-[11px] text-neutral-300 font-mono custom-scrollbar focus:border-purple-500/50 focus:ring-1 focus:ring-purple-500/20 transition-all outline-none"
                  placeholder="INSERT { ... } WHERE { ... }"
                />
              </div>
              <div className="p-4 bg-purple-900/10 rounded-xl border border-purple-900/20">
                <p className="text-[10px] text-purple-300/80 leading-relaxed">
                  <strong>Warning:</strong> These rules execute in a loop until fixed point or 10 iterations. Ensure your rules don't cause infinite growth of the graph.
                </p>
              </div>
            </div>
            <div className="p-4 bg-neutral-900/20 border-t border-neutral-900 flex justify-end gap-3">
              <button 
                onClick={() => setEditingRule(null)}
                className="px-4 py-2 text-xs font-bold text-neutral-500 hover:text-neutral-200 uppercase tracking-widest transition-colors"
              >
                Cancel
              </button>
              <button 
                onClick={() => handleSave(editingRule)}
                disabled={loading}
                className="flex items-center gap-2 px-6 py-2 bg-purple-600 hover:bg-purple-500 text-white text-[10px] font-bold rounded-lg shadow-lg shadow-purple-900/20 transition-all active:scale-95 disabled:opacity-50 uppercase tracking-widest"
              >
                {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                Save Rule
              </button>
            </div>
          </div>
        </div>
      )}

      {status && (
        <div className={`p-2 text-[10px] font-bold text-center uppercase tracking-widest ${
          status.type === 'success' ? 'bg-green-900/20 text-green-500' : 'bg-red-900/20 text-red-500'
        }`}>
          {status.message}
        </div>
      )}
    </div>
  );
};
