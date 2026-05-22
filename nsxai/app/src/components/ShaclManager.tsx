import React, { useState, useEffect } from 'react';
import { Shield, Plus, Trash2, CheckCircle2, AlertCircle, Loader2, Save, Code, X, Edit3 } from 'lucide-react';
import { apiUrl } from '../lib/api';

interface ShaclShape {
  uri: string;
  label?: string;
}

interface ShapeDetail {
  p: string;
  o: string;
  isLiteral: boolean;
}

export const ShaclManager: React.FC = () => {
  const [shapes, setShapes] = useState<ShaclShape[]>([]);
  const [selectedShape, setSelectedShape] = useState<string | null>(null);
  const [shapeTriples, setShapeTriples] = useState<ShapeDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ type: 'success' | 'error', message: string } | null>(null);

  useEffect(() => {
    fetchShapes();
  }, []);

  const fetchShapes = async () => {
    setLoading(true);
    try {
      const res = await fetch(apiUrl('/api/ontology/shacl-shapes'));
      if (res.ok) {
        const data = await res.json();
        setShapes(data);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchShapeDetail = async (uri: string) => {
    setSelectedShape(uri);
    setLoading(true);
    try {
      const res = await fetch(apiUrl(`/api/ontology/shacl-shapes/${encodeURIComponent(uri)}`));
      if (res.ok) setShapeTriples(await res.json());
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const syncCustomShapesToLocalStorage = (shapeUri: string, targetClass: string, label: string) => {
    const saved = localStorage.getItem('nsxai_shacl_shapes');
    let customShapes = saved ? JSON.parse(saved) : [];
    // enlever la forme si elle existe dejà (update)
    customShapes = customShapes.filter((s: any) => s.uri !== shapeUri);
    customShapes.push({ uri: shapeUri, targetClass, label });
    localStorage.setItem('nsxai_shacl_shapes', JSON.stringify(customShapes));
  };

  const markShapeAsDeletedInLocalStorage = (uri: string) => {
    const saved = localStorage.getItem('nsxai_deleted_shacl_shapes');
    const deletedShapes = saved ? JSON.parse(saved) : [];
    if (!deletedShapes.includes(uri)) {
      deletedShapes.push(uri);
      localStorage.setItem('nsxai_deleted_shacl_shapes', JSON.stringify(deletedShapes));
    }
    // Remove from custom shapes if it was there
    const savedCustom = localStorage.getItem('nsxai_shacl_shapes');
    if (savedCustom) {
       let customShapes = JSON.parse(savedCustom);
       customShapes = customShapes.filter((s: any) => s.uri !== uri);
       localStorage.setItem('nsxai_shacl_shapes', JSON.stringify(customShapes));
    }
  };

  const handleDeleteShape = async (uri: string) => {
    if (!confirm(`Delete shape ${uri}?`)) return;
    setLoading(true);
    try {
      const res = await fetch(apiUrl(`/api/ontology/shacl-shapes/${encodeURIComponent(uri)}`), { method: 'DELETE' });
      if (res.ok) {
        markShapeAsDeletedInLocalStorage(uri);
        setStatus({ type: 'success', message: 'Shape deleted.' });
        setSelectedShape(null);
        setShapeTriples([]);
        fetchShapes();
      } else {
        setStatus({ type: 'error', message: 'Failed to delete shape.' });
      }
    } catch (e) {
      setStatus({ type: 'error', message: 'Network error' });
    } finally {
      setLoading(false);
      setTimeout(() => setStatus(null), 3000);
    }
  };

  const [showAddModal, setShowAddModal] = useState(false);
  const [editingShapeUri, setEditingShapeUri] = useState<string | null>(null);
  const [newShape, setNewShape] = useState({ uri: '', targetClass: '', label: '' });

  const handleEditShape = (uri: string) => {
    const shape = shapes.find(s => s.uri === uri);
    const targetClass = shapeTriples.find(t => t.p === 'http://www.w3.org/ns/shacl#targetClass')?.o || '';
    setNewShape({
      uri: uri,
      label: shape?.label || '',
      targetClass: targetClass
    });
    setEditingShapeUri(uri);
    setShowAddModal(true);
  };

  const handleAddShape = async () => {
    if (!newShape.uri || !newShape.targetClass) return;
    setLoading(true);
    try {
      if (editingShapeUri) {
         await fetch(apiUrl(`/api/ontology/shacl-shapes/${encodeURIComponent(editingShapeUri)}`), { method: 'DELETE' });
         markShapeAsDeletedInLocalStorage(editingShapeUri); // Track old URI as deleted
      }
      
      const triples = [
        { s: newShape.uri, p: 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type', o: 'http://www.w3.org/ns/shacl#NodeShape', isLiteral: false },
        { s: newShape.uri, p: 'http://www.w3.org/ns/shacl#targetClass', o: newShape.targetClass, isLiteral: false }
      ];
      if (newShape.label) {
        triples.push({ s: newShape.uri, p: 'http://www.w3.org/2000/01/rdf-schema#label', o: newShape.label, isLiteral: true });
      }

      const res = await fetch(apiUrl('/api/ontology/triples'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ triples })
      });

      if (res.ok) {
        syncCustomShapesToLocalStorage(newShape.uri, newShape.targetClass, newShape.label);
        setStatus({ type: 'success', message: 'SHACL Shape updated.' });
        setShowAddModal(false);
        setNewShape({ uri: '', targetClass: '', label: '' });
        fetchShapes();
      } else {
        setStatus({ type: 'error', message: 'Failed to update shape.' });
      }
    } catch (e) {
      setStatus({ type: 'error', message: 'Network error' });
    } finally {
      setLoading(false);
      setTimeout(() => setStatus(null), 3000);
    }
  };

  return (
    <div className="flex flex-col h-full bg-neutral-950 border-l border-neutral-900 border-r">
      <div className="p-4 border-b border-neutral-900 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Shield className="w-5 h-5 text-blue-500" />
          <h2 className="text-sm font-bold uppercase tracking-widest text-neutral-200">SHACL Constraints</h2>
        </div>
        <div className="flex gap-2">
          <button 
            onClick={() => {
              setNewShape({ uri: '', targetClass: '', label: '' });
              setShowAddModal(true);
            }}
            className="flex items-center gap-2 px-3 py-1.5 bg-neutral-900 border border-neutral-800 rounded-lg text-[10px] font-bold text-neutral-400 hover:text-white hover:border-neutral-700 transition-all"
          >
            <Plus className="w-3.5 h-3.5" />
            ADD SHAPE
          </button>
          <button 
            onClick={fetchShapes}
            className="p-1.5 hover:bg-neutral-900 rounded text-neutral-500 transition-colors"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Refresh'}
          </button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Shape List */}
        <div className="w-1/3 border-r border-neutral-900 overflow-y-auto p-2 space-y-1 custom-scrollbar bg-black/20">
          {shapes.length === 0 && !loading && (
            <div className="p-4 text-center text-xs text-neutral-600 italic">No NodeShapes found.</div>
          )}
          {shapes.map(s => (
            <div key={s.uri} className="group relative">
               <button
                onClick={() => fetchShapeDetail(s.uri)}
                className={`w-full text-left p-3 rounded-xl border transition-all ${
                  selectedShape === s.uri 
                  ? 'bg-blue-600/10 border-blue-600/30 text-blue-400' 
                  : 'bg-transparent border-transparent text-neutral-400 hover:bg-neutral-900'
                }`}
              >
                <div className="text-[11px] font-bold truncate">{s.label || s.uri.split(/[#/]/).pop()}</div>
                <div className="text-[9px] opacity-40 truncate font-mono">{s.uri}</div>
              </button>
              {selectedShape === s.uri && (
                <button 
                  onClick={(e) => { e.stopPropagation(); handleDeleteShape(s.uri); }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-2 hover:bg-red-900/20 text-neutral-600 hover:text-red-500 transition-all opacity-0 group-hover:opacity-100"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
          {selectedShape ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-neutral-900/30 rounded-2xl border border-neutral-900">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-blue-600/10 flex items-center justify-center border border-blue-600/20">
                    <Shield className="w-5 h-5 text-blue-400" />
                  </div>
                  <div className="overflow-hidden">
                    <h3 className="text-xs font-bold text-neutral-200 uppercase tracking-widest truncate">
                      {selectedShape.split(/[#/]/).pop()}
                    </h3>
                    <p className="text-[9px] text-neutral-500 font-mono truncate">{selectedShape}</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button 
                    onClick={() => handleEditShape(selectedShape)}
                    className="p-2 hover:bg-blue-900/20 rounded-lg text-neutral-600 hover:text-blue-500 transition-all"
                  >
                    <Edit3 className="w-4 h-4" />
                  </button>
                  <button 
                    onClick={() => handleDeleteShape(selectedShape)}
                    className="p-2 hover:bg-red-900/20 rounded-lg text-neutral-600 hover:text-red-500 transition-all"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between px-1">
                  <h4 className="text-[10px] font-bold text-neutral-500 uppercase tracking-widest flex items-center gap-2">
                     <Code className="w-3 h-3" />
                     Triples Definition
                  </h4>
                  <span className="text-[9px] text-neutral-600 font-mono italic">{shapeTriples.length} entries</span>
                </div>
                <div className="bg-black/40 rounded-2xl border border-neutral-900 overflow-hidden">
                  <table className="w-full text-left">
                    <thead className="bg-neutral-900/30 border-b border-neutral-900">
                      <tr>
                        <th className="p-3 text-[10px] font-bold text-neutral-600 uppercase tracking-widest">Predicate</th>
                        <th className="p-3 text-[10px] font-bold text-neutral-600 uppercase tracking-widest">Object</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-neutral-900/50">
                      {shapeTriples.map((t, idx) => (
                        <tr key={idx} className="hover:bg-neutral-900/20 transition-colors">
                          <td className="p-3">
                            <span className="text-[10px] font-mono text-blue-400/70" title={t.p}>
                              {t.p.split(/[#/]/).pop()}
                            </span>
                          </td>
                          <td className="p-3">
                            <span className={`text-[10px] font-mono ${t.isLiteral ? 'text-neutral-300' : 'text-emerald-400/80'}`} title={t.o}>
                              {t.isLiteral ? `"${t.o}"` : t.o.split(/[#/]/).pop()}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-neutral-600 space-y-4 opacity-50">
              <div className="w-16 h-16 rounded-3xl bg-neutral-900/50 flex items-center justify-center border border-neutral-800">
                <Shield className="w-8 h-8" />
              </div>
              <p className="text-[10px] font-bold uppercase tracking-widest">Select a SHACL Shape to view details</p>
            </div>
          )}
        </div>
      </div>

      {showAddModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-neutral-950 border border-neutral-800 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden">
            <div className="p-4 border-b border-neutral-900 flex items-center justify-between">
              <h3 className="text-sm font-bold text-neutral-200 uppercase tracking-widest flex items-center gap-2">
                {editingShapeUri ? <Edit3 className="w-4 h-4 text-blue-500" /> : <Plus className="w-4 h-4 text-blue-500" />}
                {editingShapeUri ? 'Edit SHACL NodeShape' : 'Add SHACL NodeShape'}
              </h3>
              <button 
                onClick={() => { setShowAddModal(false); setEditingShapeUri(null); }}
                className="p-2 hover:bg-neutral-900 rounded-lg text-neutral-500"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div className="space-y-1.5">
                <label className="text-[10px] font-bold text-neutral-500 uppercase">Shape URI</label>
                <input 
                  type="text" 
                  placeholder="ex: http://example.org/MyShape"
                  value={newShape.uri}
                  onChange={e => setNewShape({...newShape, uri: e.target.value})}
                  className="w-full bg-neutral-900 border border-neutral-800 rounded-lg p-2.5 text-xs text-neutral-200"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-[10px] font-bold text-neutral-500 uppercase">Target Class URI</label>
                <input 
                  type="text" 
                  placeholder="ex: http://xmlns.com/foaf/0.1/Person"
                  value={newShape.targetClass}
                  onChange={e => setNewShape({...newShape, targetClass: e.target.value})}
                  className="w-full bg-neutral-900 border border-neutral-800 rounded-lg p-2.5 text-xs text-neutral-200"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-[10px] font-bold text-neutral-500 uppercase">Label (Optional)</label>
                <input 
                  type="text" 
                  placeholder="My Person Shape"
                  value={newShape.label}
                  onChange={e => setNewShape({...newShape, label: e.target.value})}
                  className="w-full bg-neutral-900 border border-neutral-800 rounded-lg p-2.5 text-xs text-neutral-200"
                />
              </div>
              <div className="p-3 bg-blue-900/10 rounded-lg border border-blue-900/20 text-[10px] text-blue-300/80 italic">
                This will create basic sh:NodeShape and sh:targetClass properties. You can add more constraints in the Extra Triples view.
              </div>
            </div>
            <div className="p-4 bg-neutral-900/20 border-t border-neutral-900 flex justify-end gap-3">
              <button 
                onClick={() => { setShowAddModal(false); setEditingShapeUri(null); }}
                className="px-4 py-2 text-xs font-bold text-neutral-500 hover:text-neutral-200 uppercase tracking-widest"
              >
                Cancel
              </button>
              <button 
                onClick={handleAddShape}
                disabled={loading || !newShape.uri || !newShape.targetClass}
                className="flex items-center gap-2 px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white text-[10px] font-bold rounded-lg shadow-lg shadow-blue-900/20 transition-all active:scale-95 disabled:opacity-50 uppercase tracking-widest"
              >
                {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                {editingShapeUri ? 'Update Shape' : 'Create Shape'}
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
