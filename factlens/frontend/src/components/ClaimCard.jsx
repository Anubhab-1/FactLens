import { useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Globe,
  LayoutList,
  Network,
  ShieldAlert,
  Zap,
} from "lucide-react";

import EvidenceGraph from "./EvidenceGraph";

const VERDICT = {
  TRUE: {
    label: "Verified True",
    dot: "bg-emerald-400",
    textColor: "text-emerald-400",
    ring: "ring-emerald-500/20",
    bg: "bg-emerald-500/5",
    glow: "glow-emerald",
  },
  FALSE: {
    label: "Factually False",
    dot: "bg-rose-400",
    textColor: "text-rose-400",
    ring: "ring-rose-500/20",
    bg: "bg-rose-500/5",
    glow: "glow-rose",
  },
  PARTIALLY_TRUE: {
    label: "Partially True",
    dot: "bg-amber-400",
    textColor: "text-amber-400",
    ring: "ring-amber-500/20",
    bg: "bg-amber-500/5",
    glow: "glow-amber",
  },
  UNVERIFIABLE: {
    label: "Unverifiable",
    dot: "bg-white/20",
    textColor: "text-white/40",
    ring: "ring-white/5",
    bg: "bg-white/2",
    glow: "",
  },
};

function collectEvidenceSources(result) {
  const buckets = (result?.evidence_used || []).length
    ? result.evidence_used
    : [
        ...(result?.supporting_evidence || []),
        ...(result?.conflicting_evidence || []),
        ...(result?.mixed_evidence || []),
        ...(result?.neutral_evidence || []),
      ];
  const deduped = new Map();

  for (const source of buckets) {
    const sourceId = String(source?.id || "").trim();
    const sourceUrl = String(source?.url || "").trim();
    const key = sourceId || sourceUrl;
    if (!key) continue;

    const existing = deduped.get(key);
    if (!existing || Number(source?.overall_score || 0) > Number(existing?.overall_score || 0)) {
      deduped.set(key, source);
    }
  }

  return [...deduped.values()];
}

function formatOverridePercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "0%";
  return `${Math.round(numeric * 100)}%`;
}

function formatSourceStance(value) {
  const stance = String(value || "").trim().toUpperCase();
  if (stance === "SUPPORT") return { label: "support", color: "text-emerald-400" };
  if (stance === "CONFLICT") return { label: "conflict", color: "text-rose-400" };
  if (stance === "MIXED") return { label: "mixed", color: "text-amber-400" };
  return { label: stance.toLowerCase() || "irrelevant", color: "text-slate-300" };
}

function formatSourceOrigin(value) {
  const origin = String(value || "").trim().toLowerCase();
  if (origin === "official") return { label: "Official", color: "text-sky-300" };
  if (origin === "first_party") return { label: "First-party", color: "text-blue-300" };
  if (origin === "reference") return { label: "Reference", color: "text-violet-300" };
  if (origin === "secondary") return { label: "Secondary", color: "text-slate-300" };
  if (origin === "social") return { label: "Social", color: "text-rose-300" };
  return null;
}

function formatSnapshotStamp(value) {
  if (!value) return "Capture time unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return `${parsed.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  })} UTC`;
}

function collectEvidenceProof(result) {
  const explicitProof = (result?.evidence_provenance || []).filter(Boolean);
  if (explicitProof.length) return explicitProof;

  return collectEvidenceSources(result).slice(0, 3).map((source) => {
    const topPassages = [...(source?.evidence_passages || [])]
      .filter((passage) => String(passage?.text || "").trim())
      .sort((left, right) => Number(right?.score || 0) - Number(left?.score || 0))
      .slice(0, 2)
      .map((passage) => ({
        id: String(passage?.id || "").trim(),
        text: String(passage?.text || "").trim(),
        score: Number(passage?.score || 0),
        kind: String(passage?.kind || "passage").trim(),
      }));
    const snapshot = source?.source_snapshot || {};

    return {
      source_id: String(source?.id || "").trim(),
      source_title: String(source?.title || "Untitled source").trim(),
      url: String(source?.url || "").trim(),
      domain: String(source?.domain || "").trim(),
      stance: String(source?.stance || "").trim(),
      primary_quote: topPassages[0]?.text || String(source?.snippet_used || source?.snippet || "").trim(),
      top_passages: topPassages,
      snapshot_id: String(snapshot?.snapshot_id || "").trim(),
      captured_at: String(snapshot?.captured_at || "").trim(),
      content_hash: String(snapshot?.content_hash || "").trim(),
    };
  });
}

function collectContradictionTypes(result) {
  return Array.isArray(result?.conflict_summary?.contradiction_types)
    ? result.conflict_summary.contradiction_types.filter(Boolean)
    : [];
}

function formatDomainLabel(source) {
  const domain = String(source?.domain || "").trim() || "Web";
  const year = source?.published_label ? String(source.published_label).match(/\d{4}/)?.[0] : null;
  return year ? `${domain} · ${year}` : domain;
}

function authorityTier(score) {
  if (score >= 8) return { label: "High authority", color: "text-emerald-400" };
  if (score >= 5) return { label: "Medium authority", color: "text-amber-400" };
  return { label: "Low authority", color: "text-slate-400" };
}

function ConflictSplitView({ result, sources }) {
  const support = sources.find((s) => String(s?.stance).toUpperCase() === "SUPPORT");
  const conflict = sources.find((s) => String(s?.stance).toUpperCase() === "CONFLICT");
  if (!support || !conflict) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <span className="label-cap text-rose-400">Conflict Breakdown</span>
        <div className="h-px flex-1 bg-gradient-to-r from-rose-500/20 to-transparent" />
      </div>
      <div className="relative grid gap-6 lg:grid-cols-2">
        <div className="absolute left-1/2 top-1/2 z-10 hidden -translate-x-1/2 -translate-y-1/2 items-center justify-center lg:flex">
          <div className="flex h-12 w-12 items-center justify-center rounded-full border border-white/10 bg-black text-[12px] font-black tracking-tighter text-white/40 shadow-[0_0_30px_rgba(0,0,0,1)] ring-4 ring-white/5">VS</div>
        </div>
        <div className="glass-card-static rounded-3xl glow-emerald border-emerald-500/20 bg-emerald-500/5 p-6 space-y-4 transition-all hover:bg-emerald-500/10">
          <div className="flex items-center justify-between"><span className="text-[10px] font-bold uppercase tracking-widest text-emerald-400">Support</span><Zap className="h-4 w-4 text-emerald-400" /></div>
          <p className="text-sm font-bold text-white leading-snug">{support.title}</p>
          <blockquote className="relative border-l-2 border-emerald-500/30 pl-4 py-1"><p className="text-xs leading-relaxed italic text-emerald-100/70">"{support.primary_quote || "Direct evidence detected."}"</p></blockquote>
          <div className="flex items-center gap-2 text-[10px] font-mono text-emerald-500/40"><Globe className="h-3 w-3" /><span className="truncate">{support.domain}</span></div>
        </div>
        <div className="glass-card-static rounded-3xl glow-rose border-rose-500/20 bg-rose-500/5 p-6 space-y-4 transition-all hover:bg-rose-500/10">
          <div className="flex items-center justify-between"><span className="text-[10px] font-bold uppercase tracking-widest text-rose-400">Contradict</span><ShieldAlert className="h-4 w-4 text-rose-400" /></div>
          <p className="text-sm font-bold text-white leading-snug">{conflict.title}</p>
          <blockquote className="relative border-l-2 border-rose-500/30 pl-4 py-1"><p className="text-xs leading-relaxed italic text-rose-100/70">"{conflict.primary_quote || "Counter-evidence detected."}"</p></blockquote>
          <div className="flex items-center gap-2 text-[10px] font-mono text-rose-500/40"><Globe className="h-3 w-3" /><span className="truncate">{conflict.domain}</span></div>
        </div>
      </div>
    </div>
  );
}

function SourceRow({ source }) {
  const stance = formatSourceStance(source?.stance);
  const tier = authorityTier(typeof source?.authority_score === "number" ? source.authority_score * 10 : 0);
  return (
    <div className="glass-card rounded-3xl p-6 space-y-4 transition-all hover:bg-white/[0.04] group border border-white/5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 rounded-lg bg-white/5 px-2 py-1 text-[10px] font-mono text-white/50 border border-white/5"><Globe className="h-3 w-3" />{source.domain || "Source"}</span>
          <span className={`text-[10px] font-bold uppercase tracking-widest ${stance.color}`}>{stance.label}</span>
        </div>
        <span className={`text-[10px] font-semibold ${tier.color}`}>{tier.label}</span>
      </div>
      <h4 className="text-sm font-bold text-white group-hover:text-blue-300 transition-colors line-clamp-2">{source?.title || "Untitled Document"}</h4>
      {(source?.snippet_used || source?.snippet) && (
        <p className="border-l-2 border-white/10 pl-4 text-xs italic leading-relaxed" style={{ color: "var(--ink-2)" }}>"{source.snippet_used || source.snippet}"</p>
      )}
      <div className="flex items-center justify-between pt-2">
        <span className="text-[10px] font-mono" style={{ color: "var(--ink-3)" }}>Authoritative Rank: {(source?.authority_score || 0).toFixed(1)}</span>
        <a href={source?.url} target="_blank" rel="noopener noreferrer" className="btn-secondary !py-1.5 !px-3 !text-[10px]">Access <ExternalLink className="h-3 w-3" /></a>
      </div>
    </div>
  );
}

function ClaimCard({ result, claim, anchorId }) {
  const [open, setOpen] = useState(false);
  const [viewMode, setViewMode] = useState("list");

  const verdict = result?.verdict || "UNVERIFIABLE";
  const style = VERDICT[verdict] || VERDICT.UNVERIFIABLE;
  const conf = Math.round((result?.confidence || 0) * 100);
  const sources = collectEvidenceSources(result);
  const evidenceProof = collectEvidenceProof(result);
  
  const rawClaim = String(claim?.claim || result?.claim || "");
  const displayClaim = (rawClaim.startsWith("{") || rawClaim.startsWith("[")) ? "Verification notice generated." : rawClaim;

  return (
    <article id={anchorId} className={`glass-card-static overflow-hidden rounded-[2rem] transition-all duration-500 ring-1 ${style.ring} ${style.glow} animate-fade-in-up`}>
      <div className={`flex items-center justify-between gap-4 px-6 py-5 ${style.bg} border-b border-white/5`}>
        <div className="flex items-center gap-3 min-w-0">
          <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${style.dot} shadow-[0_0_10px_rgba(255,255,255,0.2)]`} />
          <span className={`text-xs font-black uppercase tracking-[0.15em] ${style.textColor}`}>{style.label}</span>
        </div>
        <div className="flex items-center gap-2 font-mono text-[11px] text-white/40">
          <Zap className="h-3.5 w-3.5 fill-current text-blue-400" />
          <span className="font-bold text-white/60">{conf}% Consensus</span>
        </div>
      </div>

      <div className="p-7 space-y-6">
        <p className="text-lg font-bold leading-relaxed text-white">{displayClaim}</p>

        <div className="flex flex-wrap gap-x-8 gap-y-3 border-t border-white/5 pt-5 font-mono text-[10px] uppercase tracking-widest text-white/30">
          <span>{sources.length} evidence nodes</span>
          {result?.confidence_breakdown?.source_quality != null && <span>Quality Index {(result.confidence_breakdown.source_quality * 10).toFixed(1)}</span>}
          {result?.time_sensitive && <span className="text-amber-400">Temporal Risk</span>}
          {result?.conflict_detected && <span className="text-rose-400">Contentious</span>}
        </div>

        <button
          onClick={() => setOpen(!open)}
          className="flex w-full items-center justify-between gap-3 rounded-2xl bg-white/5 px-5 py-4 text-xs font-bold text-white/60 transition-all hover:bg-white/10 hover:text-white border border-white/5"
        >
          {open ? "Condense Analysis" : "Expand Verification Trail"}
          {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>

        {open && (
          <div className="space-y-8 pt-4 animate-fade-in">
            {result?.reasoning_steps?.length > 0 && (
              <div className="space-y-5">
                <div className="flex items-center gap-4"><span className="label-cap text-blue-400">Logic Chain</span><div className="h-px flex-1 bg-gradient-to-r from-blue-500/20 to-transparent" /></div>
                <div className="relative pl-10 space-y-6">
                  <div className="absolute left-[13px] top-2 bottom-6 w-0.5 bg-gradient-to-b from-blue-500 to-transparent rounded-full" />
                  {result.reasoning_steps.map((step, idx) => (
                    <div key={idx} className="relative group flex gap-5">
                      <span className="absolute -left-[35px] flex h-6 w-6 items-center justify-center rounded-full bg-[#0a0a15] border border-blue-500/40 text-[10px] font-black text-blue-300 shadow-[0_0_15px_rgba(59,130,246,0.2)]">{idx+1}</span>
                      <p className="text-sm leading-relaxed text-white/70 group-hover:text-white transition-colors">{step}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {result?.reasoning && (
              <div className="space-y-3"><div className="flex items-center gap-4"><span className="label-cap text-blue-400">Synthesis</span><div className="h-px flex-1 bg-gradient-to-r from-blue-500/20 to-transparent" /></div>
              <p className="text-sm leading-relaxed text-white/60 bg-white/[0.02] p-5 rounded-3xl border border-white/5">{result.reasoning}</p></div>
            )}

            {result?.conflict_detected && <ConflictSplitView result={result} sources={sources} />}

            <div className="space-y-5">
              <div className="flex items-center justify-between">
                <span className="label-cap text-blue-400">Evidence Suite</span>
                <div className="flex gap-2 p-1 bg-white/5 rounded-xl border border-white/5">
                  <button onClick={() => setViewMode("list")} className={`p-2 rounded-lg transition-all ${viewMode === "list" ? "bg-blue-500 text-white shadow-lg" : "text-white/30 hover:text-white/60"}`}><LayoutList className="h-3.5 w-3.5" /></button>
                  <button onClick={() => setViewMode("graph")} className={`p-2 rounded-lg transition-all ${viewMode === "graph" ? "bg-blue-500 text-white shadow-lg" : "text-white/30 hover:text-white/60"}`}><Network className="h-3.5 w-3.5" /></button>
                </div>
              </div>
              {viewMode === "graph" ? (
                <div className="rounded-3xl border border-white/5 overflow-hidden h-[400px] bg-black/20"><EvidenceGraph result={result} /></div>
              ) : (
                <div className="grid gap-4">{sources.map((s, i) => <SourceRow key={i} source={s} />)}</div>
              )}
            </div>
          </div>
        )}
      </div>
    </article>
  );
}

export default ClaimCard;
