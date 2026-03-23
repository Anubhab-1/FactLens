import { useEffect, useRef, useState, useMemo } from "react";
import ForceGraph2D from "react-force-graph-2d";

const GRAPH_COLORS = {
  CLAIM: "#60a5fa", // blue-400
  SUPPORTS: "#10b981", // emerald-500
  CONFLICTS: "#f43f5e", // rose-500
  MIXED: "#f59e0b", // amber-500
  NEUTRAL: "#94a3b8", // slate-400
};

function collectEvidenceSources(result) {
  const byKey = new Map();
  const buckets = (result?.evidence_used || []).length
    ? result.evidence_used
    : [
        ...(result?.supporting_evidence || []),
        ...(result?.conflicting_evidence || []),
        ...(result?.mixed_evidence || []),
        ...(result?.neutral_evidence || []),
      ];

  for (const source of buckets) {
    const sourceId = String(source?.id || "").trim();
    const sourceUrl = String(source?.url || "").trim();
    const key = sourceId || sourceUrl;
    if (!key) {
      continue;
    }

    const existing = byKey.get(key);
    if (!existing || Number(source?.overall_score || 0) > Number(existing?.overall_score || 0)) {
      byKey.set(key, source);
    }
  }

  return [...byKey.values()];
}

function sourceNodeColor(source) {
  const stance = String(source?.stance || "").trim().toUpperCase();
  if (stance === "SUPPORT") return GRAPH_COLORS.SUPPORTS;
  if (stance === "CONFLICT") return GRAPH_COLORS.CONFLICTS;
  if (stance === "MIXED") return GRAPH_COLORS.MIXED;
  return GRAPH_COLORS.NEUTRAL;
}

export default function EvidenceGraph({ result }) {
  const fgRef = useRef();
  const [dimensions, setDimensions] = useState({ width: 600, height: 400 });
  const containerRef = useRef(null);

  // Auto-resize graph to fit container
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDimensions({ width, height });
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const graphData = useMemo(() => {
    if (!result) return { nodes: [], links: [] };

    const nodes = [];
    const links = [];

    // Central Claim Node
    nodes.push({
      id: "claim",
      label: "The Claim",
      text: result.claim,
      color: GRAPH_COLORS.CLAIM,
      val: 25, // Large size
      isClaim: true,
    });

    const sources = collectEvidenceSources(result);

    sources.forEach((source, idx) => {
      const sourceId = `source-${idx}`;
      const nodeColor = sourceNodeColor(source);

      // Base size on authority score (0 to 1)
      const nodeSize = 8 + (source.authority_score || 0.5) * 12;

      nodes.push({
        id: sourceId,
        label: source.domain || source.title || "Source",
        text: source.snippet_used || source.snippet || "",
        title: source.title,
        authority: source.authority_score,
        color: nodeColor,
        val: nodeSize,
        url: source.url,
        stance: String(source.stance || "").trim().toUpperCase(),
      });

      links.push({
        source: sourceId,
        target: "claim",
        color: `${nodeColor}66`, // Add transparency to link
        width: 2,
      });
    });

    return { nodes, links };
  }, [result]);

  // Center graph after rendering
  useEffect(() => {
    if (fgRef.current) {
      setTimeout(() => {
        fgRef.current.d3Force("charge").strength(-400); // Push nodes apart
        fgRef.current.zoomToFit(400, 50); // Animated zoom to fit
      }, 100);
    }
  }, [graphData]);

  return (
    <div 
      ref={containerRef} 
      className="relative w-full h-[400px] overflow-hidden rounded-[1.2rem] border border-white/6 bg-[#0f172a]/50"
    >
      <ForceGraph2D
        ref={fgRef}
        width={dimensions.width}
        height={dimensions.height}
        graphData={graphData}
        nodeColor={(node) => node.color}
        nodeRelSize={1}
        nodeVal={(node) => node.val}
        linkColor={(link) => link.color}
        linkWidth={(link) => link.width}
        linkDirectionalParticles={2}
        linkDirectionalParticleSpeed={0.005}
        nodeCanvasObject={(node, ctx, globalScale) => {
          // Draw a standard circle
          const r = Math.sqrt(Math.max(0, node.val || 1)) * 1.5;
          ctx.beginPath();
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
          ctx.fillStyle = node.color;
          ctx.fill();
          
          if (node.isClaim) {
            ctx.lineWidth = 1;
            ctx.strokeStyle = "#fff";
            ctx.stroke();
          }

          // Draw label text below node
          const label = node.label;
          const fontSize = 12/globalScale;
          ctx.font = `${fontSize}px Inter, sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
          ctx.fillText(label, node.x, node.y + r + (4/globalScale) + fontSize/2);
        }}
        onNodeClick={(node) => {
          if (node.url) {
            window.open(node.url, '_blank', 'noopener,noreferrer');
          }
        }}
        enableNodeDrag={true}
        enableZoomPanInteraction={true}
      />
      
      {/* Overlay legend */}
      <div className="absolute top-4 left-4 flex flex-col gap-2 pointer-events-none">
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400">Node Legend</p>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-blue-400"></div>
          <span className="text-xs text-slate-300">The Claim</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500"></div>
          <span className="text-xs text-slate-300">Supporting Source</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-rose-500"></div>
          <span className="text-xs text-slate-300">Conflicting Source</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500"></div>
          <span className="text-xs text-slate-300">Mixed Evidence</span>
        </div>
        <p className="mt-2 text-[10px] text-slate-500 max-w-[150px] leading-relaxed">
          Node size indicates domain authority. Drag nodes to explore. Click source nodes to open URL.
        </p>
      </div>
    </div>
  );
}
