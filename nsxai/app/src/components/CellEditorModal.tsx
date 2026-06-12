import React, { useState, useEffect, useMemo } from 'react';
import { X, Search, Plus, Check, Loader2 } from 'lucide-react';
import { fetchAllEntities } from '../lib/sparqlQueries';

interface CellEditorModalProps {
  initialValue: string;
  subjectUri: string;
  predicateUri: string;
  onSave: (newValue: string) => void;
  onCancel: () => void;
}

export const CellEditorModal: React.FC<CellEditorModalProps> = ({
  initialValue,
  subjectUri,
  predicateUri,
  onSave,
  onCancel
}) => {
  const [values, setValues] = useState<string[]>(
    initialValue ? initialValue.split('|').map(v => v.trim()).filter(v => v) : []
  );
  
  const [search, setSearch] = useState('');
  const [entities, setEntities] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAllEntities(false)
      .then(data => {
        setEntities(data);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to fetch entities", err);
        setLoading(false);
      });
  }, []);

  const addValue = (val: string) => {
    const trimmed = val.trim();
    if (trimmed && !values.includes(trimmed)) {
      setValues([...values, trimmed]);
    }
    setSearch('');
  };

  const removeValue = (indexToRemove: number) => {
    setValues(values.filter((_, idx) => idx !== indexToRemove));
  };

  const handleSave = () => {
    onSave(values.join('|'));
  };

  const filteredEntities = useMemo(() => {
    if (!search) return [];
    const lowerSearch = search.toLowerCase();
    return entities
      .filter(e => 
        e.label.toLowerCase().includes(lowerSearch) || 
        e.uri.toLowerCase().includes(lowerSearch)
      )
      .slice(0, 50); // Limit results for performance
  }, [entities, search]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-slate-50 border border-slate-300 shadow-xl w-[500px] flex flex-col max-h-[80vh]">
        <div className="p-3 border-b border-slate-200 bg-slate-100 flex justify-between items-center shrink-0">
          <div>
            <h3 className="text-sm font-bold text-slate-800">Edit Cell</h3>
            <div className="text-[10px] text-slate-500 font-mono mt-1">
              <span className="font-bold text-slate-700">S:</span> {subjectUri.split(/[/#]/).pop()} &nbsp;
              <span className="font-bold text-slate-700">P:</span> {predicateUri.split(/[/#]/).pop()}
            </div>
          </div>
          <button onClick={onCancel} className="text-slate-400 hover:text-slate-700">
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <div className="p-3 flex-1 overflow-hidden flex flex-col gap-3">
          {/* Current Values */}
          <div>
            <label className="block text-[11px] font-bold text-slate-600 mb-1 uppercase">Current Values ({values.length})</label>
            <div className="bg-white border border-slate-300 p-2 min-h-[60px] max-h-[150px] overflow-y-auto flex flex-wrap gap-1">
              {values.length === 0 ? (
                <span className="text-xs text-slate-400 italic">No values. Search or add a custom URI below.</span>
              ) : (
                values.map((v, idx) => (
                  <span key={idx} className="inline-flex items-center gap-1 bg-blue-50 border border-blue-200 text-blue-800 text-xs px-1.5 py-0.5 rounded-sm font-mono max-w-full">
                    <span className="truncate" title={v}>{v.split(/[/#]/).pop() || v}</span>
                    <button 
                      onClick={() => removeValue(idx)}
                      className="hover:bg-blue-200 rounded-full p-0.5 text-blue-500 hover:text-blue-900"
                      title="Remove"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))
              )}
            </div>
          </div>

          {/* Add New Value */}
          <div className="flex-1 flex flex-col min-h-0">
            <label className="block text-[11px] font-bold text-slate-600 mb-1 uppercase">Add Existing Entity or Custom URI</label>
            <div className="relative shrink-0">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input 
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search entities or paste full URI..."
                className="w-full pl-8 pr-2 py-1.5 bg-white border border-slate-300 text-xs text-slate-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors rounded-sm"
                autoFocus
              />
            </div>
            
            <div className="mt-2 flex-1 overflow-y-auto border border-slate-200 bg-white">
              {loading ? (
                <div className="p-4 flex items-center justify-center text-slate-500 gap-2 text-xs">
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading entities...
                </div>
              ) : search.trim() ? (
                <div>
                  <div 
                    className="p-2 border-b border-slate-100 hover:bg-slate-50 cursor-pointer flex items-center gap-2"
                    onClick={() => addValue(search)}
                  >
                    <Plus className="w-4 h-4 text-slate-400" />
                    <span className="text-xs font-bold text-blue-600">Add custom value:</span>
                    <span className="text-xs font-mono text-slate-700 truncate">{search}</span>
                  </div>
                  {filteredEntities.map((ent, idx) => (
                    <div 
                      key={idx}
                      className="p-2 border-b border-slate-100 hover:bg-slate-50 cursor-pointer flex flex-col"
                      onClick={() => addValue(ent.uri)}
                    >
                      <span className="text-xs font-bold text-slate-800">{ent.label}</span>
                      <span className="text-[10px] font-mono text-slate-500 truncate">{ent.uri}</span>
                    </div>
                  ))}
                  {filteredEntities.length === 0 && (
                    <div className="p-3 text-xs text-slate-500 italic">No existing entities match. Use "Add custom value" above.</div>
                  )}
                </div>
              ) : (
                <div className="p-4 text-center text-xs text-slate-400">
                  Type to search for existing entities in the ontology.
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="p-3 border-t border-slate-200 bg-slate-100 flex justify-end gap-2 shrink-0">
          <button 
            onClick={onCancel}
            className="px-3 py-1.5 bg-white border border-slate-300 text-xs font-bold text-slate-600 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button 
            onClick={handleSave}
            className="px-3 py-1.5 bg-blue-600 border border-blue-700 text-white text-xs font-bold hover:bg-blue-700 flex items-center gap-1 shadow-sm"
          >
            <Check className="w-4 h-4" /> Save Cell
          </button>
        </div>
      </div>
    </div>
  );
};
