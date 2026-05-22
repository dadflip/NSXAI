import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Sparkles, Loader2, Info, ArrowRight, ChevronDown, UserPlus, X, Search, Database, Plus } from 'lucide-react';
import { apiUrl } from '../lib/api';

export interface IndividualData {
  name: string;
  label: string;
  comment: string;
  classUri: string;
  propertyValues: Record<string, string>;
  nestedIndividuals: Record<string, IndividualData>;
}

interface Suggestion {
  uri: string;
  range?: string;
  label?: string;
  comment?: string;
}

interface Instance {
  uri: string;
  label?: string;
}

interface IndividualFieldsProps {
  classUri: string;
  architecture: any;
  onChange: (data: IndividualData) => void;
  level?: number;
  labelPrefix?: string;
}

export function IndividualFields({ classUri, architecture, onChange, level = 0, labelPrefix = '' }: IndividualFieldsProps) {
  const [name, setName] = useState('');
  const [label, setLabel] = useState('');
  const [comment, setComment] = useState('');
  const [propertyValues, setPropertyValues] = useState<Record<string, string>>({});
  const [nestedIndividuals, setNestedIndividuals] = useState<Record<string, IndividualData>>({});
  
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(false);
  const [instancesMap, setInstancesMap] = useState<Record<string, Instance[]>>({});
  const [isLoadingInstances, setIsLoadingInstances] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (classUri) {
        loadSuggestions(classUri);
    }
  }, [classUri]);

  useEffect(() => {
    onChange({
      name,
      label,
      comment,
      classUri,
      propertyValues,
      nestedIndividuals
    });
  }, [name, label, comment, propertyValues, nestedIndividuals]);

  const loadSuggestions = async (uri: string) => {
    setIsLoadingSuggestions(true);
    try {
      const res = await fetch(apiUrl(`/api/ontology/suggestions/${encodeURIComponent(uri)}`));
      const data = await res.json();
      const newSuggestions: Suggestion[] = data.suggestions || [];
      setSuggestions(newSuggestions);

      newSuggestions.forEach(s => {
          if (s.range && !s.range.toLowerCase().includes('literal') && !s.range.toLowerCase().includes('string') && !s.range.toLowerCase().includes('integer')) {
              loadInstances(s.uri, s.range);
          }
      });
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoadingSuggestions(false);
    }
  };

  const loadInstances = async (propertyUri: string, rangeUri: string) => {
    setIsLoadingInstances(prev => ({ ...prev, [propertyUri]: true }));
    try {
      const res = await fetch(apiUrl(`/api/ontology/instances/${encodeURIComponent(rangeUri)}`));
      const data = await res.json();
      setInstancesMap(prev => ({ ...prev, [propertyUri]: data.instances || [] }));
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoadingInstances(prev => ({ ...prev, [propertyUri]: false }));
    }
  };

  const toggleNested = (propertyUri: string, rangeUri: string) => {
      setNestedIndividuals(prev => {
          if (prev[propertyUri]) {
              const newNested = { ...prev };
              delete newNested[propertyUri];
              return newNested;
          }
          return {
              ...prev,
              [propertyUri]: {
                  name: '',
                  label: '',
                  comment: '',
                  classUri: rangeUri,
                  propertyValues: {},
                  nestedIndividuals: {}
              }
          };
      });
  };

  return (
    <div className={`space-y-6 ${level > 0 ? 'p-6 bg-neutral-950/20 border border-neutral-800 rounded-3xl mt-4 relative overflow-hidden' : ''}`}>
      {level > 0 && (
          <div className="absolute top-0 left-0 w-1 h-full bg-neutral-800" />
      )}
      
      <div className="space-y-6">
        <div className="relative group">
          <label className="block text-[10px] uppercase tracking-[0.2em] text-neutral-500 font-bold mb-2 ml-1">
            {labelPrefix} Identifiant (URI)
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-14 flex items-center pointer-events-none pr-4">
                <Search className="h-4 w-4 text-neutral-600" />
            </div>
            <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ex: Patient_001"
                className="w-full bg-neutral-950 border border-neutral-800 rounded-xl pl-11 pr-4 py-3 text-sm text-white focus:outline-none focus:border-neutral-600 transition-all font-mono"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-1.5">
                <label className="block text-[10px] uppercase tracking-[0.2em] text-neutral-500 font-bold ml-1">Libellé</label>
                <input
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                    placeholder="Nom d'affichage"
                    className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-neutral-600 transition-all font-mono"
                />
            </div>
            <div className="space-y-1.5">
               <label className="block text-[10px] uppercase tracking-[0.2em] text-neutral-500 font-bold ml-1">Commentaire</label>
               <input
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="Description..."
                    className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-neutral-600 transition-all font-mono"
                />
            </div>
        </div>
      </div>

      {suggestions.length > 0 && (
        <div className="bg-neutral-950/20 rounded-3xl border border-neutral-800 p-6 space-y-6">
           <div className="flex items-center justify-between border-b border-neutral-800 pb-4">
              <div className="flex flex-col gap-1">
                 <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-neutral-400 flex items-center gap-2">
                     <Database className="w-3.5 h-3.5" />
                     Schéma de l'Entité
                 </h3>
                 <p className="text-[9px] text-neutral-500">Propriétés pour <span className="text-neutral-400 font-mono">{classUri.split(/[/#]/).pop()}</span></p>
              </div>
              {isLoadingSuggestions && <Loader2 className="w-4 h-4 animate-spin text-neutral-600" />}
           </div>

           <div className="grid grid-cols-1 gap-6">
              {suggestions.map((s) => {
                const instances = instancesMap[s.uri] || [];
                const isObjectProperty = s.range && !s.range.toLowerCase().includes('literal') && !s.range.toLowerCase().includes('string') && !s.range.toLowerCase().includes('integer');
                const isCreating = !!nestedIndividuals[s.uri];

                return (
                  <div key={s.uri} className="space-y-3 group/field">
                    <div className="flex items-center justify-between ml-1">
                        <label className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider">
                            {s.uri.split(/[/#]/).pop()}
                        </label>
                        {s.range && (
                           <span className="text-[9px] text-neutral-500 bg-neutral-900 border border-neutral-800 px-2 py-0.5 rounded-full flex items-center gap-1.5 font-mono">
                              {s.range.split(/[/#]/).pop()}
                           </span>
                        )}
                    </div>

                    <div className="flex gap-2">
                        <div className="relative flex-1">
                            {isObjectProperty && instances.length > 0 && !isCreating ? (
                                <div className="relative">
                                  <select
                                      value={propertyValues[s.uri] || ''}
                                      onChange={(e) => setPropertyValues(prev => ({ ...prev, [s.uri]: e.target.value }))}
                                      className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-2.5 text-xs text-neutral-300 focus:outline-none focus:border-neutral-600 font-mono appearance-none"
                                  >
                                      <option value="">-- Sélectionner --</option>
                                      {instances.map(inst => (
                                          <option key={inst.uri} value={inst.uri}>{inst.label || inst.uri.split(/[/#]/).pop()}</option>
                                      ))}
                                  </select>
                                  <ChevronDown className="absolute right-3 top-3 w-3 h-3 text-neutral-600 pointer-events-none" />
                                </div>
                            ) : (
                                <input
                                  disabled={isCreating}
                                  value={isCreating ? `[Création Récursive Active]` : (propertyValues[s.uri] || '')}
                                  onChange={(e) => setPropertyValues(prev => ({ ...prev, [s.uri]: e.target.value }))}
                                  placeholder={isObjectProperty ? "URI cible" : "Valeur brute"}
                                  className={`w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-2.5 text-xs font-mono focus:outline-none ${isCreating ? 'text-neutral-600 italic border-neutral-800/50' : 'text-neutral-300 focus:border-neutral-600'}`}
                                />
                            )}
                        </div>

                        {isObjectProperty && (
                            <button 
                              type="button"
                              onClick={() => toggleNested(s.uri, s.range!)}
                              className={`flex items-center gap-2 px-4 border rounded-xl text-[10px] font-bold uppercase tracking-widest transition-all active:scale-95 whitespace-nowrap ${isCreating ? 'bg-neutral-800 border-neutral-600 text-white' : 'bg-neutral-900 border-neutral-800 text-neutral-500 hover:text-white'}`}
                            >
                              {isCreating ? <X className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
                              {isCreating ? 'Annuler' : 'Nouveau'}
                            </button>
                        )}
                    </div>

                    <AnimatePresence>
                        {isCreating && (
                            <motion.div
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: 'auto' }}
                                exit={{ opacity: 0, height: 0 }}
                                className="overflow-hidden"
                            >
                                <IndividualFields 
                                  classUri={s.range!}
                                  architecture={architecture}
                                  level={level + 1}
                                  labelPrefix={`${s.uri.split(/[/#]/).pop()} >`}
                                  onChange={(data) => {
                                      setNestedIndividuals(prev => ({ ...prev, [s.uri]: data }));
                                  }}
                                />
                            </motion.div>
                        )}
                    </AnimatePresence>
                  </div>
                );
              })}
           </div>
        </div>
      )}
    </div>
  );
}