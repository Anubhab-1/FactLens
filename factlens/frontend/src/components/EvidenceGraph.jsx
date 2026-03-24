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
    if (!key) continue;

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
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) {
        setDimensions({ width, height });
        setIsReady(true);
      }
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
      label: "CLAIM CORE",
      text: result.claim,
      color: GRAPH_COLORS.CLAIM,
      val: 40,
      isClaim: true,
    });

    const sources = collectEvidenceSources(result);
    sources.forEach((source, idx) => {
      const sourceId = `source-${idx}`;
      const nodeColor = sourceNodeColor(source);
      const nodeSize = 12 + (source.authority_score || 0.5) * 15;

      nodes.push({
        id: sourceId,
        label: (source.domain || "WEB").toUpperCase(),
        title: source.title,
        color: nodeColor,
        val: nodeSize,
        url: source.url,
        stance: String(source.stance || "").trim().toUpperCase(),
      });

      links.push({
        source: sourceId,
        target: "claim",
        color: `${nodeColor}44`,
        width: 1.5,
      });
    });

    return { nodes, links };
  }, [result]);

  useEffect(() => {
    if (fgRef.current && isReady) {
      const fg = fgRef.current;
      fg.d3Force("charge").strength(-800);
      fg.d3Force("link").distance(120);
      setTimeout(() => {
        if (fgRef.current) fg.zoomToFit(600, 80);
      }, 500);
    }
  }, [graphData, isReady]);

  return (
    <div ref={containerRef} className="relative w-full h-full min-h-[400px] overflow-hidden bg-black/40">
      {!isReady ? (
        <div className="flex h-full w-full absolute inset-0 items-center justify-center text-[10px] font-mono text-white/20 uppercase tracking-[0.2em] animate-pulse">
           Initializing Topology...
        </div>
      ) : (
        <>
          <ForceGraph2D
            ref={fgRef}
            width={dimensions.width}
            height={dimensions.height}
            graphData={graphData}
            backgroundColor="rgba(0,0,0,0)"
            nodeRelSize={1}
            linkDirectionalParticles={2}
            linkDirectionalParticleSpeed={0.003}
            nodeCanvasObject={(node, ctx, globalScale) => {
              if (node.x === undefined || node.y === undefined) return;
              const r = Math.sqrt(Math.max(0, node.val || 1)) * 1.8;
              const isClaim = node.isClaim;
              ctx.save();
              try {
                const gradient = ctx.createRadialGradient(node.x, node.y, r * 0.8, node.x, node.y, r * 2.5);
                gradient.addColorStop(0, `${node.color}44`);
                gradient.addColorStop(1, `${node.color}00`);
                ctx.beginPath();
                ctx.arc(node.x, node.y, r * 2.5, 0, 2 * Math.PI);
                ctx.fillStyle = gradient;
                ctx.fill();
              } catch(e) { /* gradient safety */ }
              ctx.restore();
              ctx.beginPath();
              ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
              ctx.fillStyle = isClaim ? "#fff" : node.color;
              ctx.fill();
              if (isClaim) {
                ctx.strokeStyle = node.color;
                ctx.lineWidth = 4 / globalScale;
                ctx.stroke();
              }
              const fontSize = 10 / globalScale;
              ctx.font = `bold ${fontSize}px Inter, sans-serif`;
              ctx.textAlign = "center";
              ctx.textBaseline = "middle";
              ctx.fillStyle = "rgba(255,255,255,0.9)";
              ctx.shadowColor = "rgba(0,0,0,0.5)";
              ctx.shadowBlur = 4 / globalScale;
              ctx.fillText(node.label, node.x, node.y + r + 8 / globalScale);
              ctx.shadowBlur = 0;
            }}
            nodePointerAreaPaint={(node, color, ctx) => {
              if (node.x === undefined || node.y === undefined) return;
              const r = Math.sqrt(Math.max(0, node.val || 1)) * 1.8;
              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
              ctx.fill();
            }}
            onNodeClick={(node) => node.url && window.open(node.url, "_blank")}
          />

          <div className="absolute bottom-6 left-6 space-y-3 pointer-events-none">
            <span className="label-cap !text-[9px] text-white/30">Network Topology</span>
            <div className="flex flex-wrap gap-4">
              {[
                { label: "Claim", color: GRAPH_COLORS.CLAIM },
                { label: "Support", color: GRAPH_COLORS.SUPPORTS },
                { label: "Conflict", color: GRAPH_COLORS.CONFLICTS },
                { label: "Mixed", color: GRAPH_COLORS.MIXED },
              ].map((item) => (
                <div key={item.label} className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full" style={{ background: item.color }} />
                  <span className="text-[9px] font-bold uppercase tracking-widest text-white/50">{item.label}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
