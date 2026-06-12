import React, { useState } from 'react';
import { FlaskConical, Network, Library, FolderArchive, Table } from 'lucide-react';
import { OntologyExplorer } from './components/OntologyExplorer';
import { MatrixEditor } from './components/MatrixEditor';
import { ArtifactsViewer } from './components/ArtifactsViewer';

type AppTab = 'explorer' | 'matrix' | 'artifacts';

export default function App() {
  const [activeTab, setActiveTab] = useState<AppTab>('explorer');

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900 font-sans text-sm tracking-tight">
      <header className="h-12 px-4 border-b border-slate-300 bg-white flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <h1 className="text-base font-bold text-slate-800 tracking-tight">NSXAI Core</h1>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('explorer')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-sm font-medium border transition-none ${activeTab === 'explorer'
                ? 'bg-white text-blue-700 border-slate-300 shadow-sm'
                : 'text-slate-600 border-transparent hover:bg-slate-50 hover:text-slate-800'
              }`}
          >
            <Network className="w-3.5 h-3.5" />
            Ontology
          </button>
          <button
            onClick={() => setActiveTab('matrix')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-sm font-medium border transition-none ${activeTab === 'matrix'
                ? 'bg-white text-blue-700 border-slate-300 shadow-sm'
                : 'text-slate-600 border-transparent hover:bg-slate-50 hover:text-slate-800'
              }`}
          >
            <Table className="w-3.5 h-3.5" />
            Matrix
          </button>
          <button
            onClick={() => setActiveTab('artifacts')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-sm font-medium border transition-none ${activeTab === 'artifacts'
                ? 'bg-white text-blue-700 border-slate-300 shadow-sm'
                : 'text-slate-600 border-transparent hover:bg-slate-50 hover:text-slate-800'
              }`}
          >
            <FolderArchive className="w-3.5 h-3.5" />
            ML Outputs
          </button>
        </div>
      </header>

      <div className="p-3 h-[calc(100vh-48px)]">
        {activeTab === 'explorer' && (
          <div className="h-full">
            <OntologyExplorer />
          </div>
        )}

        {activeTab === 'matrix' && (
          <div className="h-full">
            <MatrixEditor />
          </div>
        )}

        {activeTab === 'artifacts' && (
          <div className="h-full">
            <ArtifactsViewer />
          </div>
        )}
      </div>
    </div>
  );
}
