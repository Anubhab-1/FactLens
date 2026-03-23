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
    ring: "ring-emerald-500/25",
    bg: "bg-emerald-500/8",
  },
  FALSE: {
    label: "Factually False",
    dot: "bg-rose-400",
    textColor: "text-rose-400",
    ring: "ring-rose-500/25",
    bg: "bg-rose-500/8",
  },
  PARTIALLY_TRUE: {
    label: "Partially True",
    dot: "bg-amber-400",
    textColor: "text-amber-400",
    ring: "ring-amber-500/25",
    bg: "bg-amber-500/8",
  },
  UNVERIFIABLE: {
    label: "Unverifiable",
    dot: "bg-white/30",
    textColor: "text-white/40",
    ring: "ring-white/8",
    bg: "bg-white/4",
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
    if (!key) {
      continue;
    }

    const existing = deduped.get(key);
    if (!existing || Number(source?.overall_score || 0) > Number(existing?.overall_score || 0)) {
      deduped.set(key, source);
    }
  }

  return [...deduped.values()];
}

function formatOverridePercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "0%";
  }
  return `${Math.round(numeric * 100)}%`;
}

function formatSourceStance(value) {
  const stance = String(value || "").trim().toUpperCase();
  if (stance === "SUPPORT") {
    return { label: "support", color: "text-emerald-400" };
  }
  if (stance === "CONFLICT") {
    return { label: "conflict", color: "text-rose-400" };
  }
  if (stance === "MIXED") {
    return { label: "mixed", color: "text-amber-400" };
  }
  return { label: stance.toLowerCase() || "irrelevant", color: "text-slate-300" };
}

function formatSourceOrigin(value) {
  const origin = String(value || "").trim().toLowerCase();
  if (origin === "official") {
    return { label: "Official", color: "text-sky-300" };
  }
  if (origin === "first_party") {
    return { label: "First-party", color: "text-blue-300" };
  }
  if (origin === "reference") {
    return { label: "Reference", color: "text-violet-300" };
  }
  if (origin === "secondary") {
    return { label: "Secondary", color: "text-slate-300" };
  }
  if (origin === "social") {
    return { label: "Social", color: "text-rose-300" };
  }
  return null;
}

function formatSnapshotStamp(value) {
  if (!value) {
    return "Capture time unavailable";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

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
  if (explicitProof.length) {
    return explicitProof;
  }

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

function SourceRow({ source }) {
  const stance = formatSourceStance(source?.stance);
  const origin = formatSourceOrigin(source?.source_origin);

  return (
    <div className="glass-card p-4 space-y-2" style={{ minWidth: 0 }}>
      <div className="flex flex-wrap items-center gap-2 min-w-0">
        <span
          className="flex shrink-0 items-center gap-1 rounded-md px-2 py-0.5 font-mono text-[10px] font-semibold"
          style={{
            background: "var(--bg-hover)",
            color: "var(--ink-2)",
            border: "1px solid var(--border-faint)",
          }}
        >
          <Globe className="h-3 w-3 shrink-0" />
          <span className="truncate max-w-[120px]">{source?.domain || "Web"}</span>
        </span>
        {source?.stance ? (
          <span className={`text-[10px] font-bold uppercase tracking-wider ${stance.color}`}>
            {stance.label}
          </span>
        ) : null}
        {origin ? (
          <span className={`text-[10px] font-bold uppercase tracking-wider ${origin.color}`}>
            {origin.label}
          </span>
        ) : null}
        {Number(source?.independence_group_size || 1) > 1 && Number(source?.independence_weight || 1) < 1 ? (
          <span className="text-[10px] font-bold uppercase tracking-wider text-amber-300">
            Shared network
          </span>
        ) : null}
        {source?.published_label && source.published_label !== "unknown" ? (
          <span className="font-mono text-[10px]" style={{ color: "var(--ink-3)" }}>
            {source.published_label}
          </span>
        ) : null}
      </div>

      <h4 className="truncate text-sm font-semibold text-white">{source?.title || "Untitled source"}</h4>

      {source?.snippet_used || source?.snippet || source?.content ? (
        <p
          className="border-l-2 pl-3 text-sm leading-relaxed italic line-clamp-3"
          style={{ borderColor: "var(--border-subtle)", color: "var(--ink-2)" }}
        >
          "{source.snippet_used || source.snippet || String(source.content || "").slice(0, 200)}"
        </p>
      ) : null}

      <div className="flex items-center justify-between pt-1">
        <span className="font-mono text-[10px]" style={{ color: "var(--ink-3)" }}>
          Trust {typeof source?.authority_score === "number" ? (source.authority_score * 10).toFixed(1) : "N/A"}
        </span>
        <a
          href={source?.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-semibold transition-colors hover:text-white"
          style={{ color: "var(--ink-3)", border: "1px solid var(--border-faint)" }}
        >
          Source <ExternalLink className="h-3 w-3 shrink-0" />
        </a>
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
  const contradictionTypes = collectContradictionTypes(result);
  const manualOverride = result?.manual_override || null;
  const rawClaim = String(claim?.claim || result?.claim || "");
  const isErrorClaim = rawClaim.startsWith("{") || rawClaim.startsWith("[");
  const displayClaim = isErrorClaim
    ? "A verification step reported an internal notice."
    : rawClaim;

  return (
    <article
      id={anchorId}
      className={`glass-card-static overflow-hidden rounded-2xl ring-1 ${style.ring} animate-fade-in-up`}
      style={{ minWidth: 0 }}
    >
      <div
        className={`flex items-center justify-between gap-4 px-5 py-4 ${style.bg}`}
        style={{ borderBottom: "1px solid var(--border-faint)" }}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <span className={`h-2 w-2 shrink-0 rounded-full ${style.dot}`} />
          <span className={`text-xs font-bold uppercase tracking-wider ${style.textColor}`}>
            {style.label}
          </span>
        </div>
        <div
          className="flex shrink-0 items-center gap-1.5 font-mono text-xs"
          style={{ color: "var(--ink-3)" }}
        >
          <Zap className="h-3 w-3" />
          {conf}% confident
        </div>
      </div>

      <div className="p-5 space-y-4">
        <p
          className="text-base font-semibold leading-relaxed text-white"
          style={{ wordBreak: "break-word", overflowWrap: "break-word" }}
        >
          {displayClaim}
        </p>

        <div
          className="flex flex-wrap gap-x-6 gap-y-2 border-t pt-3 font-mono text-[10px]"
          style={{ borderColor: "var(--border-faint)", color: "var(--ink-3)" }}
        >
          <span>{sources.length} source{sources.length !== 1 ? "s" : ""}</span>
          {result?.confidence_breakdown?.source_quality != null ? (
            <span>Quality {(result.confidence_breakdown.source_quality * 10).toFixed(1)}</span>
          ) : null}
          {result?.retrieval_summary?.freshest_date ? (
            <span>Latest {result.retrieval_summary.freshest_date}</span>
          ) : null}
          {result?.temporal_context?.freshest_date && result.temporal_context.freshest_date !== "unknown" ? (
            <span>As of {result.temporal_context.freshest_date}</span>
          ) : null}
          {result?.time_sensitive ? <span className="text-amber-400">Time-sensitive</span> : null}
          {result?.conflict_detected ? <span className="text-rose-400">Conflict</span> : null}
        </div>

        {manualOverride?.active ? (
          <div
            className="rounded-2xl border border-blue-400/15 bg-blue-500/8 px-4 py-3 text-sm text-blue-100"
            style={{ borderColor: "rgba(96, 165, 250, 0.2)" }}
          >
            <p className="font-semibold text-white">Manual source review is active.</p>
            <p className="mt-1 leading-6">
              {manualOverride.override_count} source{manualOverride.override_count === 1 ? "" : "s"} changed.
              {" "}Model verdict: {String(manualOverride.base_verdict || "UNKNOWN").replace(/_/g, " ")} at{" "}
              {formatOverridePercent(manualOverride.base_confidence)} confidence.
            </p>
          </div>
        ) : null}

        <button
          type="button"
          onClick={() => setOpen((previous) => !previous)}
          className="flex w-full items-center justify-between gap-2 rounded-xl px-4 py-3 text-xs font-semibold transition-all hover:bg-white/5"
          style={{
            color: "var(--ink-2)",
            border: "1px solid var(--border-faint)",
          }}
        >
          {open ? "Hide evidence" : "Show evidence & reasoning"}
          {open ? (
            <ChevronUp className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 shrink-0" />
          )}
        </button>

        {open ? (
          <div className="space-y-5 pt-2 animate-fade-in">
            {result?.reasoning_steps?.length > 0 ? (
              <div className="space-y-3">
                <span className="label-cap">Chain of Thought</span>
                <div className="space-y-2">
                  {result.reasoning_steps.map((step, idx) => (
                    <div key={idx} className="flex gap-3 text-xs leading-relaxed" style={{ color: "var(--ink-2)" }}>
                      <span className="shrink-0 font-mono text-[10px] opacity-40">0{idx + 1}</span>
                      <p>{step}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {result?.reasoning ? (
              <div className="space-y-2">
                <span className="label-cap">Conclusion</span>
                <p
                  className="text-sm leading-relaxed text-white/70"
                  style={{ wordBreak: "break-word", overflowWrap: "break-word" }}
                >
                  {result.reasoning}
                </p>
              </div>
            ) : null}

            {result?.self_reflection ? (
              <div className="rounded-xl border border-white/5 bg-white/3 p-4 space-y-2">
                <span className="label-cap !text-[9px] opacity-50">Auditor Self-Reflection</span>
                <p className="text-xs leading-relaxed italic text-white/60">
                  "{result.self_reflection}"
                </p>
              </div>
            ) : null}

            {result?.risk_flags?.some(f => f.includes("Reflection Auditor")) ? (
              <div
                className="flex gap-3 rounded-xl p-4 bg-amber-500/10 border border-amber-500/20"
              >
                <ShieldAlert className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
                <div className="min-w-0 space-y-1">
                  <p className="text-xs font-bold text-amber-400 uppercase tracking-wider">
                    Auditor Warning
                  </p>
                  <p className="text-sm leading-relaxed text-amber-200/80">
                    {result.risk_flags.find(f => f.includes("Reflection Auditor"))}
                  </p>
                </div>
              </div>
            ) : null}

            {result?.conflict_detected && result?.conflict_summary?.summary ? (
              <div
                className="flex gap-3 rounded-xl p-4"
                style={{
                  background: "rgba(244,63,94,0.07)",
                  border: "1px solid rgba(244,63,94,0.2)",
                }}
              >
                <ShieldAlert className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
                <div className="min-w-0 space-y-1">
                  <p className="text-xs font-bold text-rose-400 uppercase tracking-wider">
                    Conflicting evidence
                  </p>
                  <p
                    className="text-sm leading-relaxed"
                    style={{ color: "var(--ink-2)", wordBreak: "break-word" }}
                  >
                    {result.conflict_summary.summary}
                  </p>
                  {contradictionTypes.length ? (
                    <div className="flex flex-wrap gap-2 pt-1">
                      {contradictionTypes.map((item) => (
                        <span
                          key={item?.id || item?.label}
                          className="rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-rose-200"
                          style={{
                            background: "rgba(244,63,94,0.12)",
                            border: "1px solid rgba(244,63,94,0.2)",
                          }}
                        >
                          {item?.label || "Unknown conflict"}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}

            {result?.temporal_context?.summary ? (
              <div
                className="flex gap-3 rounded-xl p-4"
                style={{
                  background: "rgba(245,158,11,0.08)",
                  border: "1px solid rgba(245,158,11,0.18)",
                }}
              >
                <Zap className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
                <div className="min-w-0 space-y-1">
                  <p className="text-xs font-bold text-amber-300 uppercase tracking-wider">
                    Temporal context
                  </p>
                  <p
                    className="text-sm leading-relaxed"
                    style={{ color: "var(--ink-2)", wordBreak: "break-word" }}
                  >
                    {result.temporal_context.summary}
                  </p>
                </div>
              </div>
            ) : null}

            {(result?.subclaim_results || []).length > 0 ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="label-cap">Subclaim Map</span>
                  <span className="font-mono text-[10px]" style={{ color: "var(--ink-3)" }}>
                    {result.subclaim_results.length} parts
                  </span>
                </div>
                {result?.subclaim_summary?.synthesis_note ? (
                  <p className="text-sm leading-relaxed" style={{ color: "var(--ink-2)" }}>
                    {result.subclaim_summary.synthesis_note}
                  </p>
                ) : null}
                <div className="grid gap-3">
                  {result.subclaim_results.map((subclaim) => {
                    const subclaimStyle = VERDICT[subclaim?.verdict] || VERDICT.UNVERIFIABLE;
                    const subclaimConfidence = Math.round(Number(subclaim?.confidence || 0) * 100);
                    return (
                      <div
                        key={subclaim?.subclaim_id || subclaim?.claim}
                        className="rounded-xl p-4 space-y-2"
                        style={{
                          border: "1px solid var(--border-faint)",
                          background: "rgba(255,255,255,0.02)",
                        }}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className={`text-[10px] font-bold uppercase tracking-wider ${subclaimStyle.textColor}`}>
                            {subclaimStyle.label}
                          </span>
                          <span className="font-mono text-[10px]" style={{ color: "var(--ink-3)" }}>
                            {subclaimConfidence}% confident
                          </span>
                        </div>
                        <p className="text-sm font-semibold text-white">{subclaim?.claim}</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}

            {evidenceProof.length > 0 ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="label-cap">Evidence Proof</span>
                  <span className="font-mono text-[10px]" style={{ color: "var(--ink-3)" }}>
                    {evidenceProof.length} snapshot{evidenceProof.length === 1 ? "" : "s"}
                  </span>
                </div>

                <div className="grid gap-3">
                  {evidenceProof.map((proof) => {
                    const stance = formatSourceStance(proof?.stance);
                    return (
                      <div
                        key={proof?.snapshot_id || proof?.url || proof?.source_id || proof?.source_title}
                        className="rounded-xl p-4 space-y-3"
                        style={{
                          border: "1px solid var(--border-faint)",
                          background: "rgba(255,255,255,0.02)",
                        }}
                      >
                        <div className="flex flex-wrap items-center gap-2 min-w-0">
                          <span
                            className="flex shrink-0 items-center gap-1 rounded-md px-2 py-0.5 font-mono text-[10px] font-semibold"
                            style={{
                              background: "var(--bg-hover)",
                              color: "var(--ink-2)",
                              border: "1px solid var(--border-faint)",
                            }}
                          >
                            <Globe className="h-3 w-3 shrink-0" />
                            <span className="truncate max-w-[120px]">{proof?.domain || "Web"}</span>
                          </span>
                          {proof?.stance ? (
                            <span className={`text-[10px] font-bold uppercase tracking-wider ${stance.color}`}>
                              {stance.label}
                            </span>
                          ) : null}
                          {proof?.snapshot_id ? (
                            <span className="font-mono text-[10px]" style={{ color: "var(--ink-3)" }}>
                              {proof.snapshot_id}
                            </span>
                          ) : null}
                        </div>

                        <p className="text-sm font-semibold text-white">
                          {proof?.source_title || "Untitled source"}
                        </p>

                        {proof?.primary_quote ? (
                          <p
                            className="border-l-2 pl-3 text-sm leading-relaxed italic"
                            style={{ borderColor: "var(--border-subtle)", color: "var(--ink-2)" }}
                          >
                            "{proof.primary_quote}"
                          </p>
                        ) : null}

                        <div
                          className="flex flex-wrap items-center justify-between gap-2 font-mono text-[10px]"
                          style={{ color: "var(--ink-3)" }}
                        >
                          <span>{formatSnapshotStamp(proof?.captured_at)}</span>
                          {proof?.content_hash ? <span>hash {proof.content_hash}</span> : null}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}

            {sources.length > 0 ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="label-cap">Sources ({sources.length})</span>
                  <div className="flex gap-1">
                    {[
                      { id: "list", Icon: LayoutList, label: "List" },
                      { id: "graph", Icon: Network, label: "Graph" },
                    ].map(({ id, Icon, label }) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => setViewMode(id)}
                        className={`flex items-center gap-1 rounded-lg px-2.5 py-1 text-[10px] font-semibold transition-all ${
                          viewMode === id ? "bg-white/10 text-white" : "text-white/30 hover:text-white/70"
                        }`}
                      >
                        <Icon className="h-3 w-3" /> {label}
                      </button>
                    ))}
                  </div>
                </div>

                {viewMode === "graph" ? (
                  <div
                    className="overflow-hidden rounded-xl"
                    style={{ border: "1px solid var(--border-faint)" }}
                  >
                    <EvidenceGraph result={result} />
                  </div>
                ) : (
                  <div className="grid gap-3">
                    {sources.map((source) => (
                      <SourceRow key={source.url || source.id || source.title} source={source} />
                    ))}
                  </div>
                )}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}

export default ClaimCard;
