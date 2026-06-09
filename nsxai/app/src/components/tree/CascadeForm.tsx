import React, { useState } from 'react';
import { getShortUri as shortLocal } from '../../lib/core';

export interface CascadeFormProps {
  classUri: string;
  baseUri: string;
  onConfirm: (uri: string, label: string) => void;
  onCancel: () => void;
}

export function CascadeForm({ classUri, baseUri, onConfirm, onCancel }: CascadeFormProps) {
  const [localName, setLocalName] = useState('');
  const [label, setLabel]         = useState('');
  return (
    <div className="mt-2 pl-3 border-l border-neutral-700 space-y-3">
      <p className="text-[9px] uppercase tracking-widest text-neutral-500">
        Créer un nouveau <span className="text-blue-400">{shortLocal(classUri)}</span>
      </p>
      <div>
        <label className="block text-[9px] text-neutral-600 mb-1">Identifiant local</label>
        <div className="flex items-baseline gap-1">
          <span className="text-[9px] text-neutral-700 font-mono">{shortLocal(baseUri)}#</span>
          <input autoFocus value={localName} onChange={e => setLocalName(e.target.value)}
            placeholder="NomLocal"
            className="flex-1 bg-transparent border-b border-neutral-700 py-0.5 text-xs text-neutral-100 placeholder:text-neutral-600 focus:outline-none focus:border-neutral-400 font-mono" />
        </div>
      </div>
      <div>
        <label className="block text-[9px] text-neutral-600 mb-1">Label (optionnel)</label>
        <input value={label} onChange={e => setLabel(e.target.value)} placeholder="Nom d'affichage..."
          className="w-full bg-transparent border-b border-neutral-700 py-0.5 text-xs text-neutral-100 placeholder:text-neutral-600 focus:outline-none focus:border-neutral-400" />
      </div>
      <div className="flex gap-4">
        <button type="button" disabled={!localName.trim()}
          onClick={() => onConfirm(`${baseUri}#${localName.trim()}`, label)}
          className="text-[11px] text-neutral-200 hover:text-white font-medium transition-colors disabled:text-neutral-700 disabled:cursor-not-allowed">
          Créer et lier
        </button>
        <button type="button" onClick={onCancel} className="text-[11px] text-neutral-600 hover:text-neutral-400 transition-colors">Annuler</button>
      </div>
    </div>
  );
}
