import { useEffect, useState } from "react";
import { RefreshCcw, ShieldCheck } from "lucide-react";

const STANCE_OPTIONS = [
  { value: "SUPPORT", label: "Support" },
  { value: "CONFLICT", label: "Conflict" },
  { value: "MIXED", label: "Mixed" },
  { value: "IRRELEVANT", label: "Ignore" },
];

const STANCE_META = {
  SUPPORT: "bg-emerald-500/12 text-emerald-200 ring-1 ring-inset ring-emerald-400/20",
  CONFLICT: "bg-rose-500/12 text-rose-200 ring-1 ring-inset ring-rose-400/20",
  MIXED: "bg-amber-500/12 text-amber-200 ring-1 ring-inset ring-amber-400/20",
  IRRELEVANT: "bg-slate-500/12 text-slate-200 ring-1 ring-inset ring-slate-400/20",
};

function normalizeStance(value) {
  const normalized = String(value || "IRRELEVANT").trim().toUpperCase();
  return STANCE_META[normalized] ? normalized : "IRRELEVANT";
}

function formatPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "0%";
  }
  return `${Math.round(numeric * 100)}%`;
}

function collectReviewSources(result) {
  const evidenceBuckets = (result?.evidence_used || []).length
    ? result.evidence_used
    : [
        ...(result?.supporting_evidence || []),
        ...(result?.conflicting_evidence || []),
        ...(result?.mixed_evidence || []),
        ...(result?.neutral_evidence || []),
      ];
  const baseByKey = new Map();

  for (const assessment of result?.base_source_assessments || []) {
    const sourceId = String(assessment?.source_id || "").trim();
    const sourceUrl = String(assessment?.url || "").trim();
    const stance = normalizeStance(assessment?.stance);
    if (sourceId) {
      baseByKey.set(`id:${sourceId}`, stance);
    }
    if (sourceUrl) {
      baseByKey.set(`url:${sourceUrl}`, stance);
    }
  }

  const deduped = new Map();
  for (const source of evidenceBuckets) {
    const sourceId = String(source?.id || "").trim();
    const sourceUrl = String(source?.url || "").trim();
    const key = sourceId ? `id:${sourceId}` : `url:${sourceUrl}`;
    if (!key || (!sourceId && !sourceUrl)) {
      continue;
    }

    const existing = deduped.get(key);
    if (!existing || Number(source?.overall_score || 0) > Number(existing?.overall_score || 0)) {
      deduped.set(key, {
        key,
        sourceId,
        url: sourceUrl,
        title: source?.title || sourceUrl || "Untitled source",
        domain: source?.domain || "unknown",
        summary: source?.assessment_summary || source?.snippet_used || source?.snippet || "",
        overallScore: Number(source?.overall_score || 0),
        currentStance: normalizeStance(source?.stance),
        baseStance: normalizeStance(
          baseByKey.get(key) ||
            (sourceUrl ? baseByKey.get(`url:${sourceUrl}`) : null) ||
            source?.stance,
        ),
      });
    }
  }

  return [...deduped.values()].sort((left, right) => right.overallScore - left.overallScore);
}

function SourceReviewPanel({ result, canManage, onApplyOverrides, isBusy = false, error = null }) {
  const sources = collectReviewSources(result);
  const [draftStances, setDraftStances] = useState({});
  const sourceSignature = JSON.stringify(
    sources.map((source) => [source.key, source.currentStance, source.baseStance]),
  );
  const manualOverride = result?.manual_override || null;

  useEffect(() => {
    const nextDraft = {};
    for (const source of sources) {
      nextDraft[source.key] = source.currentStance;
    }
    setDraftStances(nextDraft);
  }, [sourceSignature]);

  if (!sources.length) {
    return null;
  }

  const hasUnsavedChanges = sources.some(
    (source) => normalizeStance(draftStances[source.key] || source.currentStance) !== source.currentStance,
  );
  const pendingOverrides = sources
    .map((source) => {
      const nextStance = normalizeStance(draftStances[source.key] || source.currentStance);
      if (nextStance === source.baseStance) {
        return null;
      }

      return {
        source_id: source.sourceId || undefined,
        source_url: source.url || undefined,
        stance: nextStance,
      };
    })
    .filter(Boolean);

  const handleSelectStance = (sourceKey, stance) => {
    if (!canManage || isBusy) {
      return;
    }

    setDraftStances((current) => ({
      ...current,
      [sourceKey]: stance,
    }));
  };

  const handleApply = () => {
    if (!canManage || isBusy || !hasUnsavedChanges) {
      return;
    }
    onApplyOverrides(result.claim_id, pendingOverrides);
  };

  const handleResetDraft = () => {
    const nextDraft = {};
    for (const source of sources) {
      nextDraft[source.key] = source.currentStance;
    }
    setDraftStances(nextDraft);
  };

  const handleRestoreModel = () => {
    if (!canManage || isBusy || !manualOverride?.active) {
      return;
    }
    onApplyOverrides(result.claim_id, []);
  };

  return (
    <section className="glass-card-static rounded-[1.75rem] p-4 animate-fade-in-up sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Manual review</p>
          <h3 className="mt-2 text-lg font-semibold text-white sm:text-xl">Source stance override</h3>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            Reclassify how each source relates to the claim, then recalculate the verdict from the same evidence set.
          </p>
        </div>
        <span className="glass-pill inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium text-white/80">
          <ShieldCheck className="h-4 w-4 shrink-0 text-blue-300" />
          {canManage ? "Owner controls" : "Read only"}
        </span>
      </div>

      {manualOverride?.active ? (
        <div className="mt-4 rounded-[1.3rem] border border-blue-400/15 bg-blue-500/8 px-4 py-4 text-sm text-blue-100">
          <p className="font-semibold text-white">Manual review is active.</p>
          <p className="mt-2 leading-6">
            {manualOverride.override_count} source{manualOverride.override_count === 1 ? "" : "s"} changed.
            Model verdict: {String(manualOverride.base_verdict || "unknown").replace(/_/g, " ")} at{" "}
            {formatPercent(manualOverride.base_confidence)} confidence.
          </p>
        </div>
      ) : null}

      {!canManage ? (
        <div className="mt-4 rounded-[1.3rem] border border-white/8 bg-white/4 px-4 py-4 text-sm text-slate-300">
          Only the report owner can adjust source stances. Shared viewers still see the current evidence breakdown.
        </div>
      ) : null}

      {error ? (
        <div className="mt-4 rounded-[1.3rem] border border-rose-400/20 bg-rose-500/8 px-4 py-4 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      <div className="mt-4 space-y-3">
        {sources.map((source) => {
          const selectedStance = normalizeStance(draftStances[source.key] || source.currentStance);
          const differsFromModel = selectedStance !== source.baseStance;

          return (
            <article key={source.key} className="glass-card rounded-[1.35rem] p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-white">{source.title}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <span className="glass-pill rounded-full px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                      {source.domain}
                    </span>
                    <span
                      className={`rounded-full px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] ${STANCE_META[selectedStance]}`}
                    >
                      Current {selectedStance.replace(/_/g, " ")}
                    </span>
                    {selectedStance !== source.baseStance ? (
                      <span
                        className={`rounded-full px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] ${STANCE_META[source.baseStance]}`}
                      >
                        Model {source.baseStance.replace(/_/g, " ")}
                      </span>
                    ) : null}
                  </div>
                </div>
                {differsFromModel ? (
                  <span className="rounded-full bg-blue-500/12 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-blue-200 ring-1 ring-inset ring-blue-400/20">
                    Override draft
                  </span>
                ) : null}
              </div>

              {source.summary ? (
                <p className="mt-3 text-sm leading-6 text-slate-400">{source.summary}</p>
              ) : null}

              {canManage ? (
                <div className="mt-4 grid grid-cols-2 gap-2">
                  {STANCE_OPTIONS.map((option) => {
                    const active = selectedStance === option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => handleSelectStance(source.key, option.value)}
                        disabled={isBusy}
                        className={`rounded-2xl px-3 py-2 text-sm font-medium transition-all duration-300 ${
                          active
                            ? `${STANCE_META[option.value]} shadow-lg`
                            : "border border-white/8 bg-white/4 text-slate-300 hover:bg-white/8"
                        } disabled:cursor-not-allowed disabled:opacity-50`}
                      >
                        {option.label}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </article>
          );
        })}
      </div>

      {canManage ? (
        <div className="mt-5 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleApply}
            disabled={isBusy || !hasUnsavedChanges}
            className="btn-shimmer inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-blue-400 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 transition-all duration-300 hover:scale-[1.03] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isBusy ? "Recalculating..." : "Apply review"}
          </button>
          {hasUnsavedChanges ? (
            <button
              type="button"
              onClick={handleResetDraft}
              disabled={isBusy}
              className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Reset draft
            </button>
          ) : manualOverride?.active ? (
            <button
              type="button"
              onClick={handleRestoreModel}
              disabled={isBusy}
              className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RefreshCcw className="h-4 w-4" />
              Restore model verdict
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default SourceReviewPanel;
