import { ArrowRight, Plus, Trash2, X } from "lucide-react";

function ClaimReviewPanel({
  draft,
  onUpdateClaim,
  onAddClaim,
  onRemoveClaim,
  onVerifyReviewedClaims,
  onDiscardDraft,
  isSubmitting = false,
}) {
  if (!draft) {
    return null;
  }

  const hasValidClaims = draft.claims.some((claim) => claim.claim.trim());
  const requiresExplicitReview =
    Boolean(draft.reviewRequired) || draft.claimExtraction?.mode === "heuristic";

  return (
    <section className="glass-card-static rounded-[1.75rem] p-5 animate-fade-in-up gradient-border">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-300">
            Claim review
          </p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Edit the extracted claims before verification</h2>
          <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-400">
            Remove noisy claims, rewrite ambiguous ones, or add missing atomic facts. Only the reviewed claim list will be sent into retrieval and verification.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <span className="glass-pill rounded-full px-3 py-1.5 text-xs uppercase tracking-[0.18em] text-slate-300">
            {draft.claims.length} claim{draft.claims.length === 1 ? "" : "s"}
          </span>
          {draft.sourceTextTruncated ? (
            <span className="rounded-full bg-amber-500/12 px-3 py-1.5 text-xs uppercase tracking-[0.18em] text-amber-200 ring-1 ring-inset ring-amber-400/20">
              Text truncated
            </span>
          ) : null}
        </div>
      </div>

      {requiresExplicitReview ? (
        <div className="mt-5 rounded-[1.35rem] border border-amber-400/20 bg-amber-500/10 px-4 py-4 text-sm text-amber-100 glow-amber">
          <p className="font-semibold text-white">Explicit review is required before verification.</p>
          <p className="mt-2 leading-6">
            {draft.reviewRequiredReason ||
              "FactLens had to use a heuristic claim draft, so the extracted claims must be reviewed and confirmed before retrieval and verification."}
          </p>
        </div>
      ) : null}

      <div className="mt-5 space-y-4">
        {draft.claims.length ? (
          draft.claims.map((claim, index) => (
            <article key={claim.id} className="glass-card rounded-[1.35rem] p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-white/8 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">
                    Claim {index + 1}
                  </span>
                  <span className="glass-pill rounded-full px-3 py-1 text-xs uppercase tracking-[0.16em] text-slate-400">
                    {String(claim.claim_type || "entity").replace(/_/g, " ")}
                  </span>
                  {claim.time_sensitive ? (
                    <span className="rounded-full bg-blue-500/12 px-3 py-1 text-xs uppercase tracking-[0.16em] text-blue-200 ring-1 ring-inset ring-blue-400/20">
                      Time-sensitive
                    </span>
                  ) : null}
                </div>

                <button
                  type="button"
                  onClick={() => onRemoveClaim(claim.id)}
                  className="inline-flex items-center gap-2 rounded-full border border-rose-400/15 bg-rose-500/8 px-3 py-1.5 text-xs font-medium uppercase tracking-[0.16em] text-rose-200 transition-all duration-300 hover:bg-rose-500/15"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Remove
                </button>
              </div>

              <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                <label className="block">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                    Claim text
                  </span>
                  <textarea
                    value={claim.claim}
                    onChange={(event) => onUpdateClaim(claim.id, { claim: event.target.value })}
                    rows={3}
                    className="mt-2 min-h-24 w-full rounded-[1.2rem] border border-white/8 bg-slate-950/40 px-4 py-3 text-sm leading-7 text-white outline-none transition-all duration-300 placeholder:text-slate-500 focus:border-blue-400/30 focus:bg-slate-950/60"
                  />
                </label>

                <label className="block">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                    Original context
                  </span>
                  <textarea
                    value={claim.context}
                    onChange={(event) => onUpdateClaim(claim.id, { context: event.target.value })}
                    rows={3}
                    className="mt-2 min-h-24 w-full rounded-[1.2rem] border border-white/8 bg-slate-950/40 px-4 py-3 text-sm leading-7 text-white outline-none transition-all duration-300 placeholder:text-slate-500 focus:border-blue-400/30 focus:bg-slate-950/60"
                  />
                </label>
              </div>
            </article>
          ))
        ) : (
          <div className="rounded-[1.35rem] border border-dashed border-white/8 bg-white/3 px-5 py-6 text-sm leading-7 text-slate-400">
            No claims are in the draft yet. Add one manually to continue.
          </div>
        )}
      </div>

      <div className="mt-5 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onAddClaim}
          className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-white/10"
        >
          <Plus className="h-4 w-4" />
          Add claim
        </button>
        <button
          type="button"
          onClick={onDiscardDraft}
          className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-white/10"
        >
          <X className="h-4 w-4" />
          Discard draft
        </button>
        <button
          type="button"
          onClick={onVerifyReviewedClaims}
          disabled={!hasValidClaims || isSubmitting}
          className="btn-shimmer inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-blue-400 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 transition-all duration-300 hover:scale-[1.03] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:scale-100"
        >
          <ArrowRight className="h-4 w-4" />
          {isSubmitting ? "Starting verification..." : "Verify reviewed claims"}
        </button>
      </div>
    </section>
  );
}

export default ClaimReviewPanel;
