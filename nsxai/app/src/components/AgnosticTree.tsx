import React, { useState, useEffect } from 'react';
import { ChevronRight, ChevronDown, Layers, Box, Link, Circle, Loader2, Search, BrainCircuit } from 'lucide-react';
import { fetchAllEntities, fetchAgnosticChildren } from '../lib/sparqlQueries';
import { fetchApi } from '../lib/apiClient';

export function getCategoryInfo(types: string[] = []): { category: string, Icon: any, color: string, order: number } {
  const tStr = types.join(' ');
  if (tStr.includes('Class')) return { category: 'Classes', Icon: Layers, color: 'text-slate-700', order: 1 };
  if (tStr.includes('Property')) return { category: 'Properties', Icon: Link, color: 'text-slate-700', order: 2 };
  if (tStr.includes('NamedIndividual') || types.length > 0) return { category: 'Individuals', Icon: Box, color: 'text-slate-700', order: 3 };
  return { category: 'Others (Generic)', Icon: Circle, color: 'text-slate-500', order: 4 };
}

const TreeNode: React.FC<{
  node: { uri: string, label: string, types?: string[], predicate?: string },
  level: number,
  selectedUri: string | null,
  onSelect: (uri: string) => void,
  mlTopics: Map<string, string>
}> = ({ node, level, selectedUri, onSelect, mlTopics }) => {
  const [expanded, setExpanded] = useState(false);
  const [children, setChildren] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const isSelected = selectedUri === node.uri;

  const toggleExpand = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (expanded) {
      setExpanded(false);
      return;
    }
    
    setLoading(true);
    try {
      const childrenData = await fetchAgnosticChildren(node.uri);
      setChildren(childrenData);
      setExpanded(true);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const { Icon, color } = getCategoryInfo(node.types);

  return (
    <div className="select-none">
      <div 
        className={`flex items-center gap-1.5 py-0.5 px-1 cursor-pointer ${isSelected ? 'bg-blue-100 text-blue-900 border border-blue-300 font-bold shadow-none' : 'hover:bg-slate-100 text-slate-800 border border-transparent'}`}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
        onClick={() => onSelect(node.uri)}
      >
        <span onClick={toggleExpand} className="p-0.5 hover:bg-slate-200 rounded-sm">
          {loading ? <Loader2 className="w-3 h-3 animate-spin text-slate-500" /> :
           expanded ? <ChevronDown className="w-3 h-3 text-slate-600" /> : <ChevronRight className="w-3 h-3 text-slate-600" />}
        </span>
        <span className="text-xs truncate font-mono" title={node.uri}>{node.label}</span>
        {(() => {
          const localName = node.uri.split(/[/#]/).pop();
          let conf = localName ? mlTopics.get(localName) : undefined;
          if (!conf && node.types) {
            for (const t of node.types) {
              const tl = t.split(/[/#]/).pop();
              if (tl && mlTopics.has(tl)) {
                conf = mlTopics.get(tl);
                break;
              }
            }
          }
          if (!conf) return null;
          
          let brainColor = "text-green-600";
          if (conf === "Moderate") brainColor = "text-yellow-600";
          if (conf === "Weak") brainColor = "text-slate-400";
          
          return (
            <BrainCircuit className={`w-3.5 h-3.5 ml-1 ${brainColor} shrink-0`} title={`AI Recommendations available (Confidence: ${conf})`} />
          );
        })()}
      </div>
      
      {expanded && children.length > 0 && (
        <div>
          {children.map(child => (
            <TreeNode 
              key={child.uri + child.predicate} 
              node={child} 
              level={level + 1} 
              selectedUri={selectedUri} 
              onSelect={onSelect} 
              mlTopics={mlTopics}
            />
          ))}
        </div>
      )}
      {expanded && children.length === 0 && (
        <div className="text-[10px] text-slate-500 italic py-0.5" style={{ paddingLeft: `${(level + 1) * 16 + 8}px` }}>
          No children for this entity.
        </div>
      )}
    </div>
  );
};

interface AgnosticTreeProps {
  onSelect: (uri: string) => void;
  selectedUri: string | null;
  refreshTrigger?: number; // Pass a counter to force reload
}

export const AgnosticTree: React.FC<AgnosticTreeProps> = ({ onSelect, selectedUri, refreshTrigger = 0 }) => {
  const [loadingRoots, setLoadingRoots] = useState(false);
  const [groupedRoots, setGroupedRoots] = useState<Record<string, any[]>>({});
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({
    'Classes': true,
    'Properties': true,
    'Individuals': true
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [mlTopics, setMlTopics] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    fetchApi('topics')
        .then(res => res.json())
        .then(data => {
            const topicsData = data.topics || data;
            if (topicsData) {
                if (Array.isArray(topicsData)) {
                    const map = new Map<string, string>();
                    topicsData.forEach((t: string) => map.set(t, "Moderate"));
                    setMlTopics(map);
                } else {
                    setMlTopics(new Map(Object.entries(topicsData)));
                }
            }
        })
        .catch(console.error);

    setLoadingRoots(true);
    fetchAllEntities(refreshTrigger > 0)
      .then(entities => {
        const groups: Record<string, any[]> = {};
        entities.forEach(e => {
          const { category } = getCategoryInfo(e.types);
          if (!groups[category]) groups[category] = [];
          groups[category].push(e);
        });
        setGroupedRoots(groups);
      })
      .catch(console.error)
      .finally(() => setLoadingRoots(false));
  }, [refreshTrigger]);

  if (loadingRoots) {
    return (
      <div className="p-2 flex items-center gap-2 text-slate-600 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading knowledge base...
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-slate-50">
      <div className="p-1 border-b border-slate-300 bg-slate-200">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-white border border-slate-300 rounded-sm pl-8 pr-2 py-1 text-xs text-slate-800 outline-none focus:border-blue-400"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-1">
        {Object.entries(groupedRoots)
          .sort((a, b) => getCategoryInfo(a[1][0]?.types).order - getCategoryInfo(b[1][0]?.types).order)
          .map(([category, nodes]: [string, any[]]) => {
            const filteredNodes = searchQuery 
              ? nodes.filter(n => n.label?.toLowerCase().includes(searchQuery.toLowerCase()) || n.uri.toLowerCase().includes(searchQuery.toLowerCase()))
              : nodes;

            if (filteredNodes.length === 0) return null;

            return (
              <div key={category} className="mb-2">
                <div 
                  className="flex items-center gap-1.5 py-1 px-1 cursor-pointer hover:bg-slate-100 text-slate-800 font-bold text-xs select-none border-b border-slate-200 mb-1"
                  onClick={() => setExpandedGroups(prev => ({...prev, [category]: !prev[category]}))}
                >
                  {expandedGroups[category] ? <ChevronDown className="w-3 h-3 text-slate-600" /> : <ChevronRight className="w-3 h-3 text-slate-600" />}
                  {category} <span className="text-slate-500 font-normal">({filteredNodes.length})</span>
                </div>
                {expandedGroups[category] && (
                  <div className="pl-1">
                    {filteredNodes.map((rc: any) => (
                      <TreeNode 
                        key={rc.uri} 
                        node={rc} 
                        level={0} 
                        selectedUri={selectedUri} 
                        onSelect={onSelect} 
                        mlTopics={mlTopics}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
};
