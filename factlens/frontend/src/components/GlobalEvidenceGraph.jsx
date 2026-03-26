import { useEffect, useRef, useState, useMemo } from "react";
import ForceGraph2D from "react-force-graph-2d";

const GRAPH_COLORS = {
  CLAIM: "#60a5fa", // blue-400
  SUPPORTS: "#10b981", // emerald-500
  CONFLICTS: "#f43f5e", // rose-500
  MIXED: "#f59e0b", // amber-500
  NEUTRAL: "#94a3b8", // slate-400
};

function sourceNodeColor(stance) {
  const s = String(stance || "").trim().toUpperCase();
  if (s === "SUPPORT") return GRAPH_COLORS.SUPPORTS;
  if (s === "CONFLICT") return GRAPH_COLORS.CONFLICTS;
  if (s === "MIXED") return GRAPH_COLORS.MIXED;
  return GRAPH_COLORS.NEUTRAL;
}

export default function GlobalEvidenceGraph({ session }) {
  const fgRef = useRef();
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });
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
    if (!session || !session.results) return { nodes: [], links: [] };

    const nodesMap = new Map();
    const links = [];

    // 1. Collect all claims as nodes
    session.results.forEach((result) => {
      const claimId = `claim-${result.claim_id}`;
      const claimObj = session.claims?.find(c => String(c.id) === String(result.claim_id));
      nodesMap.set(claimId, {
        id: claimId,
        label: `CLAIM ${result.claim_id}`,
        text: claimObj?.claim || `Claim ${result.claim_id}`,
        color: GRAPH_COLORS.CLAIM,
        val: 25,
        isClaim: true,
      });

      // 2. Collect all sources for this claim
      const buckets = [
        ...(result.supporting_evidence || []),
        ...(result.conflicting_evidence || []),
        ...(result.mixed_evidence || []),
        ...(result.neutral_evidence || []),
      ];

      buckets.forEach((source) => {
        if (!source) return;
        const sourceUrl = String(source?.url || "").trim();
        const sourceId = String(source?.id || "").trim();
        const sourceKey = sourceUrl || sourceId;
        if (!sourceKey) return;

        if (!nodesMap.has(sourceKey)) {
          nodesMap.set(sourceKey, {
            id: sourceKey,
            label: (source.domain || "WEB").toUpperCase(),
            title: source.title,
            color: sourceNodeColor(source.stance),
            val: 12 + (source.authority_score || 0.5) * 10,
            url: source.url,
            isSource: true,
          });
        }

        links.push({
          source: sourceKey,
          target: claimId,
          color: `${sourceNodeColor(source.stance)}33`,
          width: 1,
        });
      });
    });

    return {
      nodes: Array.from(nodesMap.values()),
      links: links,
    };
  }, [session]);

  useEffect(() => {
    if (fgRef.current && isReady) {
      const fg = fgRef.current;
      fg.d3Force("charge").strength(-500);
      fg.d3Force("link").distance(100);
      setTimeout(() => {
        if (fgRef.current) fg.zoomToFit(600, 50);
      }, 500);
    }
  }, [graphData, isReady]);

  return (
    <div ref={containerRef} className="relative w-full h-[500px] overflow-hidden bg-black/40 rounded-[2rem] border border-white/5 shadow-2xl">
      {!isReady ? (
        <div className="flex h-full w-full absolute inset-0 items-center justify-center text-[10px] font-mono text-white/20 uppercase tracking-[0.2em] animate-pulse">
          Mapping Global Consensus...
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
            linkDirectionalParticles={1}
            linkDirectionalParticleSpeed={0.002}
            nodeCanvasObject={(node, ctx, globalScale) => {
              if (node.x === undefined || node.y === undefined) return;
              const r = Math.sqrt(Math.max(0, node.val || 1)) * 1.5;
              const isClaim = node.isClaim;
              
              ctx.save();
              try {
                // Glow
                const gradient = ctx.createRadialGradient(node.x, node.y, r * 0.5, node.x, node.y, r * 3);
                gradient.addColorStop(0, `${node.color}55`);
                gradient.addColorStop(1, `${node.color}00`);
                ctx.beginPath();
                ctx.arc(node.x, node.y, r * 3, 0, 2 * Math.PI);
                ctx.fillStyle = gradient;
                ctx.fill();
              } catch (e) {
                // radial gradient fallback
              }
              ctx.restore();

              ctx.beginPath();
              ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
              ctx.fillStyle = isClaim ? "#fff" : node.color;
              ctx.fill();
              
              if (isClaim) {
                ctx.strokeStyle = node.color;
                ctx.lineWidth = 3 / globalScale;
                ctx.stroke();
              }

              // Text Labels (dynamic based on zoom)
              if (globalScale > 0.8) {
                const fontSize = 8 / globalScale;
                ctx.font = `bold ${fontSize}px Inter, sans-serif`;
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillStyle = "rgba(255,255,255,0.8)";
                ctx.fillText(node.label || "", node.x, node.y + r + 10 / globalScale);
              }
            }}
            nodePointerAreaPaint={(node, color, ctx) => {
              if (node.x === undefined || node.y === undefined) return;
              const r = Math.sqrt(Math.max(0, node.val || 1)) * 1.5;
              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
              ctx.fill();
            }}
            onNodeClick={(node) => node.url && window.open(node.url, "_blank")}
          />

          <div className="absolute top-8 left-8 p-4 glass-card-static rounded-2xl border border-white/10 pointer-events-none">
            <h4 className="label-cap text-blue-400 mb-2">Global Evidence Topology</h4>
            <p className="text-[10px] text-white/40 leading-relaxed max-w-[200px]">
              Visualizing cross-references between claims and shared evidence sources.
            </p>
          </div>

          <div className="absolute bottom-8 right-8 flex gap-4 pointer-events-none">
            {[
              { label: "Claims", color: GRAPH_COLORS.CLAIM },
              { label: "Supporting", color: GRAPH_COLORS.SUPPORTS },
              { label: "Conflicting", color: GRAPH_COLORS.CONFLICTS },
            ].map((item) => (
              <div key={item.label} className="flex items-center gap-2">
                <div className="h-1.5 w-1.5 rounded-full" style={{ background: item.color }} />
                <span className="text-[9px] font-bold uppercase tracking-widest text-white/50">{item.label}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
