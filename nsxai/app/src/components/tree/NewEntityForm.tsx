import React, { useState, useEffect } from 'react';
import { Settings2 } from 'lucide-react';

export interface NewEntityFormProps {
  getShortUri: (u: string) => string;
  onCancel: () => void;
  onCreate: () => void;
}

export function NewEntityForm({ getShortUri, onCancel, onCreate }: NewEntityFormProps) {
  const [label, setLabel] = useState('');
  const [uri, setUri] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [autoGen, setAutoGen] = useState(true);

  // Auto-generate URI from label
  useEffect(() => {
    if (autoGen) {
      const generated = label
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "") // remove accents
        .replace(/[^a-zA-Z0-9]/g, "") // remove spaces and special chars
        .replace(/^./, (str) => str.toUpperCase()); // PascalCase
      setUri(generated);
    }
  }, [label, autoGen]);

  const handleUriChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setUri(e.target.value);
    setAutoGen(false);
  };

  return (
    <div className="h-full flex flex-col border border-white/10 bg-[#0a0a0a]/80 backdrop-blur-2xl rounded-[2rem] shadow-2xl ring-1 ring-white/5 animate-in fade-in duration-200 overflow-hidden relative max-w-2xl mx-auto mt-10">
      <div className="shrink-0 p-6 border-b border-neutral-800/80 bg-neutral-900/20">
         <h2 className="text-3xl font-bold tracking-tight text-neutral-100">Nouvelle Entrée</h2>
         <p className="mt-2 text-sm text-neutral-400">Créez une nouvelle ressource. Vous pourrez ensuite lui ajouter des propriétés, des types, etc.</p>
      </div>

      <div className="p-8 space-y-6 flex-1">
        <div>
          <label className="block text-[11px] font-semibold uppercase tracking-widest text-neutral-500 mb-2">Nom / Libellé</label>
          <input 
            type="text" 
            id="new-label" 
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Ex: Jean Dupont"
            className="w-full bg-white/5 border border-white/10 focus:bg-white/10 focus:border-emerald-500/50 rounded-xl px-4 py-3 text-sm text-white placeholder:text-neutral-600 focus:outline-none transition-all duration-300 shadow-inner" 
            autoFocus
          />
        </div>

        <div>
          <div className="flex justify-between items-center mb-2">
            <label className="block text-[11px] font-semibold uppercase tracking-widest text-neutral-500">URI (Identifiant)</label>
            <button 
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-[10px] text-neutral-500 hover:text-neutral-300 flex items-center gap-1"
            >
              <Settings2 className="w-3 h-3" /> Personnaliser
            </button>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <input 
                type="text" 
                id="new-uri" 
                value={uri}
                onChange={handleUriChange}
                disabled={!showAdvanced}
                placeholder="IdentifiantUnique"
                className={`w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm font-mono transition-all duration-300 shadow-inner focus:outline-none ${showAdvanced ? 'text-emerald-400 focus:border-emerald-500/50 focus:bg-white/10' : 'text-neutral-500 cursor-not-allowed opacity-70'}`} 
              />
            </div>
          </div>
          {!showAdvanced && (
             <p className="mt-2 text-[11px] text-neutral-600 italic">L'URI est générée automatiquement à partir du nom. Personnalisez-la si besoin.</p>
          )}
        </div>
      </div>

      <div className="shrink-0 p-6 border-t border-neutral-800/80 bg-neutral-900/40 flex justify-end gap-3">
        <button 
          onClick={onCancel}
          className="px-6 py-2 rounded-full text-sm font-medium text-neutral-400 hover:text-white hover:bg-white/10 transition-colors"
        >
          Annuler
        </button>
        <button 
          onClick={onCreate}
          disabled={!uri}
          className="px-6 py-2 rounded-full text-sm font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 hover:text-emerald-300 transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-emerald-500/10"
        >
          Créer l'entrée
        </button>
      </div>
    </div>
  );
}
