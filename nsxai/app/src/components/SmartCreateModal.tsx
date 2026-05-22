import React, { useState, useEffect } from 'react';
import { X, Plus, Sparkles, Loader2, Save, Database, Activity, Tag } from 'lucide-react';
import { IndividualFields, IndividualData } from './IndividualFields';
import { apiUrl } from '../lib/api';

interface SmartCreateModalProps {
  isOpen: boolean;
  onClose: () => void;
  type: 'class' | 'individual' | 'property' | 'unknown';
  architecture: any;
  onSuccess: (uri?: string) => void;
  initialName?: string;
  initialClass?: string;
}

export function SmartCreateModal({ 
  isOpen, 
  onClose, 
  type: initialType, 
  architecture, 
  onSuccess,
  initialName = '',
  initialClass = ''
}: SmartCreateModalProps) {
  const [activeType, setActiveType] = useState(initialType);
  
  // States for Class/Property creation (Simple)
  const [name, setName] = useState(initialName);
  const [label, setLabel] = useState('');
  const [comment, setComment] = useState('');
  
  // State for Individual creation (Recursive)
  const [individualData, setIndividualData] = useState<IndividualData | null>(null);
  const [selectedClass, setSelectedClass] = useState(initialClass);

  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (isOpen) {
        setActiveType(initialType === 'unknown' ? 'individual' : initialType);
        setName(initialName);
        setSelectedClass(initialClass);
    }
  }, [initialType, isOpen, initialName, initialClass]);

  const createRecursive = async (data: IndividualData): Promise<string> => {
    const baseUri = 'https://lms.flipova.fr/nsxai/v1/ontologies/data#';
    const uri = data.name.startsWith('http') ? data.name : `${baseUri}${data.name.replace(/\s+/g, '_')}`;
    
    const additionalTriples = [];
    if (data.classUri) {
        additionalTriples.push({ p: 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type', o: data.classUri, isLiteral: false });
    }
    
    // 1. Process nested children first
    const finalPropertyValues = { ...data.propertyValues };
    for (const [pUri, nestedData] of Object.entries(data.nestedIndividuals)) {
        if (nestedData && nestedData.name) {
            const nestedUri = await createRecursive(nestedData);
            finalPropertyValues[pUri] = nestedUri;
        }
    }
    
    // 2. Build triples
    Object.entries(finalPropertyValues).forEach(([pUri, val]) => {
        if (val.trim()) {
            const isLiteral = !val.startsWith('http');
            additionalTriples.push({ p: pUri, o: val, isLiteral });
        }
    });
    
    const res = await fetch(apiUrl('/api/ontology/create'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: 'individual',
        uri,
        label: data.label || data.name,
        comment: data.comment,
        additionalTriples
      })
    });
    
    if (!res.ok) throw new Error(await res.text());
    return uri;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    
    try {
      if (activeType === 'individual' && individualData && individualData.name) {
          const uri = await createRecursive(individualData);
          onSuccess(uri);
      } else {
          // Simple creation for Class/Property
          const baseUri = 'https://lms.flipova.fr/nsxai/v1/ontologies/data#';
          const uri = name.startsWith('http') ? name : `${baseUri}${name.replace(/\s+/g, '_')}`;
          
          const res = await fetch(apiUrl('/api/ontology/create'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              type: activeType,
              uri,
              label: label || name,
              comment,
              additionalTriples: []
            })
          });

          if (!res.ok) throw new Error(await res.text());
          onSuccess(uri);
      }
      
      onClose();
      resetForm();
    } catch (e: any) {
      alert("Erreur lors de la création : " + e.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const resetForm = () => {
    setName('');
    setSelectedClass('');
    setLabel('');
    setComment('');
    setIndividualData(null);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-[#0a0a0a]/90 backdrop-blur-md" onClick={onClose} />
      
      <div className="relative w-full max-w-2xl bg-neutral-900 border border-neutral-800 rounded-[2rem] shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        <div className="px-8 py-6 border-b border-neutral-800 flex items-center justify-between bg-neutral-950/40">
          <div className="flex items-center gap-4">
            <div className="p-2.5 bg-neutral-800 rounded-2xl border border-neutral-700">
                <Plus className="w-5 h-5 text-neutral-400" />
            </div>
            <div>
              <h2 className="text-lg font-medium text-white tracking-tight">Création d'Élément</h2>
              <p className="text-[10px] text-neutral-500 font-mono uppercase tracking-widest mt-0.5">Topologie Récursive</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-neutral-800 rounded-full transition-all group active:scale-90">
            <X className="w-5 h-5 text-neutral-500 group-hover:text-neutral-300" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-8 space-y-8 scrollbar-hide">
          <div className="grid grid-cols-3 gap-3">
            {[
              { id: 'class', label: 'Classe', icon: Database },
              { id: 'individual', label: 'Individu', icon: Activity },
              { id: 'property', label: 'Propriété', icon: Tag }
            ].map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setActiveType(t.id as any)}
                className={`flex flex-col items-center gap-2 p-4 rounded-3xl border transition-all duration-300 relative overflow-hidden group ${activeType === t.id ? 'bg-neutral-800 border-neutral-600 text-white shadow-lg' : 'bg-neutral-950 border-neutral-800 text-neutral-500 hover:border-neutral-700'}`}
              >
                <t.icon className={`w-5 h-5 mb-1 ${activeType === t.id ? 'text-white' : 'text-neutral-600'}`} />
                <span className="text-[10px] font-bold uppercase tracking-[0.2em]">{t.label}</span>
              </button>
            ))}
          </div>

          <div className="space-y-8">
            {activeType === 'individual' ? (
              <div className="space-y-6">
                <div className="space-y-1.5">
                  <label className="block text-[10px] uppercase tracking-[0.2em] text-neutral-500 font-bold ml-1">Classification du sujet</label>
                  <select
                      value={selectedClass}
                      onChange={(e) => setSelectedClass(e.target.value)}
                      className="w-full bg-neutral-950 border border-neutral-800 rounded-2xl px-4 py-3.5 text-sm text-white focus:outline-none focus:border-neutral-600 transition-all appearance-none cursor-pointer"
                  >
                      <option value="">Sélectionner une classe...</option>
                      {architecture?.classes?.sort((a: any, b: any) => a.uri.localeCompare(b.uri)).map((c: any) => (
                          <option key={c.uri} value={c.uri}>{c.uri.split(/[/#]/).pop()}</option>
                      ))}
                  </select>
                </div>
                
                {selectedClass && (
                    <IndividualFields 
                        classUri={selectedClass}
                        architecture={architecture}
                        onChange={setIndividualData}
                    />
                )}
              </div>
            ) : (
              <div className="space-y-6">
                <div className="space-y-1.5">
                  <label className="block text-[10px] uppercase tracking-[0.2em] text-neutral-500 font-bold ml-1">Identifiant Unique (URI)</label>
                  <input
                      required
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Ex: MaRessource"
                      className="w-full bg-neutral-950 border border-neutral-800 rounded-2xl px-4 py-3.5 text-sm text-white focus:outline-none focus:border-neutral-600 transition-all font-mono"
                  />
                </div>
                <div className="grid grid-cols-2 gap-6">
                    <div className="space-y-1.5">
                        <label className="block text-[10px] uppercase tracking-[0.2em] text-neutral-500 font-bold ml-1">Libellé</label>
                        <input
                            value={label}
                            onChange={(e) => setLabel(e.target.value)}
                            className="w-full bg-neutral-950 border border-neutral-800 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:border-neutral-600"
                        />
                    </div>
                    <div className="space-y-1.5">
                       <label className="block text-[10px] uppercase tracking-[0.2em] text-neutral-500 font-bold ml-1">Commentaire</label>
                       <input
                            value={comment}
                            onChange={(e) => setComment(e.target.value)}
                            className="w-full bg-neutral-950 border border-neutral-800 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:border-neutral-600"
                        />
                    </div>
                </div>
              </div>
            )}
          </div>
        </form>

        <div className="px-8 py-6 bg-neutral-950 border-t border-neutral-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-neutral-700" />
            <p className="text-[9px] text-neutral-500 uppercase tracking-widest font-mono">
                Moteur de Peuplement Sobre
            </p>
          </div>
          <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={onClose}
                className="px-6 py-2.5 text-[10px] font-bold uppercase tracking-[0.2em] text-neutral-500 hover:text-white transition-all"
                disabled={isSubmitting}
              >
                Annuler
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={isSubmitting || (activeType === 'individual' ? !individualData?.name : !name)}
                className="flex items-center gap-2.5 px-8 py-3 bg-white text-neutral-900 rounded-2xl text-[10px] font-black uppercase tracking-[0.2em] hover:bg-neutral-200 transition-all active:scale-95 disabled:opacity-30"
              >
                {isSubmitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                {isSubmitting ? 'VALIDATION...' : 'VALIDER'}
              </button>
          </div>
        </div>
      </div>
    </div>
  );
}