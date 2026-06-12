import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';

interface GraphEdge {
    source: string;
    predicate: string;
    target: string;
}

interface LocalGraphProps {
    edges: GraphEdge[];
    centerUri: string;
    onNodeClick?: (uri: string) => void;
    recommendations?: any[];
    inferenceMode?: boolean;
}

interface NodeData extends d3.SimulationNodeDatum {
    id: string;
    label: string;
    isCenter: boolean;
    isVirtual?: boolean;
}

interface LinkData extends d3.SimulationLinkDatum<NodeData> {
    predicate: string;
    label: string;
    isVirtual?: boolean;
    score?: number;
}

function extractLabel(uri: string) {
    return uri.split(/[/#]/).pop() || uri;
}

export const LocalGraph: React.FC<LocalGraphProps> = ({ edges, centerUri, onNodeClick, recommendations, inferenceMode }) => {
    const svgRef = useRef<SVGSVGElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

    // Handle resize
    useEffect(() => {
        if (!containerRef.current) return;
        const observer = new ResizeObserver((entries) => {
            if (entries[0]) {
                const { width, height } = entries[0].contentRect;
                setDimensions({ width, height: height || 600 });
            }
        });
        observer.observe(containerRef.current);
        return () => observer.disconnect();
    }, []);

    useEffect(() => {
        if (!svgRef.current) return;
        // Even if edges are empty, we might have recommendations to show in inference mode
        if (edges.length === 0 && (!inferenceMode || !recommendations || recommendations.length === 0)) {
            d3.select(svgRef.current).selectAll('*').remove();
            return;
        }

        const { width, height } = dimensions;
        
        // Prepare data
        const nodeMap = new Map<string, NodeData>();
        
        // Make sure center node exists even if edges are empty
        if (centerUri && !nodeMap.has(centerUri)) {
            nodeMap.set(centerUri, { id: centerUri, label: extractLabel(centerUri), isCenter: true });
        }

        edges.forEach(edge => {
            if (!nodeMap.has(edge.source)) {
                nodeMap.set(edge.source, { id: edge.source, label: extractLabel(edge.source), isCenter: edge.source === centerUri });
            }
            if (!nodeMap.has(edge.target)) {
                nodeMap.set(edge.target, { id: edge.target, label: extractLabel(edge.target), isCenter: edge.target === centerUri });
            }
        });

        const nodes: NodeData[] = Array.from(nodeMap.values());
        const links: LinkData[] = edges.map(e => ({
            source: e.source,
            target: e.target,
            predicate: e.predicate,
            label: extractLabel(e.predicate)
        }));

        if (inferenceMode && recommendations && recommendations.length > 0) {
            recommendations.forEach((rec, idx) => {
                if (rec.raw_path && rec.raw_relations && rec.raw_path.length > 0) {
                    const path = rec.raw_path;
                    const rels = rec.raw_relations;
                    
                    const resolveNodeId = (raw: string, isTarget: boolean) => {
                        if (extractLabel(raw) === extractLabel(centerUri)) return centerUri;
                        return isTarget ? `virtual-${raw}-${idx}` : `virtual-${raw}`;
                    };

                    for (let i = 0; i < path.length; i++) {
                        const isTarget = i === path.length - 1;
                        const nodeId = resolveNodeId(path[i], isTarget);
                        
                        if (!nodeMap.has(nodeId) && nodeId !== centerUri) {
                            const vNode: NodeData = { 
                                id: nodeId, 
                                label: extractLabel(path[i]), 
                                isCenter: false, 
                                isVirtual: true 
                            };
                            nodeMap.set(nodeId, vNode);
                            nodes.push(vNode);
                        }
                    }
                    
                    for (let i = 0; i < rels.length; i++) {
                        const sourceId = resolveNodeId(path[i], false);
                        const targetId = resolveNodeId(path[i+1], i + 1 === path.length - 1);
                        
                        let predLabel = extractLabel(rels[i]);
                        const isRev = predLabel.includes('(rev)');
                        if (isRev) {
                            predLabel = '← ' + predLabel.replace('(rev)', '');
                        }

                        links.push({
                            source: sourceId,
                            target: targetId,
                            predicate: rels[i],
                            label: predLabel,
                            isVirtual: true,
                            score: i === rels.length - 1 ? rec.neurosymbolic_score : undefined
                        });
                    }
                } else {
                    const targetId = `virtual-${rec.target}-${idx}`;
                    if (!nodeMap.has(targetId)) {
                        const vNode: NodeData = { id: targetId, label: extractLabel(rec.target), isCenter: false, isVirtual: true };
                        nodeMap.set(targetId, vNode);
                        nodes.push(vNode);
                    }
                    links.push({
                        source: centerUri,
                        target: targetId,
                        predicate: rec.key_relation,
                        label: extractLabel(rec.key_relation),
                        isVirtual: true,
                        score: rec.neurosymbolic_score
                    });
                }
            });
        }

        const svg = d3.select(svgRef.current);
        svg.selectAll('*').remove();

        svg.attr('viewBox', [0, 0, width, height]);

        // Define arrow markers for graph links
        svg.append('defs').selectAll('marker')
            .data(['end', 'end-virtual'])
            .enter().append('marker')
            .attr('id', String)
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 22)
            .attr('refY', 0)
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path')
            .attr('fill', d => d === 'end-virtual' ? '#8b5cf6' : '#9ca3af')
            .attr('d', 'M0,-5L10,0L0,5');

        const g = svg.append('g');

        // Setup Zoom
        const zoom = d3.zoom<SVGSVGElement, unknown>()
            .scaleExtent([0.1, 4])
            .on('zoom', (event) => {
                g.attr('transform', event.transform);
            });
        
        svg.call(zoom as any);
        // Initialize camera to center of the viewport
        svg.call(zoom.transform as any, d3.zoomIdentity.translate(width / 2, height / 2));

        const simulation = d3.forceSimulation<NodeData>(nodes)
            .force('link', d3.forceLink<NodeData, LinkData>(links).id(d => d.id).distance(120))
            .force('charge', d3.forceManyBody().strength(-400))
            .force('center', d3.forceCenter(0, 0))
            .force('collide', d3.forceCollide().radius(40));

        // Links
        const link = g.append('g')
            .selectAll('line')
            .data(links)
            .join('line')
            .attr('stroke', d => d.isVirtual ? '#8b5cf6' : '#d1d5db')
            .attr('stroke-width', d => d.isVirtual ? 2 : 1.5)
            .attr('stroke-dasharray', d => d.isVirtual ? '4,4' : null)
            .attr('marker-end', d => d.isVirtual ? 'url(#end-virtual)' : 'url(#end)');

        // Edge labels
        const edgeLabels = g.append('g')
            .selectAll('text')
            .data(links)
            .join('text')
            .attr('font-size', '10px')
            .attr('fill', d => d.isVirtual ? '#8b5cf6' : '#6b7280')
            .attr('text-anchor', 'middle')
            .attr('dy', -4)
            .text(d => d.isVirtual && d.score !== undefined ? `${d.label} (${(d.score * 100).toFixed(0)}%)` : d.label);

        // Nodes
        const node = g.append('g')
            .selectAll('g')
            .data(nodes)
            .join('g')
            .call(d3.drag<any, NodeData>()
                .on('start', dragstarted)
                .on('drag', dragged)
                .on('end', dragended) as any
            )
            .on('click', (event, d) => {
                event.stopPropagation();
                if (!d.isVirtual && onNodeClick) onNodeClick(d.id);
            });

        // Node shapes
        node.each(function(d) {
            const el = d3.select(this);
            if (d.isCenter && d.id !== 'GLOBAL') {
                // Red rounded square for the center node
                el.append('rect')
                  .attr('x', -14)
                  .attr('y', -14)
                  .attr('width', 28)
                  .attr('height', 28)
                  .attr('rx', 6)
                  .attr('fill', '#ef4444')
                  .attr('stroke', '#ffffff')
                  .attr('stroke-width', 2.5)
                  .attr('class', 'cursor-pointer hover:stroke-slate-300 transition-colors');
            } else if (d.isVirtual) {
                // Purple circle with dashed border for virtual nodes
                el.append('circle')
                  .attr('r', 10)
                  .attr('fill', '#ffffff')
                  .attr('stroke', '#8b5cf6')
                  .attr('stroke-width', 2)
                  .attr('stroke-dasharray', '3,3');
                
                el.append('circle')
                  .attr('r', 4)
                  .attr('fill', '#8b5cf6');
            } else {
                // Blue circle for other nodes
                el.append('circle')
                  .attr('r', 8)
                  .attr('fill', '#3b82f6')
                  .attr('stroke', '#fff')
                  .attr('stroke-width', 1.5)
                  .attr('class', 'cursor-pointer hover:stroke-blue-300 transition-colors');
            }
        });

        // Node labels
        node.append('text')
            .text(d => d.label)
            .attr('x', 14)
            .attr('y', 4)
            .attr('fill', d => d.isVirtual ? '#8b5cf6' : '#374151')
            .attr('font-size', '12px')
            .attr('class', 'select-none pointer-events-none');

        simulation.on('tick', () => {
            link
                .attr('x1', d => (d.source as NodeData).x!)
                .attr('y1', d => (d.source as NodeData).y!)
                .attr('x2', d => (d.target as NodeData).x!)
                .attr('y2', d => (d.target as NodeData).y!);

            edgeLabels
                .attr('x', d => ((d.source as NodeData).x! + (d.target as NodeData).x!) / 2)
                .attr('y', d => ((d.source as NodeData).y! + (d.target as NodeData).y!) / 2);

            node
                .attr('transform', d => `translate(${d.x},${d.y})`);
        });

        // Drag functions
        function dragstarted(event: any, d: NodeData) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }

        function dragged(event: any, d: NodeData) {
            d.fx = event.x;
            d.fy = event.y;
        }

        function dragended(event: any, d: NodeData) {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }

        return () => {
            simulation.stop();
        };
    }, [edges, dimensions, centerUri, onNodeClick, inferenceMode, recommendations]);

    return (
        <div ref={containerRef} className="w-full h-full relative">
            <svg ref={svgRef} className="w-full h-full bg-white" />
            {edges.length === 0 && (
                <div className="absolute inset-0 flex items-center justify-center text-slate-500 bg-white font-medium text-sm">
                    No relations found at this depth.
                </div>
            )}
        </div>
    );
};
