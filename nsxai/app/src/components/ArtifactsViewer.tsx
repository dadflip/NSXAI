import React, { useState, useEffect } from 'react';
import { Folder, File, FileText, Image, Table2, LayoutTemplate, Download, FileJson, FileCode, ChevronRight, ChevronDown, Loader2, Database } from 'lucide-react';
import { apiUrl } from '../config';

interface ArtifactNode {
  name: string;
  type: 'directory' | 'file';
  path: string;
  size?: number;
  ext?: string;
  children?: ArtifactNode[];
}

const getFileIcon = (ext?: string) => {
  switch (ext) {
    case '.png':
    case '.jpg':
    case '.jpeg':
      return <Image className="w-4 h-4 text-blue-500" />;
    case '.csv':
      return <Table2 className="w-4 h-4 text-green-600" />;
    case '.html':
      return <LayoutTemplate className="w-4 h-4 text-orange-500" />;
    case '.json':
      return <FileJson className="w-4 h-4 text-yellow-600" />;
    case '.yaml':
    case '.yml':
    case '.log':
    case '.txt':
      return <FileText className="w-4 h-4 text-slate-500" />;
    case '.pkl':
      return <Database className="w-4 h-4 text-purple-600" />;
    default:
      return <File className="w-4 h-4 text-slate-400" />;
  }
};

const formatSize = (bytes?: number) => {
  if (bytes === undefined) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
};

export const ArtifactsViewer: React.FC = () => {
  const [tree, setTree] = useState<ArtifactNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedFile, setSelectedFile] = useState<ArtifactNode | null>(null);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());

  const [fileContent, setFileContent] = useState<string | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);

  useEffect(() => {
    fetch(apiUrl('/api/artifacts/tree'))
      .then(res => res.json())
      .then(data => {
        setTree(data);
        // Expand root level by default
        const roots = new Set<string>();
        data.forEach((node: ArtifactNode) => {
          if (node.type === 'directory') roots.add(node.path);
        });
        setExpandedDirs(roots);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to load artifacts tree", err);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!selectedFile || selectedFile.type !== 'file') return;

    const ext = selectedFile.ext;
    const isText = ['.csv', '.json', '.log', '.txt', '.yaml', '.yml'].includes(ext || '');
    
    if (isText) {
      setLoadingContent(true);
      fetch(apiUrl(`/api/artifacts/download/${selectedFile.path}`))
        .then(res => res.text())
        .then(text => setFileContent(text))
        .catch(console.error)
        .finally(() => setLoadingContent(false));
    } else {
      setFileContent(null);
    }
  }, [selectedFile]);

  const toggleDir = (path: string) => {
    const next = new Set(expandedDirs);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    setExpandedDirs(next);
  };

  const renderTree = (nodes: ArtifactNode[], level = 0) => {
    return nodes.map((node) => {
      const isExpanded = expandedDirs.has(node.path);
      const isSelected = selectedFile?.path === node.path;
      
      if (node.type === 'directory') {
        return (
          <div key={node.path}>
            <div 
              className={`flex items-center gap-1.5 px-2 py-1 cursor-pointer hover:bg-slate-100 select-none text-slate-700`}
              style={{ paddingLeft: `${level * 12 + 8}px` }}
              onClick={() => toggleDir(node.path)}
            >
              {isExpanded ? <ChevronDown className="w-3.5 h-3.5 text-slate-400 shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />}
              <Folder className="w-4 h-4 text-blue-400 shrink-0 fill-blue-100" />
              <span className="text-sm font-medium truncate">{node.name}</span>
            </div>
            {isExpanded && node.children && renderTree(node.children, level + 1)}
          </div>
        );
      }

      return (
        <div 
          key={node.path}
          className={`flex items-center justify-between gap-1.5 px-2 py-1 cursor-pointer select-none group
            ${isSelected ? 'bg-blue-50 text-blue-800 border-l-2 border-blue-500' : 'text-slate-600 hover:bg-slate-50 border-l-2 border-transparent'}`}
          style={{ paddingLeft: `${level * 12 + 24}px` }}
          onClick={() => setSelectedFile(node)}
        >
          <div className="flex items-center gap-1.5 min-w-0">
            {getFileIcon(node.ext)}
            <span className={`text-sm truncate ${isSelected ? 'font-medium' : ''}`}>{node.name}</span>
          </div>
          <span className="text-[10px] text-slate-400 font-mono hidden group-hover:block shrink-0">
            {formatSize(node.size)}
          </span>
        </div>
      );
    });
  };

  const renderContent = () => {
    if (!selectedFile) {
      return (
        <div className="h-full flex flex-col items-center justify-center text-slate-400">
          <Folder className="w-12 h-12 mb-2 opacity-20" />
          <p>Select a file from the left panel to view it.</p>
        </div>
      );
    }

    const downloadUrl = apiUrl(`/api/artifacts/download/${selectedFile.path}`);
    const ext = selectedFile.ext;

    const Header = () => (
      <div className="p-3 border-b border-slate-300 bg-slate-100 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          {getFileIcon(ext)}
          <h3 className="text-sm font-bold text-slate-800 truncate">{selectedFile.name}</h3>
          <span className="text-xs text-slate-500 font-mono bg-slate-200 px-1.5 py-0.5 rounded-sm shrink-0">
            {formatSize(selectedFile.size)}
          </span>
        </div>
        <a 
          href={downloadUrl} 
          download={selectedFile.name}
          target="_blank" rel="noreferrer"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded-sm text-xs font-bold hover:bg-slate-50 shadow-sm shrink-0"
        >
          <Download className="w-3.5 h-3.5" /> Download
        </a>
      </div>
    );

    if (ext === '.png' || ext === '.jpg') {
      return (
        <div className="flex flex-col h-full overflow-hidden bg-slate-50">
          <Header />
          <div className="flex-1 overflow-auto p-4 flex items-center justify-center">
            <img src={downloadUrl} alt={selectedFile.name} className="max-w-full max-h-full object-contain border border-slate-300 shadow-sm bg-white" />
          </div>
        </div>
      );
    }

    if (ext === '.html') {
      return (
        <div className="flex flex-col h-full overflow-hidden bg-white">
          <Header />
          <iframe src={downloadUrl} className="flex-1 w-full border-none bg-white" title={selectedFile.name} />
        </div>
      );
    }

    if (ext === '.csv' && fileContent) {
      // Basic CSV rendering
      const rows = fileContent.trim().split('\n');
      const headers = rows[0].split(',');
      
      return (
        <div className="flex flex-col h-full overflow-hidden bg-white">
          <Header />
          <div className="flex-1 overflow-auto bg-white custom-scrollbar p-0">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-slate-100 sticky top-0 z-10 shadow-sm">
                <tr>
                  {headers.map((h, i) => (
                    <th key={i} className="px-3 py-2 border-b border-r border-slate-300 font-bold text-slate-700 whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(1).map((row, i) => {
                  // Simple CSV split (doesn't handle quotes perfectly, but okay for outputs)
                  const cells = row.split(',');
                  return (
                    <tr key={i} className="hover:bg-slate-50 border-b border-slate-200">
                      {cells.map((c, j) => (
                        <td key={j} className="px-3 py-1.5 border-r border-slate-200 text-slate-600 whitespace-nowrap overflow-hidden text-ellipsis max-w-xs">
                          {c}
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      );
    }

    if (fileContent !== null) {
      return (
        <div className="flex flex-col h-full overflow-hidden bg-white">
          <Header />
          <div className="flex-1 overflow-auto bg-slate-50 p-3">
            <pre className="text-xs font-mono text-slate-800 whitespace-pre-wrap word-break-all">
              {fileContent}
            </pre>
          </div>
        </div>
      );
    }

    if (loadingContent) {
      return (
        <div className="flex flex-col h-full overflow-hidden bg-slate-50">
          <Header />
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
          </div>
        </div>
      );
    }

    // Default fallback for binary/large files
    return (
      <div className="flex flex-col h-full overflow-hidden bg-slate-50">
        <Header />
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-slate-600">
          <Database className="w-16 h-16 mb-4 text-slate-300" />
          <h3 className="text-lg font-bold text-slate-800 mb-2">Binary or Large File</h3>
          <p className="text-sm max-w-md mb-6">
            This file type ({ext || 'unknown'}) cannot be previewed directly in the browser. 
            Please download it to view its contents.
          </p>
          <a 
            href={downloadUrl} 
            download={selectedFile.name}
            className="px-4 py-2 bg-blue-600 text-white rounded-sm text-sm font-bold hover:bg-blue-700 shadow-sm"
          >
            Download {formatSize(selectedFile.size)}
          </a>
        </div>
      </div>
    );
  };

  return (
    <div className="h-full flex gap-2">
      {/* Sidebar */}
      <div className="w-64 flex flex-col bg-slate-50 border border-slate-300 shrink-0">
        <div className="p-2 border-b border-slate-300 bg-slate-200">
          <h2 className="font-bold text-slate-800 flex items-center gap-2 text-sm tracking-tight">
            <Folder className="w-4 h-4 text-slate-600" />
            ML Outputs
          </h2>
        </div>
        <div className="flex-1 overflow-y-auto py-2 custom-scrollbar">
          {loading ? (
            <div className="flex justify-center p-4">
              <Loader2 className="w-5 h-5 text-slate-400 animate-spin" />
            </div>
          ) : tree.length === 0 ? (
            <div className="p-4 text-sm text-slate-500 italic text-center">
              No artifacts found. Run the ML pipeline first.
            </div>
          ) : (
            renderTree(tree)
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 bg-slate-50 border border-slate-300 overflow-hidden relative">
        {renderContent()}
      </div>
    </div>
  );
};
