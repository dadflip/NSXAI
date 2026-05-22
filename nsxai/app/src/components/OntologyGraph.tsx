import React, { useEffect, useRef, useState, useMemo } from 'react';
import * as d3 from 'd3';
import { ZoomIn, ZoomOut, Maximize, Target, Pause, Play, Settings2, Search, Route, Database } from 'lucide-react';
import { apiUrl } from '../lib/api';

export default function OntologyGraph({ 
  triples, 
  getShortUri,
  nodeColorScale,
  nodeShapeScale,
  linkColorScale,
  selectedNodeId,
  setSelectedNodeId
}: { 
  triples: any[], 
  getShortUri: (u: string) => string,
  nodeColorScale: d3.ScaleOrdinal<string, string>,
  nodeShapeScale: d3.ScaleOrdinal<string, d3.SymbolType>,
  linkColorScale: d3.ScaleOrdinal<string, string>,
  selectedNodeId: string | null,
  setSelectedNodeId: React.Dispatch<React.SetStateAction<string | null>>
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [hoveredNode, setHoveredNode] = useState<any>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isPlaying, setIsPlaying] = useState(true);
  const [layoutMode, setLayoutMode] = useState<'spread' | 'force' | 'spread' | 'compact' | 'circle' | 'layered'>('spread');
  const [showSettings, setShowSettings] = useState(false);
  const [hideIsolated, setHideIsolated] = useState(false);
  const [hiddenNodeGroups, setHiddenNodeGroups] = useState<Set<string>>(new Set());
  const [hiddenPredicates, setHiddenPredicates] = useState<Set<string>>(new Set());
  const [hideInferredLinks, setHideInferredLinks] = useState(false);

  const [pathFindingMode, setPathFindingMode] = useState(false);
  const [pathStartNodeId, setPathStartNodeId] = useState<string | null>(null);
  const [pathEndNodeId, setPathEndNodeId] = useState<string | null>(null);
  const [shortestPath, setShortestPath] = useState<any | null>(null);
  const simRef = useRef<any>(null);

  const pathFinderState = useRef({ mode: false, start: null as string | null, end: null as string | null });
  useEffect(() => {
      pathFinderState.current = { mode: pathFindingMode, start: pathStartNodeId, end: pathEndNodeId };
  }, [pathFindingMode, pathStartNodeId, pathEndNodeId]);

  const [inferences, setInferences] = useState<Set<string>>(new Set());
  
  useEffect(() => {
    fetch(apiUrl('/api/reasoner/inferences'))
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const ct = r.headers.get("content-type");
        if (ct && ct.includes("application/json")) return r.json();
        return [];
      })
      .then(d => setInferences(new Set(d)))
      .catch(err => console.error("Error fetching inferences in graph viewer:", err));
  }, []);

  const { allNodes, allPredicates, allNodeGroups } = useMemo(() => {
    if (!triples) return { allNodes: [], allPredicates: new Set<string>(), allNodeGroups: new Set<string>() };
    const nodes: any[] = [];
    const nodeMap = new Map();
    const predicates = new Set<string>();
    const typeMap = new Map<string, string[]>(); // Map node uri -> array of rdf types

    triples.forEach(t => {
       if (t.predicate === 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type' && t.objectType !== 'Literal') {
           const shortType = getShortUri(t.object);
           // Prevent 'NamedIndividual' from overwriting actual interesting types
           if (t.object !== 'http://www.w3.org/2002/07/owl#NamedIndividual') {
               if (!typeMap.has(t.subject)) typeMap.set(t.subject, []);
               // Don't add dupe types
               if (!typeMap.get(t.subject)!.includes(shortType)) {
                   typeMap.get(t.subject)!.push(shortType);
               }
           }
       }
       predicates.add(t.predicate);
    });

    const addNode = (id: string, originalUri?: string, fallbackGroup: string = 'Inconnu') => {
      if (!nodeMap.has(id)) {
        let group = fallbackGroup;
        if (fallbackGroup !== 'Literal') {
            const types = typeMap.get(id);
            if (types && types.length > 0) {
                group = types[0]; // just take first inferred type for grouping/color
            }
        }
        const node = { id, group, label: getShortUri(id), uri: originalUri || id };
        nodes.push(node);
        nodeMap.set(id, node);
      }
      return nodeMap.get(id);
    };

    triples.forEach(t => {
       addNode(t.subject, t.subject, 'Inconnu');
       let oStr = t.object;
       
       if (t.objectType === 'Literal') {
           const literalId = `${t.subject}-${t.predicate}-${t.object}`;
           addNode(literalId, t.object, 'Literal');
           if (t.datatype && t.datatype !== 'http://www.w3.org/2001/XMLSchema#string') {
               oStr = `"${t.object}"^^<${t.datatype}>`;
           }
       } else {
           addNode(t.object, t.object, 'Inconnu');
       }
       t.inferred = inferences.has(`${t.subject}|${t.predicate}|${oStr}`) || inferences.has(`${t.subject}|${t.predicate}|${t.object}`);
    });

    const groups = new Set<string>();
    nodes.forEach(n => groups.add(n.group));

    return { allNodes: nodes, allPredicates: predicates, allNodeGroups: groups };
  }, [triples, getShortUri, inferences]);

  const searchResults = useMemo(() => {
     if (!searchQuery.trim()) return [];
     const q = searchQuery.toLowerCase();
     return allNodes.filter(n => n.label.toLowerCase().includes(q) || n.uri.toLowerCase().includes(q)).slice(0, 10);
  }, [searchQuery, allNodes]);

  const calculateShortestPath = (startId: string, endId: string) => {
      const adjacencyList = new Map<string, {target: string, type: string}[]>();
      
      const addEdge = (u: string, v: string, type: string) => {
          if (!adjacencyList.has(u)) adjacencyList.set(u, []);
          adjacencyList.get(u)!.push({target: v, type});
          if (!adjacencyList.has(v)) adjacencyList.set(v, []);
          adjacencyList.get(v)!.push({target: u, type});
      };

      triples?.forEach(t => {
         if (t.objectType === 'Literal') {
             const targetId = `${t.subject}-${t.predicate}-${t.object}`;
             addEdge(t.subject, targetId, getShortUri(t.predicate));
         } else {
             addEdge(t.subject, t.object, getShortUri(t.predicate));
         }
      });

      const queue = [startId];
      const visited = new Set<string>([startId]);
      const cameFrom = new Map<string, {node: string, type: string}>();
      
      let found = false;
      while (queue.length > 0) {
         const current = queue.shift()!;
         if (current === endId) {
            found = true;
            break;
         }
         
         const neighbors = adjacencyList.get(current) || [];
         for (const neighbor of neighbors) {
            if (!visited.has(neighbor.target)) {
               visited.add(neighbor.target);
               cameFrom.set(neighbor.target, {node: current, type: neighbor.type});
               queue.push(neighbor.target);
            }
         }
      }
      
      if (!found) return null;
      
      const pathNodes = [];
      const pathLinks = [];
      let curr = endId;
      while (curr !== startId) {
         pathNodes.unshift(curr);
         const prev = cameFrom.get(curr)!;
         // Note: the direction might be reversed visually, but for highlighting it doesn't matter much
         pathLinks.unshift({source: prev.node, target: curr, type: prev.type});
         curr = prev.node;
      }
      pathNodes.unshift(startId);
      return {nodes: pathNodes, links: pathLinks};
  };

  useEffect(() => {
      if (pathStartNodeId && pathEndNodeId) {
          const path = calculateShortestPath(pathStartNodeId, pathEndNodeId);
          setShortestPath(path);
      } else {
          setShortestPath(null);
      }
  }, [pathStartNodeId, pathEndNodeId, triples, allNodes]);

  useEffect(() => {
    if (!simRef.current) return;
    
    const width = containerRef.current?.clientWidth || 1000;
    const height = 650;

    let linkDistance = 120;
    let chargeStrength = -400;
    let collideRadius = 40;

    if (layoutMode === 'compact') {
      linkDistance = 60;
      chargeStrength = -150;
      collideRadius = 25;
      simRef.current.force('r', null);
      simRef.current.force('y', null);
      simRef.current.force('x', null);
    } else if (layoutMode === 'spread') {
      linkDistance = 250;
      chargeStrength = -800;
      collideRadius = 60;
      simRef.current.force('r', null);
      simRef.current.force('y', null);
      simRef.current.force('x', null);
    } else if (layoutMode === 'circle') {
      linkDistance = 50;
      chargeStrength = -150;
      collideRadius = 20;
      simRef.current.force('r', d3.forceRadial(Math.min(width, height) / 2.5, width / 2, height / 2).strength(1));
      simRef.current.force('y', null);
      simRef.current.force('x', null);
    } else if (layoutMode === 'layered') {
      linkDistance = 100;
      chargeStrength = -300;
      collideRadius = 30;
      simRef.current.force('r', null);
      simRef.current.force('y', null); // Generic layered is hard without generic groups, just null it for now
      simRef.current.force('x', d3.forceX(width / 2).strength(0.1));
    } else {
      simRef.current.force('r', null);
      simRef.current.force('y', null);
      simRef.current.force('x', null);
    }

    simRef.current.force('link').distance(linkDistance);
    simRef.current.force('charge').strength(chargeStrength);
    simRef.current.force('collide').radius(collideRadius);
    simRef.current.alpha(1).restart();
    setIsPlaying(true);
  }, [layoutMode]);

  useEffect(() => {
    if (!triples || !svgRef.current || !containerRef.current) return;

    const width = containerRef.current.clientWidth || 1000;
    const height = 650; 

    // Preserve previous positions if they exist
    const oldNodes = simRef.current ? new Map(simRef.current.nodes().map((n: any) => [n.id, n])) : new Map();
    
    const nodes = allNodes.map((d: any) => {
        const old = oldNodes.get(d.id);
        if (old) {
            return { ...d, x: old.x, y: old.y, vx: old.vx, vy: old.vy };
        }
        return { ...d };
    });
    
    const links: any[] = [];
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const seenLinks = new Set<string>();

    const addUniqueLink = (source: string, target: string, type: string, category: string, inferred: boolean = false) => {
        const key = `${source}-${target}-${type}-${category}`;
        if (seenLinks.has(key)) return;
        if (nodeMap.has(source) && nodeMap.has(target)) {
            links.push({ source, target, type, category, inferred });
            seenLinks.add(key);
        }
    };

    triples.forEach(t => {
      const category = t.predicate;
      if (t.objectType === 'Literal') {
         const targetId = `${t.subject}-${t.predicate}-${t.object}`;
         addUniqueLink(t.subject, targetId, getShortUri(t.predicate), category, t.inferred);
      } else {
         addUniqueLink(t.subject, t.object, getShortUri(t.predicate), category, t.tbox ? false : t.inferred);
      }
    });

    let finalNodes = nodes.filter((n: any) => {
        if (hiddenNodeGroups.has(n.group)) return false;
        return true;
    });

    let finalLinks = links.filter((l: any) => {
        if (hiddenPredicates.has(l.category)) return false;
        if (hideInferredLinks && l.inferred) return false;
        return true;
    });
    
    // Filter out links whose source or target nodes were hidden
    const visibleNodeIds = new Set(finalNodes.map((n: any) => n.id));
    finalLinks = finalLinks.filter((l: any) => visibleNodeIds.has(l.source) && visibleNodeIds.has(l.target));

    if (hideIsolated) {
        const coreConnectedIds = new Set<string>();
        const nonLiteralIds = new Set(finalNodes.filter((n: any) => n.group !== 'literal').map((n: any) => n.id));

        finalLinks.forEach((l: any) => {
            if (nonLiteralIds.has(l.source) && nonLiteralIds.has(l.target)) {
                coreConnectedIds.add(l.source);
                coreConnectedIds.add(l.target);
            }
        });

        const keptNodeIds = new Set<string>(coreConnectedIds);
        
        finalLinks.forEach((l: any) => {
            if (coreConnectedIds.has(l.source) && !nonLiteralIds.has(l.target)) {
                keptNodeIds.add(l.target);
            }
            if (coreConnectedIds.has(l.target) && !nonLiteralIds.has(l.source)) {
                keptNodeIds.add(l.source);
            }
        });

        finalNodes = finalNodes.filter((n: any) => keptNodeIds.has(n.id));
        finalLinks = finalLinks.filter((l: any) => keptNodeIds.has(l.source) && keptNodeIds.has(l.target));
    }

    const linkPairs = new Map<string, any[]>();
    finalLinks.forEach(l => {
        const p1 = l.source;
        const p2 = l.target;
        const key = p1 < p2 ? `${p1}-${p2}` : `${p2}-${p1}`;
        if (!linkPairs.has(key)) linkPairs.set(key, []);
        linkPairs.get(key)!.push(l);
    });

    finalLinks.forEach(l => {
        const p1 = l.source;
        const p2 = l.target;
        const key = p1 < p2 ? `${p1}-${p2}` : `${p2}-${p1}`;
        const pairLinks = linkPairs.get(key)!;
        l.linkNum = pairLinks.indexOf(l);
        l.totalLinks = pairLinks.length;
    });

    const currentTransform = d3.zoomTransform(svgRef.current as any);

    d3.select(svgRef.current).selectAll('*').remove();

    const svg = d3.select(svgRef.current)
      .attr('viewBox', [0, 0, width, height])
      .on('click', (event) => {
         // If click is on the SVG background itself, deselect
         if (event.target === svgRef.current) {
            setSelectedNodeId(null);
            setPathStartNodeId(null);
            setPathEndNodeId(null);
         }
      });

    const g = svg.append('g');
    g.attr('transform', currentTransform as any);

    const zoom = d3.zoom()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });

    svg.call(zoom as any)
       .on("dblclick.zoom", null); // Disable double click zoom
    
    // Restore current zoom state
    svg.call(zoom.transform as any, currentTransform);
    
    (svg.node() as any).__zoomObj = zoom;
    (svg.node() as any).__gObj = g; // For programmatic zooming

    let linkDistance = 120;
    let chargeStrength = -400;
    let collideRadius = 40;

    if (layoutMode === 'compact') {
      linkDistance = 60;
      chargeStrength = -150;
      collideRadius = 25;
    } else if (layoutMode === 'spread') {
      linkDistance = 250;
      chargeStrength = -800;
      collideRadius = 60;
    } else if (layoutMode === 'circle') {
      linkDistance = 50;
      chargeStrength = -150;
      collideRadius = 20;
    } else if (layoutMode === 'layered') {
      linkDistance = 100;
      chargeStrength = -300;
      collideRadius = 30;
    }

    const simulation = d3.forceSimulation(finalNodes)
      .alphaDecay(0.15) // Converge very fast so it stops moving
      .force('link', d3.forceLink(finalLinks).id((d: any) => d.id).distance(linkDistance))
      .force('charge', d3.forceManyBody().strength(chargeStrength))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide().radius(collideRadius));
      
    if (layoutMode === 'circle') {
       simulation.force('r', d3.forceRadial(Math.min(width, height) / 2.5, width / 2, height / 2).strength(1));
    } else if (layoutMode === 'layered') {
       simulation.force('y', null);
       simulation.force('x', d3.forceX(width / 2).strength(0.1));
    }
    
    simulation.on('end', () => setIsPlaying(false));
      
    simRef.current = simulation;

    const defs = svg.append('defs');
    
    // Create markers for every distinct predicate
    allPredicates.forEach((pred) => {
        defs.append('marker')
          .attr('id', `arrow-${pred.replace(/[^a-zA-Z0-9]/g, '_')}`)
          .attr('viewBox', '0 -5 10 10')
          .attr('refX', 22)
          .attr('refY', 0)
          .attr('markerWidth', 6)
          .attr('markerHeight', 6)
          .attr('orient', 'auto')
          .append('path')
          .attr('fill', linkColorScale(pred))
          .attr('d', 'M0,-5L10,0L0,5');
    });

    const link = g.append('g')
      .selectAll('.link')
      .data(finalLinks)
      .join('path')
      .attr('class', 'link')
      .attr('stroke', (d: any) => d.inferred ? '#10b981' : linkColorScale(d.category))
      .attr('stroke-width', (d: any) => d.inferred ? 1.5 : 1.5)
      .attr('stroke-dasharray', (d: any) => d.inferred ? '2,4' : 'none')
      .attr('stroke-linecap', 'round')
      .attr('fill', 'none')
      .attr('marker-end', (d: any) => `url(#arrow-${d.category.replace(/[^a-zA-Z0-9]/g, '_')})`);

    const linkLabel = g.append('g')
      .selectAll('.link-label')
      .data(finalLinks)
      .join('text')
      .attr('class', 'link-label')
      .attr('font-size', '9px')
      .attr('font-weight', 'bold')
      .attr('fill', '#64748b')
      .attr('text-anchor', 'middle')
      .text(d => d.type);

    const node = g.append('g')
      .selectAll('.node')
      .data(finalNodes)
      .join('g')
      .attr('class', 'node')
      .attr('id', (d: any) => `node-${d.id.replace(/[^a-zA-Z0-9]/g, '-')}`) // Sanitize ID for selection
      .call(d3.drag()
        .on('start', (event, d: any) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d: any) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d: any) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        }) as any)
      .on('mouseover', (event, d: any) => {
          setHoveredNode(d);
          node.style('opacity', (n: any) => (n === d || n?.id === selectedNodeId ? 1 : 0.2));
          link.style('opacity', (l: any) => (l.source === d || l.target === d || l.source?.id === selectedNodeId || l.target?.id === selectedNodeId ? 1 : 0.1));
          linkLabel.style('opacity', (l: any) => (l.source === d || l.target === d || l.source?.id === selectedNodeId || l.target?.id === selectedNodeId ? 1 : 0.1));
      })
      .on('mouseout', () => {
          setHoveredNode(null);
          node.style('opacity', (n: any) => (!selectedNodeId || n?.id === selectedNodeId ? 1 : 0.2));
          link.style('opacity', (l: any) => (!selectedNodeId || l.source?.id === selectedNodeId || l.target?.id === selectedNodeId ? 1 : 0.1));
          linkLabel.style('opacity', (l: any) => (!selectedNodeId || l.source?.id === selectedNodeId || l.target?.id === selectedNodeId ? 1 : 0.1));
      })
      .on('click', (event, d: any) => {
          const pf = pathFinderState.current;
          if (pf.mode) {
             if (!pf.start) {
                 setPathStartNodeId(d.id);
             } else if (!pf.end) {
                 setPathEndNodeId(d.id);
             } else {
                 setPathStartNodeId(d.id);
                 setPathEndNodeId(null);
             }
          } else {
             setSelectedNodeId(prev => prev === d.id ? null : d.id);
          }
      });

    // Node shapes based on type
    node.each(function(this: any, d: any) {
        const el = d3.select(this);
        if (d.group === 'Literal') {
            // Rounded rect for literals
            el.append('rect')
              .attr('x', -15)
              .attr('y', -10)
              .attr('width', 30)
              .attr('height', 20)
              .attr('rx', 4)
              .attr('fill', '#fcd34d')
              .attr('stroke', '#d97706')
              .attr('stroke-width', 2);
        } else {
            // Shape for generic typed nodes
            const symbolType = nodeShapeScale(d.group) as unknown as d3.SymbolType;
            const pathData = d3.symbol().type(symbolType).size(500)();
            el.append('path')
              .attr('d', pathData)
              .attr('fill', nodeColorScale(d.group))
              .attr('stroke', d3.color(nodeColorScale(d.group) as string)?.darker()?.formatHex() || '#475569')
              .attr('stroke-width', 2);
        }
    });

    node.append('text')
      .text((d: any) => d.label)
      .attr('x', 20)
      .attr('y', 4)
      .attr('font-size', '11px')
      .attr('font-weight', 'black')
      .attr('font-family', 'Inter, sans-serif')
      .attr('fill', '#f8fafc');

    node.append('circle')
       .attr('class', 'selection-ring')
       .attr('r', 18)
       .attr('fill', 'none')
       .attr('stroke', '#ec4899')
       .attr('stroke-width', 2)
       .attr('stroke-dasharray', '4,4')
       .style('opacity', 0); // Hidden by default

    simulation.on('tick', () => {
      link
        .attr('d', (d: any) => {
            const dx = d.target.x - d.source.x;
            const dy = d.target.y - d.source.y;
            const dr = Math.sqrt(dx * dx + dy * dy) || 0.001;
            
            let curveOffset = 0;
            if (d.totalLinks > 1) {
                const mid = (d.totalLinks - 1) / 2;
                curveOffset = (d.linkNum - mid) * 0.35; 
            }
            
            if (curveOffset === 0) {
               return `M${d.source.x},${d.source.y}L${d.target.x},${d.target.y}`;
            } else {
               const qxA = (d.source.x + d.target.x) / 2;
               const qyA = (d.source.y + d.target.y) / 2;
               const nx = -dy / dr;
               const ny = dx / dr;
               const offsetAmount = curveOffset * Math.min(dr, 150);
               const cx = qxA + nx * offsetAmount;
               const cy = qyA + ny * offsetAmount;
               return `M${d.source.x},${d.source.y} Q${cx},${cy} ${d.target.x},${d.target.y}`;
            }
        });

      linkLabel
        .attr('x', (d: any) => {
            if (d.totalLinks <= 1) return (d.source.x + d.target.x) / 2;
            const dx = d.target.x - d.source.x;
            const dy = d.target.y - d.source.y;
            const dr = Math.sqrt(dx * dx + dy * dy) || 0.001;
            const mid = (d.totalLinks - 1) / 2;
            const curveOffset = (d.linkNum - mid) * 0.35;
            const qxA = (d.source.x + d.target.x) / 2;
            const nx = -dy / dr;
            const offsetAmount = curveOffset * Math.min(dr, 150) * 0.5; // quadratic bezier midpoint is halfway to control pt
            return qxA + nx * offsetAmount;
        })
        .attr('y', (d: any) => {
            if (d.totalLinks <= 1) return (d.source.y + d.target.y) / 2 - 4;
            const dx = d.target.x - d.source.x;
            const dy = d.target.y - d.source.y;
            const dr = Math.sqrt(dx * dx + dy * dy) || 0.001;
            const mid = (d.totalLinks - 1) / 2;
            const curveOffset = (d.linkNum - mid) * 0.35;
            const qyA = (d.source.y + d.target.y) / 2;
            const ny = dx / dr;
            const offsetAmount = curveOffset * Math.min(dr, 150) * 0.5;
            return qyA + ny * offsetAmount - 4;
        });

      node.attr('transform', (d: any) => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
    };
  }, [allNodes]);

  // Effect to handle selection changes
  useEffect(() => {
     if (!svgRef.current) return;
     const svg = d3.select(svgRef.current);
     const g = svg.select('g');
     
     if (shortestPath) {
         const pathNodes = new Set(shortestPath.nodes);
         const isLinkInPath = (l: any) => {
             return shortestPath.links.some((pl: any) => 
                 (pl.source === l.source?.id && pl.target === l.target?.id) || 
                 (pl.source === l.target?.id && pl.target === l.source?.id)
             );
         };

         g.selectAll('.node').style('opacity', (n: any) => pathNodes.has(n?.id) ? 1 : 0.1);
         g.selectAll('.selection-ring').style('opacity', (n: any) => pathNodes.has(n?.id) ? 1 : 0);
         
         g.selectAll('.link').style('opacity', (l: any) => isLinkInPath(l) ? 1 : 0.05)
           .attr('stroke', (l: any) => isLinkInPath(l) ? '#34d399' : (l.inferred ? '#10b981' : linkColorScale(l.category) as string)) // emerald-400
           .attr('stroke-width', (l: any) => isLinkInPath(l) ? 2.5 : 1.5);
           
         g.selectAll('.link-label').style('opacity', (d: any) => {
             if (d && d.source) return isLinkInPath(d) ? 1 : 0.05;
             return 1;
         });
         
     } else if (selectedNodeId || pathStartNodeId || pathEndNodeId) {
         const highlightedIds = new Set<string>();
         if (selectedNodeId) highlightedIds.add(selectedNodeId);
         if (pathStartNodeId) highlightedIds.add(pathStartNodeId);
         if (pathEndNodeId) highlightedIds.add(pathEndNodeId);

         g.selectAll('.node').style('opacity', (n: any) => highlightedIds.has(n?.id) ? 1 : 0.2);
         g.selectAll('.selection-ring').style('opacity', (n: any) => highlightedIds.has(n?.id) ? 1 : 0);
         g.selectAll('.link').style('opacity', (l: any) => highlightedIds.has(l?.source?.id) || highlightedIds.has(l?.target?.id) ? 1 : 0.1)
           .attr('stroke', (l: any) => l.inferred ? '#10b981' : linkColorScale(l.category) as string)
           .attr('stroke-width', 1.5);
         g.selectAll('.link-label').style('opacity', (d: any) => {
             if (d && d.source) return (highlightedIds.has(d?.source?.id) || highlightedIds.has(d?.target?.id)) ? 1 : 0.1;
             return 1;
         });
         
         if (simRef.current && selectedNodeId) {
             const nodes = simRef.current.nodes();
             const targetNode = nodes.find((n: any) => n?.id === selectedNodeId);
             
             // Removed auto-zoom to prevent the camera from fighting the user's manual zoom
         }
     } else {
         g.selectAll('.node').style('opacity', 1);
         g.selectAll('.selection-ring').style('opacity', 0);
         g.selectAll('.link').style('opacity', 1)
           .attr('stroke', (l: any) => l.inferred ? '#10b981' : linkColorScale(l.category) as string)
           .attr('stroke-width', (d: any) => d.category === 'hierarchy' ? 2.5 : 1.5);
         g.selectAll('.link-label').style('opacity', 1);
     }
  }, [selectedNodeId, pathStartNodeId, pathEndNodeId, shortestPath, triples]);

  const handleZoomIn = () => {
     if (svgRef.current) {
        const svg = d3.select(svgRef.current);
        const zoom = (svgRef.current as any).__zoomObj;
        if (zoom) {
            svg.transition().duration(300).call(zoom.scaleBy as any, 1.3);
        }
     }
  };

  const handleZoomOut = () => {
     if (svgRef.current) {
        const svg = d3.select(svgRef.current);
        const zoom = (svgRef.current as any).__zoomObj;
        if (zoom) {
            svg.transition().duration(300).call(zoom.scaleBy as any, 0.7);
        }
     }
  };

  const handleRecenter = () => {
     if (svgRef.current && containerRef.current) {
        const svg = d3.select(svgRef.current);
        const zoom = (svgRef.current as any).__zoomObj;
        if (zoom) {
            svg.transition().duration(500).call(zoom.transform as any, d3.zoomIdentity);
        }
     }
  };

  const handleTogglePlay = () => {
     if (simRef.current) {
         if (isPlaying) {
             simRef.current.stop();
         } else {
             simRef.current.alpha(0.3).restart();
         }
         setIsPlaying(!isPlaying);
     }
  };

  return (
    <div className="relative w-full h-full bg-[#050505] overflow-hidden" ref={containerRef}>
      <svg ref={svgRef} className="w-full h-full cursor-grab active:cursor-grabbing outline-none" />
      
      {/* Search Bar */}
      <div className="absolute top-6 left-1/2 -translate-x-1/2 w-64 md:w-96 z-20">
          <div className="relative group">
              <input 
                  type="text" 
                  placeholder="Rechercher (ex: Goal)..." 
                  className="w-full pl-10 pr-4 py-2.5 bg-neutral-900/50 backdrop-blur-md text-neutral-200 rounded-full border border-neutral-800/50 focus:border-neutral-500 focus:bg-neutral-900 shadow-lg outline-none transition-all placeholder:text-neutral-500 text-sm"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
              />
              <Search className="w-4 h-4 text-neutral-400 absolute left-4 top-1/2 -translate-y-1/2 group-focus-within:text-neutral-300 transition-colors" />
          </div>
          
          {searchResults.length > 0 && (
              <div className="mt-2 bg-neutral-900/90 backdrop-blur-md rounded-2xl shadow-2xl border border-neutral-800/70 max-h-60 overflow-y-auto w-full absolute custom-scrollbar overflow-hidden">
                  {searchResults.map(res => (
                      <button 
                          key={res.id} 
                          className="w-full text-left px-4 py-3 text-sm hover:bg-neutral-800/50 flex flex-col gap-1 border-b border-neutral-800/50 last:border-0 transition-colors"
                          onClick={() => {
                              if (pathFindingMode) {
                                  if (!pathStartNodeId) {
                                      setPathStartNodeId(res.id);
                                  } else if (!pathEndNodeId) {
                                      if (pathStartNodeId === res.id) setPathStartNodeId(null);
                                      else setPathEndNodeId(res.id);
                                  } else {
                                      if (pathEndNodeId === res.id) setPathEndNodeId(null);
                                      else {
                                          setPathStartNodeId(res.id);
                                          setPathEndNodeId(null);
                                      }
                                  }
                              } else {
                                  setSelectedNodeId(prev => prev === res.id ? null : res.id);
                              }
                              setSearchQuery('');
                          }}
                      >
                          <span className="font-medium text-neutral-200">{res.label}</span>
                          <span className="text-[10px] text-neutral-500 truncate font-mono">{res.uri}</span>
                      </button>
                  ))}
              </div>
          )}
      </div>

      {/* Zoom Controls */}
      <div className="absolute top-6 left-6 flex flex-col gap-1.5 bg-neutral-900/50 backdrop-blur-md p-1.5 rounded-xl shadow-lg border border-neutral-800/50">
         <button onClick={handleZoomIn} className="p-2 hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 rounded-lg transition-colors" title="Zoom In">
            <ZoomIn className="w-4 h-4" />
         </button>
         <button onClick={handleZoomOut} className="p-2 hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 rounded-lg transition-colors" title="Zoom Out">
            <ZoomOut className="w-4 h-4" />
         </button>
         <button onClick={handleRecenter} className="p-2 hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 rounded-lg transition-colors" title="Reset View">
            <Target className="w-4 h-4" />
         </button>
         <div className="h-px bg-neutral-800/50 w-full my-1" />
         <button onClick={handleTogglePlay} className="p-2 hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 rounded-lg transition-colors" title={isPlaying ? "Pause Simulation" : "Resume Simulation"}>
            {isPlaying ? <Pause className="w-4 h-4 fill-current text-neutral-500" /> : <Play className="w-4 h-4 fill-current text-white" />}
         </button>
         <button onClick={() => setShowSettings(!showSettings)} className={`p-2 rounded-lg transition-colors ${showSettings ? 'bg-neutral-200 text-neutral-900' : 'hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200'}`} title="Layout Settings">
            <Settings2 className="w-4 h-4" />
         </button>
         <button onClick={() => setPathFindingMode(!pathFindingMode)} className={`p-2 rounded-lg transition-colors ${pathFindingMode ? 'bg-neutral-200 text-neutral-900' : 'hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200'}`} title="Outil de chemin">
            <Route className="w-4 h-4" />
         </button>
      </div>

      {pathFindingMode && (
         <div className="absolute top-6 right-6 bg-neutral-900/80 backdrop-blur-md border border-neutral-800/70 p-5 rounded-2xl shadow-2xl w-80 flex flex-col gap-4 z-30 animate-in slide-in-from-right-4 duration-300">
            <h3 className="text-neutral-200 font-medium flex items-center gap-2"><Route className="w-4 h-4 text-neutral-400"/> Plus Court Chemin</h3>
            
            <div className="flex flex-col gap-2 mx-1 mt-1">
                <div className={`p-3 rounded-xl border ${!pathStartNodeId ? 'border-neutral-500/50 bg-neutral-800/50 text-neutral-200' : 'border-neutral-800 bg-transparent text-neutral-400'} flex gap-3 items-center transition-colors text-sm`}>
                    <div className="w-6 h-6 rounded-full bg-neutral-950 flex items-center justify-center text-[10px] font-medium border border-neutral-800 text-neutral-400">A</div>
                    <div className="flex-1 truncate tracking-tight">{pathStartNodeId ? getShortUri(pathStartNodeId) : 'Cliquer sur le graphe...'}</div>
                </div>
                <div className={`p-3 rounded-xl border ${pathStartNodeId && !pathEndNodeId ? 'border-neutral-500/50 bg-neutral-800/50 text-neutral-200' : 'border-neutral-800 bg-transparent text-neutral-400'} flex gap-3 items-center transition-colors text-sm`}>
                    <div className="w-6 h-6 rounded-full bg-neutral-950 flex items-center justify-center text-[10px] font-medium border border-neutral-800 text-neutral-400">B</div>
                    <div className="flex-1 truncate tracking-tight">{pathEndNodeId ? getShortUri(pathEndNodeId) : 'Cliquer sur le graphe...'}</div>
                </div>
            </div>
            
            {shortestPath ? (
               <div className="mt-2 flex flex-col gap-2">
                   <div className="text-xs text-emerald-400 font-medium bg-emerald-950/30 p-2 rounded -mx-1 border border-emerald-900/30">
                       Chemin trouvé ({shortestPath.links.length} sauts)
                   </div>
                   <div className="max-h-48 overflow-y-auto custom-scrollbar flex flex-col gap-1 -mx-1 px-1">
                      {shortestPath.links.map((link: any, idx: number) => (
                        <div key={idx} className="bg-neutral-950 border border-neutral-800 rounded p-1.5 flex flex-col gap-0.5 text-[10px]">
                           <div className="text-neutral-300 font-mono truncate">{getShortUri(link.source)}</div>
                           <div className="flex items-center gap-1 text-emerald-400/80 pl-2">
                              <span>↳</span> <span className="font-semibold">{link.type}</span>
                           </div>
                           <div className="text-neutral-300 font-mono truncate">{getShortUri(link.target)}</div>
                        </div>
                      ))}
                   </div>
                   <button onClick={() => {setPathStartNodeId(null); setPathEndNodeId(null); setShortestPath(null);}} className="text-xs text-neutral-400 hover:text-neutral-200 bg-neutral-800 hover:bg-neutral-700 py-1.5 rounded transition">
                       Réinitialiser
                   </button>
               </div>
            ) : (pathStartNodeId && pathEndNodeId) ? (
               <div className="mt-2 flex flex-col gap-2">
                   <div className="text-xs text-red-400 font-medium bg-red-950/30 p-2 rounded -mx-1 border border-red-900/30">
                       Aucun chemin trouvé
                   </div>
                   <button onClick={() => {setPathStartNodeId(null); setPathEndNodeId(null); setShortestPath(null);}} className="text-xs text-neutral-400 hover:text-neutral-200 bg-neutral-800 hover:bg-neutral-700 py-1.5 rounded transition">
                       Réinitialiser
                   </button>
               </div>
            ) : null}
         </div>
      )}

      {showSettings && (
         <div className="absolute top-6 left-20 bg-neutral-900/80 backdrop-blur-md p-5 rounded-2xl shadow-2xl border border-neutral-800/70 flex flex-col gap-4 z-10 w-64 animate-in fade-in slide-in-from-left-4 duration-300">
             <div className="text-sm font-medium text-neutral-200">Disposition</div>
             <div className="flex flex-col gap-2">
                 <label className="flex items-center gap-3 text-sm text-neutral-400 hover:text-neutral-200 cursor-pointer transition-colors group">
                     <div className="relative flex items-center justify-center w-4 h-4">
                         <input type="radio" name="layout" className="opacity-0 absolute" checked={layoutMode === 'compact'} onChange={() => setLayoutMode('compact')} />
                         <div className={`w-4 h-4 rounded-full border transition-colors ${layoutMode === 'compact' ? 'border-neutral-200' : 'border-neutral-600 group-hover:border-neutral-400'}`}></div>
                         {layoutMode === 'compact' && <div className="absolute w-2 h-2 rounded-full bg-neutral-200"></div>}
                     </div>
                     Compact
                 </label>
                 <label className="flex items-center gap-3 text-sm text-neutral-400 hover:text-neutral-200 cursor-pointer transition-colors group">
                     <div className="relative flex items-center justify-center w-4 h-4">
                         <input type="radio" name="layout" className="opacity-0 absolute" checked={layoutMode === 'force'} onChange={() => setLayoutMode('force')} />
                         <div className={`w-4 h-4 rounded-full border transition-colors ${layoutMode === 'force' ? 'border-neutral-200' : 'border-neutral-600 group-hover:border-neutral-400'}`}></div>
                         {layoutMode === 'force' && <div className="absolute w-2 h-2 rounded-full bg-neutral-200"></div>}
                     </div>
                     Standard
                 </label>
                 <label className="flex items-center gap-3 text-sm text-neutral-400 hover:text-neutral-200 cursor-pointer transition-colors group">
                     <div className="relative flex items-center justify-center w-4 h-4">
                         <input type="radio" name="layout" className="opacity-0 absolute" checked={layoutMode === 'spread'} onChange={() => setLayoutMode('spread')} />
                         <div className={`w-4 h-4 rounded-full border transition-colors ${layoutMode === 'spread' ? 'border-neutral-200' : 'border-neutral-600 group-hover:border-neutral-400'}`}></div>
                         {layoutMode === 'spread' && <div className="absolute w-2 h-2 rounded-full bg-neutral-200"></div>}
                     </div>
                     Espacé
                 </label>
                 <label className="flex items-center gap-3 text-sm text-neutral-400 hover:text-neutral-200 cursor-pointer transition-colors group">
                     <div className="relative flex items-center justify-center w-4 h-4">
                         <input type="radio" name="layout" className="opacity-0 absolute" checked={layoutMode === 'layered'} onChange={() => setLayoutMode('layered')} />
                         <div className={`w-4 h-4 rounded-full border transition-colors ${layoutMode === 'layered' ? 'border-neutral-200' : 'border-neutral-600 group-hover:border-neutral-400'}`}></div>
                         {layoutMode === 'layered' && <div className="absolute w-2 h-2 rounded-full bg-neutral-200"></div>}
                     </div>
                     Couches
                 </label>
                 <label className="flex items-center gap-3 text-sm text-neutral-400 hover:text-neutral-200 cursor-pointer transition-colors group">
                     <div className="relative flex items-center justify-center w-4 h-4">
                         <input type="radio" name="layout" className="opacity-0 absolute" checked={layoutMode === 'circle'} onChange={() => setLayoutMode('circle')} />
                         <div className={`w-4 h-4 rounded-full border transition-colors ${layoutMode === 'circle' ? 'border-neutral-200' : 'border-neutral-600 group-hover:border-neutral-400'}`}></div>
                         {layoutMode === 'circle' && <div className="absolute w-2 h-2 rounded-full bg-neutral-200"></div>}
                     </div>
                     Radial
                 </label>
             </div>
             <div className="h-px bg-neutral-800/50 my-1" />
             <label className="flex items-center gap-3 text-sm text-neutral-400 hover:text-neutral-200 cursor-pointer transition-colors group">
                 <div className="relative flex items-center justify-center w-4 h-4">
                     <input type="checkbox" className="opacity-0 absolute" checked={hideIsolated} onChange={() => setHideIsolated(!hideIsolated)} />
                     <div className={`w-4 h-4 rounded border transition-colors ${hideIsolated ? 'border-neutral-200 bg-neutral-200 text-neutral-900' : 'border-neutral-600 group-hover:border-neutral-400'}`}>
                         {hideIsolated && <svg className="w-full h-full" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
                     </div>
                 </div>
                 Masquer isolés
             </label>
         </div>
      )}

     {/* Legend */}
      <div className="absolute top-6 right-6 bg-neutral-900/80 backdrop-blur-md p-5 rounded-2xl shadow-xl border border-neutral-800/70 text-xs flex flex-col gap-4 max-w-[280px] max-h-[85vh] overflow-y-auto custom-scrollbar">
         <div>
             <div className="font-medium text-neutral-500 mb-3 text-[10px] uppercase tracking-wider">Entités ({allNodeGroups.size})</div>
             <div className="flex flex-col gap-2.5">
                 {Array.from(allNodeGroups).map(group => {
                     const isVisible = !hiddenNodeGroups.has(group);
                     return (
                         <label key={group} className="flex items-center gap-3 cursor-pointer group/label">
                            <input 
                               type="checkbox" 
                               className="hidden" 
                               checked={isVisible} 
                               onChange={() => {
                                   const newHidden = new Set(hiddenNodeGroups);
                                   if (isVisible) newHidden.add(group);
                                   else newHidden.delete(group);
                                   setHiddenNodeGroups(newHidden);
                               }} 
                            />
                            <div className={`flex shrink-0 items-center justify-center w-4 h-4 rounded border ${isVisible ? 'border-neutral-500 bg-neutral-800' : 'border-neutral-700 bg-neutral-900'} transition-colors`}>
                                {isVisible && <svg className="w-3 h-3 text-neutral-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
                            </div>
                            {group === 'Literal' ? (
                                <div className="w-3.5 h-3.5 rounded bg-[#fcd34d]" style={{ opacity: isVisible ? 1 : 0.4 }} />
                            ) : (
                                <svg width="14" height="14" viewBox="-7 -7 14 14" style={{ opacity: isVisible ? 1 : 0.4, overflow: 'visible' }}>
                                    <path 
                                        d={d3.symbol().type(nodeShapeScale(group as string) as any).size(80)()} 
                                        fill={nodeColorScale(group as string) as any} 
                                    />
                                </svg>
                            )}
                            <span className={`text-neutral-300 transition-opacity truncate w-full ${isVisible ? 'opacity-100' : 'opacity-50'}`} title={group}>{group}</span>
                         </label>
                     );
                 })}
             </div>
         </div>
         
         <div className="h-px w-full bg-neutral-800/50" />
         
         <div>
             <div className="font-medium text-neutral-500 mb-3 text-[10px] uppercase tracking-wider">Relations ({allPredicates.size})</div>
             <div className="flex flex-col gap-2.5">
                 {Array.from(allPredicates).map(pred => {
                     const isVisible = !hiddenPredicates.has(pred);
                     return (
                         <label key={pred} className="flex items-center gap-3 cursor-pointer group/label">
                            <input 
                               type="checkbox" 
                               className="hidden" 
                               checked={isVisible} 
                               onChange={() => {
                                   const newHidden = new Set(hiddenPredicates);
                                   if (isVisible) newHidden.add(pred);
                                   else newHidden.delete(pred);
                                   setHiddenPredicates(newHidden);
                               }} 
                            />
                            <div className={`flex shrink-0 items-center justify-center w-4 h-4 rounded border ${isVisible ? 'border-neutral-500 bg-neutral-800' : 'border-neutral-700 bg-neutral-900'} transition-colors`}>
                                {isVisible && <svg className="w-3 h-3 text-neutral-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
                            </div>
                            <div className={`w-6 h-0.5 transition-opacity ${isVisible ? 'opacity-100' : 'opacity-40'}`} style={{ backgroundColor: linkColorScale(pred as string) as any }} />
                            <span className={`text-neutral-400 font-mono text-[9px] truncate w-full transition-opacity ${isVisible ? 'opacity-100' : 'opacity-50'}`} title={pred as string}>{getShortUri(pred as string)}</span>
                         </label>
                     );
                 })}
                  <div className="h-px w-full bg-neutral-800/30 my-1" />
                  <label className="flex items-center gap-3 cursor-pointer group">
                     <input type="checkbox" className="hidden" checked={!hideInferredLinks} onChange={() => setHideInferredLinks(!hideInferredLinks)} />
                     <div className={`flex items-center justify-center w-4 h-4 rounded border ${!hideInferredLinks ? 'border-neutral-500 bg-neutral-800' : 'border-neutral-700 bg-neutral-900'} transition-colors`}>
                         {!hideInferredLinks && <svg className="w-3 h-3 text-neutral-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
                     </div>
                     <div className={`w-6 h-0 border-t-[1.5px] border-dotted border-emerald-500 transition-opacity ${!hideInferredLinks ? 'opacity-100' : 'opacity-40'}`} />
                     <span className={`text-emerald-400 font-mono text-[10px] transition-opacity ${!hideInferredLinks ? 'opacity-100' : 'opacity-50'}`}>Afficher inférences</span>
                  </label>
             </div>
         </div>
      </div>

      {/* Tooltip */}
      {hoveredNode && (
         <div className="absolute bottom-6 right-6 bg-neutral-900/90 backdrop-blur-xl p-6 rounded-2xl shadow-2xl border border-neutral-800/70 max-w-sm pointer-events-none z-40 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center gap-4 mb-4">
               <div>
                   <h4 className="font-medium text-neutral-100 text-lg leading-tight break-words">{hoveredNode.label}</h4>
                   <div className="text-[10px] text-neutral-500 uppercase tracking-widest mt-1 font-medium">{hoveredNode.group}</div>
               </div>
            </div>
            
            {(() => {
                const comments = triples.filter((t: any) => t.subject === hoveredNode.uri && t.predicate === 'http://www.w3.org/2000/01/rdf-schema#comment');
                if (comments.length > 0) {
                    return (
                        <div className="mb-4 text-xs text-neutral-400 italic leading-relaxed border-l-2 border-neutral-700 pl-3 py-1">
                            {comments[0].object}
                        </div>
                    );
                }
                return null;
            })()}

            <div className="space-y-4 text-xs">
                {(hoveredNode.uri && hoveredNode.uri.match(/\/ontologies\/([^#]+)#/)) && (
                    <div className="flex items-center justify-between py-2 border-t border-neutral-800/50">
                        <span className="text-neutral-500">Ontologie</span>
                        <span className="font-mono text-neutral-300">
                           {hoveredNode.uri.match(/\/ontologies\/([^#]+)#/)[1].split('/').pop()}
                        </span>
                    </div>
                )}
                
                <div className="p-3 bg-neutral-950/50 border border-neutral-800/30 rounded-xl text-[10px] text-neutral-500 font-mono break-all leading-relaxed">
                   {hoveredNode.uri}
                </div>
            </div>
         </div>
      )}
    </div>
  );
}