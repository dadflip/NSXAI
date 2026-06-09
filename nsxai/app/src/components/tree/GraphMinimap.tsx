import React, { useEffect, useRef, useState, useMemo } from 'react';
import * as d3 from 'd3';
import { Maximize2, Minimize2 } from 'lucide-react';
import { type Triple } from '../lib/core';

interface GraphMinimapProps {
  nodeUri: string;
  triples: Triple[];
  subjectsMap: Map<string, Triple[]>;
  shortLocal: (uri: string) => string;
  onNavigate?: (uri: string) => void;
}

export function GraphMinimap({ nodeUri, triples, subjectsMap, shortLocal, onNavigate }: GraphMinimapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [depth, setDepth] = useState(1);

  const localTriples = useMemo(() => {
    let currentLevelURIs = new Set([nodeUri]);
    const collectedTriples = new Set<Triple>();
    
    for (let i = 0; i < depth; i++) {
      const nextLevel = new Set<string>();
      for (const t of triples) {
        if (currentLevelURIs.has(t.subject) && !collectedTriples.has(t)) {
          collectedTriples.add(t);
          if (t.objectType === 'uri' || t.objectType === 'bnode' || t.objectType !== 'Literal' && t.objectType !== 'literal' && t.objectType !== 'typed-literal') {
             nextLevel.add(t.object);
          }
        }
      }
      currentLevelURIs = nextLevel;
      if (currentLevelURIs.size === 0) break;
    }
    return Array.from(collectedTriples);
  }, [triples, nodeUri, depth]);

  useEffect(() => {
    if (!containerRef.current) return;
    
    // Clear previous SVG
    containerRef.current.innerHTML = '';

    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight;

    // Build graph data
    const nodesMap = new Map<string, { id: string; group: number; label: string; isLiteral?: boolean }>();
    const links: { source: string; target: string; label: string }[] = [];

    // Central node
    const centralLabel = localTriples.find(t => t.predicate === 'http://www.w3.org/2000/01/rdf-schema#label' && t.subject === nodeUri)?.object || shortLocal(nodeUri);
    nodesMap.set(nodeUri, { id: nodeUri, group: 1, label: centralLabel });

    localTriples.forEach(t => {
      const isLit = t.objectType === 'literal' || t.objectType === 'typed-literal' || t.objectType === 'Literal';
      const objId = isLit ? `${t.predicate}_${t.object}_${t.subject}` : t.object;
      if (!nodesMap.has(objId)) {
        let objLabel = shortLocal(t.object);
        if (!isLit && subjectsMap.has(t.object)) {
          const l = subjectsMap.get(t.object)?.find(x => x.predicate === 'http://www.w3.org/2000/01/rdf-schema#label');
          if (l) objLabel = l.object;
        }
        nodesMap.set(objId, { 
          id: objId, 
          group: isLit ? 3 : 2, 
          label: isLit ? `"${t.object}"` : objLabel,
          isLiteral: isLit
        });
      }
      
      // Ensure subject is in nodesMap
      if (!nodesMap.has(t.subject)) {
        let subjLabel = shortLocal(t.subject);
        if (subjectsMap.has(t.subject)) {
          const l = subjectsMap.get(t.subject)?.find(x => x.predicate === 'http://www.w3.org/2000/01/rdf-schema#label');
          if (l) subjLabel = l.object;
        }
        nodesMap.set(t.subject, { id: t.subject, group: 2, label: subjLabel, isLiteral: false });
      }

      links.push({
        source: t.subject,
        target: objId,
        label: shortLocal(t.predicate)
      });
    });

    const nodesData = Array.from(nodesMap.values());
    const linksData = links.map(d => ({ ...d })); // copy for d3

    const svg = d3.select(containerRef.current)
      .append('svg')
      .attr('width', '100%')
      .attr('height', '100%')
      .attr('viewBox', [0, 0, width, height]);

    // Add zoom capabilities
    const g = svg.append('g');
    const zoom = d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.1, 4])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });
    svg.call(zoom);

    // Forces
    const simulation = d3.forceSimulation(nodesData as d3.SimulationNodeDatum[])
      .force('link', d3.forceLink(linksData).id((d: any) => d.id).distance(isExpanded ? 120 : 80))
      .force('charge', d3.forceManyBody().strength(isExpanded ? -300 : -200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide().radius(isExpanded ? 50 : 30));

    // Links
    const link = g.append('g')
      .selectAll('line')
      .data(linksData)
      .join('line')
      .attr('stroke', 'rgba(255,255,255,0.2)')
      .attr('stroke-width', 1.5);

    // Link labels
    const linkLabels = g.append('g')
      .selectAll('text')
      .data(linksData)
      .join('text')
      .attr('font-size', isExpanded ? '10px' : '8px')
      .attr('fill', 'rgba(255,255,255,0.4)')
      .attr('text-anchor', 'middle')
      .attr('dy', -2)
      .text((d: any) => d.label);

    // Nodes
    const node = g.append('g')
      .selectAll('g')
      .data(nodesData)
      .join('g')
      .call(d3.drag<any, any>()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended))
      .style('cursor', (d: any) => (d.group !== 3 && d.id !== nodeUri) ? 'pointer' : 'default')
      .on('click', (event, d: any) => {
          if (d.group !== 3 && d.id !== nodeUri && onNavigate) {
              onNavigate(d.id);
          }
      });

    node.append('circle')
      .attr('r', (d: any) => d.group === 1 ? (isExpanded ? 16 : 12) : (isExpanded ? 12 : 8))
      .attr('fill', (d: any) => d.group === 1 ? '#4ade80' : d.group === 2 ? '#60a5fa' : '#9ca3af')
      .attr('stroke', 'rgba(255,255,255,0.2)')
      .attr('stroke-width', 1.5);

    node.append('text')
      .attr('dx', isExpanded ? 16 : 12)
      .attr('dy', 4)
      .attr('font-size', isExpanded ? '12px' : '10px')
      .attr('fill', 'rgba(255,255,255,0.8)')
      .text((d: any) => d.label);

    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);

      linkLabels
        .attr('x', (d: any) => (d.source.x + d.target.x) / 2)
        .attr('y', (d: any) => (d.source.y + d.target.y) / 2);

      node
        .attr('transform', (d: any) => `translate(${d.x},${d.y})`);
    });

    function dragstarted(event: any, d: any) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    }

    function dragged(event: any, d: any) {
      d.fx = event.x;
      d.fy = event.y;
    }

    function dragended(event: any, d: any) {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null;
      d.fy = null;
    }

    return () => {
      simulation.stop();
    };
  }, [nodeUri, localTriples, subjectsMap, isExpanded]);

  return (
    <div className={`transition-all duration-500 overflow-hidden border border-white/10 ring-1 ring-white/5 shadow-2xl ${
      isExpanded 
        ? 'absolute inset-0 bg-[#0a0a0a]/95 backdrop-blur-3xl rounded-[2rem] z-50' 
        : 'absolute bottom-6 right-6 w-64 h-64 bg-[#0a0a0a]/80 backdrop-blur-md rounded-2xl z-20'
    }`}>
      <div className={`absolute top-0 left-0 w-full p-2 bg-gradient-to-b from-black/50 to-transparent flex items-center justify-between z-10 ${isExpanded ? 'p-6' : 'p-2'}`}>
        <div className="flex items-center gap-4">
          <span className="text-[10px] uppercase font-semibold tracking-wider text-neutral-400">Graphe Local</span>
          {isExpanded && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-neutral-500">Profondeur:</span>
              <input 
                type="range" 
                min="1" max="5" 
                value={depth} 
                onChange={(e) => setDepth(parseInt(e.target.value))}
                className="w-20 accent-emerald-500 h-1 bg-neutral-800 rounded-full appearance-none cursor-pointer"
              />
              <span className="text-[10px] text-neutral-300 font-mono w-2">{depth}</span>
            </div>
          )}
        </div>
        <button 
          onClick={() => setIsExpanded(!isExpanded)}
          className="p-1.5 rounded-full hover:bg-white/10 text-neutral-400 hover:text-white transition-colors"
          title={isExpanded ? "Réduire" : "Agrandir"}
        >
          {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
        </button>
      </div>
      <div ref={containerRef} className="w-full h-full" />
    </div>
  );
}

