import React, { useState } from 'react';
import { Plus, Check, X } from 'lucide-react';

export function AddTypeInline({ node, knownTypeUris, getShortUri, onAdd }: {
  node: string; knownTypeUris: string[];
  getShortUri: (u: string) => string;
  onAdd: (typeUri: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [val, setVal]   = useState('');

  if (!open) return (
    <button type="button" onClick={() => setOpen(true)}
      className="text-[9px] flex items-center gap-1 text-neutral-500 hover:text-neutral-200 transition-colors px-1.5 py-0.5 rounded border border-neutral-800 bg-neutral-900/50 hover:bg-neutral-800">
      <Plus className="w-3 h-3" /> type
    </button>
  );

  return (
    <div className="flex items-center gap-1">
      <select value={val} onChange={e => setVal(e.target.value)}
        className="bg-transparent border-b border-neutral-700 py-0.5 text-[10px] text-neutral-300 focus:outline-none appearance-none">
        <option value="" className="bg-neutral-900">—</option>
        {knownTypeUris.map(uri => (
          <option key={uri} value={uri} className="bg-neutral-900">{getShortUri(uri)}</option>
        ))}
      </select>
      <button type="button" onClick={() => { if (val) { onAdd(val); setVal(''); setOpen(false); } }}
        className="text-neutral-500 hover:text-emerald-400 transition-colors p-[1px]"><Check className="w-[10px] h-[10px]" strokeWidth={3}/></button>
      <button type="button" onClick={() => { setOpen(false); setVal(''); }}
        className="text-neutral-600 hover:text-red-400 transition-colors p-[1px]"><X className="w-[10px] h-[10px]" strokeWidth={3} /></button>
    </div>
  );
}
