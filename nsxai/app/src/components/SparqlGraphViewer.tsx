import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import { Maximize2, ZoomIn, ZoomOut, Download } from 'lucide-react';

interface SparqlGraphViewerProps {
  data: any;
}

export const SparqlGraphViewer: React.FC<SparqlGraphViewerProps> = ({ data }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    if (!data || !data.results || !data.results.bindings || data.results.bindings.length === 0) return;
    if (!svgRef.current || !containerRef.current) return;

    const bindings = data.results.bindings;
    const vars = data.head.vars || [];
    
    // Convert bindings to generic graph format
    const nodesMap = new Map<string, any>();
    const links: any[] = [];
    
    // We expect SPARQL query to return URI nodes. If we have exactly 3 vars ?s ?p ?o, we use that.
    // If not, we just iterate bindings and for each row, we treat unqiue URIs as nodes, 
    // and if there are 2 URIs, link them. Or we just link consecutive variables.
    
    let isSPO = vars.includes('s') && vars.includes('p') && vars.includes('o');
    let isSubObj = vars.length >= 2;

    bindings.forEach((row: any) => {
        if (isSPO) {
            const s = row['s'];
            const p = row['p'];
            const o = row['o'];
            
            if (s && o) {
                if (!nodesMap.has(s.value)) nodesMap.set(s.value, { id: s.value, type: s.type });
                if (o.type === 'uri' || o.type === 'bnode') {
                   if (!nodesMap.has(o.value)) nodesMap.set(o.value, { id: o.value, type: o.type });
                   links.push({ source: s.value, target: o.value, label: p ? (p.value.split(/[/#]/).pop() || p.value) : '' });
                } else {
                   // literal node
                   const litId = `${s.value}_${p ? p.value : 'lit'}_${o.value}`;
                   if (!nodesMap.has(litId)) nodesMap.set(litId, { id: litId, label: o.value, type: 'literal' });
                   links.push({ source: s.value, target: litId, label: p ? (p.value.split(/[/#]/).pop() || p.value) : '' });
                }
            }
        } else if (isSubObj) {
            // Find all URIs in this row
            const uris = Object.values(row).filter((v: any) => v && (v.type === 'uri' || v.type === 'bnode'));
            for (let i = 0; i < uris.length; i++) {
                const u = uris[i] as any;
                if (!nodesMap.has(u.value)) nodesMap.set(u.value, { id: u.value, type: u.type });
                if (i > 0) {
                   const prev = uris[i - 1] as any;
                   links.push({ source: prev.value, target: u.value, label: '' });
                }
            }
        }
    });

    const nodes = Array.from(nodesMap.values());
    if (nodes.length === 0) return;

    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const g = svg.append("g");

    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on("zoom", (event) => g.attr("transform", event.transform));

    svg.call(zoom);

    // D3 Force Simulation
    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((d: any) => d.id).distance(150))
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius(40));

    // Arrow marker
    svg.append("defs").selectAll("marker")
      .data(["end"])
      .enter().append("marker")
        .attr("id", "arrow")
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 25)
        .attr("refY", 0)
        .attr("markerWidth", 8)
        .attr("markerHeight", 8)
        .attr("orient", "auto")
      .append("path")
        .attr("fill", "#ccc")
        .attr("d", "M0,-5L10,0L0,5");

    const link = g.append("g")
      .selectAll("g")
      .data(links)
      .enter().append("g");

    const linkPath = link.append("line")
      .attr("stroke", "#ccc")
      .attr("stroke-width", 1.5)
      .attr("marker-end", "url(#arrow)");

    const linkLabel = link.append("text")
      .attr("font-size", "10px")
      .attr("fill", "#666")
      .attr("text-anchor", "middle")
      .attr("dy", -5)
      .text((d: any) => d.label);

    const node = g.append("g")
      .selectAll("g")
      .data(nodes)
      .enter().append("g")
      .call(d3.drag<any, any>()
        .on("start", (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on("drag", (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on("end", (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        }));

    node.append("circle")
      .attr("r", (d: any) => d.type === 'literal' ? 5 : 12)
      .attr("fill", (d: any) => {
          if (d.type === 'literal') return '#e2e8f0';
          if (d.type === 'bnode') return '#cbd5e1';
          return '#6366f1';
      })
      .attr("stroke", "#fff")
      .attr("stroke-width", 2);

    node.append("text")
      .attr("dy", 20)
      .attr("text-anchor", "middle")
      .attr("font-size", "10px")
      .attr("fill", "#333")
      .text((d: any) => {
         if (d.type === 'literal') return d.label;
         return d.id.split(/[/#]/).pop() || d.id;
      });

    simulation.on("tick", () => {
      linkPath
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);

      linkLabel
        .attr("x", (d: any) => (d.source.x + d.target.x) / 2)
        .attr("y", (d: any) => (d.source.y + d.target.y) / 2);

      node
        .attr("transform", (d: any) => `translate(${d.x},${d.y})`);
    });

  }, [data, isFullscreen]);

  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen);
  };

  return (
    <div 
      className={`relative bg-neutral-950 rounded-lg border border-neutral-800 overflow-hidden ${
        isFullscreen ? 'fixed inset-0 z-50 bg-neutral-900' : 'w-full h-[500px]'
      }`} 
      ref={containerRef}
    >
      <div className="absolute top-4 right-4 flex gap-2 z-10">
          <button 
            onClick={toggleFullscreen}
            className="p-2 bg-neutral-900 rounded-md shadow-sm border border-neutral-800 hover:bg-neutral-800"
            title={isFullscreen ? "Réduire" : "Plein écran"}
          >
             <Maximize2 className="w-4 h-4 text-neutral-600" />
          </button>
      </div>
      <svg ref={svgRef} className="w-full h-full cursor-grab active:cursor-grabbing outline-none" />
    </div>
  );
};
