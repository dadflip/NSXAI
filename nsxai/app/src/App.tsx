import React, { useEffect, useState, useCallback } from 'react';
import { ListTree, PlugZap, Search, Edit3, Loader2, X, Plus, RefreshCcw } from 'lucide-react';
import { AgnosticTripleTree } from './components/AgnosticTripleTree';
import { ExportStudio } from './components/ExportStudio';
import { SelectControl } from './components/ui/SelectControl';
import { IconButton } from './components/ui/IconButton';
import { apiUrl, CONFIG } from './config';
import { getShortUri } from './lib/core';
import { fetchApi } from './lib/apiClient';

type AppTab = 'explorer' | 'export';

export default function App() {
  const [architecture, setArchitecture] = useState<{
    classes: { uri: string }[];
    properties: { uri: string }[];
    imports: { uri: string }[];
    individuals: { uri: string }[];
    individualLinks: { source: string; target: string; property: string }[];
  } | null>(null);
  const [triples, setTriples] = useState<{ subject: string; predicate: string; object: string; objectType: string }[]>([]);
  const [activeTab, setActiveTab] = useState<AppTab>('explorer');

  // Search state lifted from AgnosticTripleTree
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [editMode, setEditMode] = useState(false);
  const [creatingNew, setCreatingNew] = useState(false);

  const fetchData = useCallback(() => {
    fetchApi('architecture')
      .then((res) => {
        if (!res.ok) throw new Error(`Architecture fetch failed: ${res.status}`);
        return res.json();
      })
      .then((data) => setArchitecture(data))
      .catch(console.error);

    fetchApi('triples')
      .then((res) => {
        if (!res.ok) throw new Error(`Triples fetch failed: ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setTriples(data?.triples ?? []);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, CONFIG.explorer.refreshIntervalMs);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleReset = async () => {
    if (window.confirm('Êtes-vous sûr de vouloir réinitialiser la base de données avec l\'ontologie d\'origine ?')) {
      try {
        const res = await fetchApi('reset', { method: 'POST' });
        if (res.ok) {
          alert('Base de données réinitialisée avec succès !');
          fetchData();
        } else {
          alert('Erreur lors de la réinitialisation.');
        }
      } catch (e) {
        console.error(e);
        alert('Erreur réseau lors de la réinitialisation.');
      }
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-neutral-200 font-sans selection:bg-neutral-800 pt-24">
      <header className="fixed top-6 left-6 right-6 z-50 flex justify-center pointer-events-none">
        <div className="pointer-events-auto flex items-center gap-5 px-6 py-3 bg-[#0a0a0a]/80 backdrop-blur-2xl border border-white/10 rounded-[2rem] shadow-2xl ring-1 ring-white/5 w-full">
          {/* Logo/Title */}
          <div className="flex items-center shrink-0">
            <h1 className="text-base font-semibold tracking-wide text-transparent bg-clip-text bg-gradient-to-r from-neutral-100 to-neutral-500">
              {CONFIG.app.name}
            </h1>
          </div>
          
          {/* Divider */}
          <div className="w-px h-5 bg-white/10 shrink-0" />
          
          {/* Search Bar */}
          <div className="relative flex-1 max-w-sm h-9 group">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-500" />
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    setSearch(searchInput);
                  }
                }}
                placeholder="Rechercher..."
                className="w-full h-full pl-9 pr-9 py-1 text-sm text-neutral-200 placeholder:text-neutral-500 bg-white/5 border border-transparent rounded-full focus:outline-none focus:bg-white/10 focus:border-white/20 transition-all duration-300"
              />
              <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
                {search && (
                  <IconButton
                    onClick={() => { setSearch(''); setSearchInput(''); }}
                    icon={<X className="w-4 h-4" />}
                  />
                )}
                <IconButton
                  onClick={() => setSearch(searchInput)}
                  icon={
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                    </svg>
                  }
                />
              </div>
            </div>
            {/* Divider */}
            <div className="w-px h-5 bg-white/10 shrink-0 hidden lg:block" />
            
            {/* Tab Buttons (Segmented Control style) */}
            <div className="flex items-center gap-1 shrink-0 bg-white/5 p-1 rounded-full border border-white/5">
              <button
                onClick={() => setActiveTab('explorer')}
                className={`px-4 py-1.5 text-sm font-medium rounded-full transition-all duration-300 flex items-center gap-2 ${
                  activeTab === 'explorer'
                    ? 'bg-white text-black shadow-md'
                    : 'text-neutral-400 hover:text-white hover:bg-white/10'
                }`}
              >
                <ListTree className="w-4 h-4" />
                <span className="hidden sm:inline">Explorateur</span>
              </button>
              <button
                onClick={() => setActiveTab('export')}
                className={`px-4 py-1.5 text-sm font-medium rounded-full transition-all duration-300 flex items-center gap-2 ${
                  activeTab === 'export'
                    ? 'bg-white text-black shadow-md'
                    : 'text-neutral-400 hover:text-white hover:bg-white/10'
                }`}
              >
                <PlugZap className="w-4 h-4" />
                <span className="hidden sm:inline">Export</span>
              </button>
            </div>
            {/* Divider */}
            <div className="w-px h-5 bg-white/10 shrink-0 hidden lg:block" />
            
            {/* Edit Buttons */}
            {activeTab === 'explorer' && (
              <div className="flex items-center gap-1 shrink-0 bg-white/5 p-1 rounded-full border border-white/5">
                <button
                  onClick={() => setEditMode(!editMode)}
                  className={`px-4 py-1.5 text-sm font-medium rounded-full transition-all duration-300 flex items-center gap-2 ${
                    editMode
                      ? 'bg-white text-black shadow-md'
                      : 'text-neutral-400 hover:text-white hover:bg-white/10'
                  }`}
                >
                  {editMode ? <X className="w-4 h-4" /> : <Edit3 className="w-4 h-4" />}
                  <span className="hidden sm:inline">{editMode ? 'Fermer' : 'Éditer'}</span>
                </button>
                {editMode && (
                  <button
                    onClick={() => setCreatingNew(true)}
                    className="px-4 py-1.5 text-sm font-medium rounded-full transition-all duration-300 flex items-center gap-2 text-black bg-emerald-400 hover:bg-emerald-300 shadow-md"
                  >
                    <Plus className="w-4 h-4" />
                    <span className="hidden sm:inline">Nouvelle</span>
                  </button>
                )}
              </div>
            )}
            
            {/* Divider */}
            <div className="w-px h-5 bg-white/10 shrink-0 hidden lg:block" />
            
            {/* Reset Button */}
            <button
              onClick={handleReset}
              title="Réinitialiser la base avec l'ontologie d'origine"
              className="p-1.5 rounded-full text-neutral-400 hover:text-white hover:bg-white/10 transition-colors"
            >
              <RefreshCcw className="w-4 h-4" />
            </button>
        </div>
      </header>
      <div
        className={
          activeTab === 'explorer'
            ? 'w-full px-0'
            : 'max-w-6xl mx-auto p-4 md:p-8 h-[calc(100vh-96px)]'
        }
      >
        {activeTab === 'export' && (
          <div className="animate-in fade-in slide-in-from-bottom-2 duration-300 h-full">
            {architecture ? (
              <ExportStudio />
            ) : (
              <div className="text-neutral-400">Chargement...</div>
            )}
          </div>
        )}

        {activeTab === 'explorer' && (
          <div className="h-[calc(100vh-96px)]">
            {architecture ? (
              <AgnosticTripleTree
                triples={triples}
                architecture={architecture}
                search={search}
                editMode={editMode}
                creatingNew={creatingNew}
                onSetCreatingNew={setCreatingNew}
                onCancelCreate={() => setCreatingNew(false)}
                onRefresh={fetchData}
              />
            ) : (
              <div className="flex items-center justify-center h-full">
                <div className="flex flex-col items-center gap-4 text-neutral-400">
                  <Loader2 className="w-8 h-8 animate-spin text-neutral-500" />
                  <span className="font-medium">Chargement de l'architecture...</span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
