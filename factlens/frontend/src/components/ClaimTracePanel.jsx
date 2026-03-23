function findClaimRange(sourceText, claim) {
  const haystack = String(sourceText || "");
  if (!haystack.trim()) {
    return null;
  }

  const lowerHaystack = haystack.toLowerCase();
  const candidates = [claim?.context, claim?.claim]
    .map((value) => String(value || "").trim())
    .filter(Boolean);

  for (const candidate of candidates) {
    const lowerCandidate = candidate.toLowerCase();
    const start = lowerHaystack.indexOf(lowerCandidate);
    if (start !== -1) {
      return {
        claimId: claim.id,
        start,
        end: start + candidate.length,
        matchedText: haystack.slice(start, start + candidate.length),
      };
    }
  }

  return null;
}

function buildSegments(sourceText, claims) {
  const ranges = claims
    .map((claim) => ({
      claim,
      range: findClaimRange(sourceText, claim),
    }))
    .filter((item) => item.range)
    .sort((left, right) => {
      if (left.range.start !== right.range.start) {
        return left.range.start - right.range.start;
      }
      return right.range.end - left.range.end;
    });

  const segments = [];
  let cursor = 0;

  for (const { claim, range } of ranges) {
    if (range.start < cursor) {
      continue;
    }

    if (cursor < range.start) {
      segments.push({
        type: "text",
        text: sourceText.slice(cursor, range.start),
      });
    }

    segments.push({
      type: "claim",
      claimId: claim.id,
      claimText: claim.claim,
      text: range.matchedText,
    });
    cursor = range.end;
  }

  if (cursor < sourceText.length) {
    segments.push({
      type: "text",
      text: sourceText.slice(cursor),
    });
  }

  return {
    segments,
    matchedClaimIds: ranges.map((item) => item.claim.id),
  };
}

function ClaimTracePanel({
  sourceText,
  claims,
  selectedClaimId = null,
  onSelectClaimId,
  isTruncated = false,
}) {
  if (!sourceText?.trim() || !claims?.length) {
    return null;
  }

  const { segments, matchedClaimIds } = buildSegments(sourceText, claims);
  const matchedCount = new Set(matchedClaimIds).size;

  return (
    <section className="glass-card-static rounded-[1.75rem] p-5 animate-fade-in-up">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
            Claim trace
          </p>
          <h3 className="mt-2 text-xl font-semibold text-white">Mapped back to the analyzed text</h3>
          <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-400">
            Extracted claims are highlighted directly inside the input so the report stays anchored to
            the original wording.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <span className="glass-pill rounded-full px-3 py-1.5 text-xs uppercase tracking-[0.18em] text-slate-300">
            Matched {matchedCount}/{claims.length}
          </span>
          {selectedClaimId ? (
            <span className="rounded-full bg-blue-500/12 px-3 py-1.5 text-xs uppercase tracking-[0.18em] text-blue-200 ring-1 ring-inset ring-blue-400/20">
              Focused claim {selectedClaimId}
            </span>
          ) : null}
        </div>
      </div>

      <div className="mt-5 max-h-[26rem] overflow-y-auto rounded-[1.35rem] border border-white/6 bg-slate-950/35 p-4 text-sm leading-7 text-slate-300">
        {segments.length ? (
          <p className="whitespace-pre-wrap">
            {segments.map((segment, index) =>
              segment.type === "claim" ? (
                <button
                  key={`${segment.claimId}-${index}`}
                  type="button"
                  onClick={() => onSelectClaimId?.(segment.claimId)}
                  className={`inline rounded-md px-1.5 py-0.5 text-left transition-all duration-300 ${
                    selectedClaimId === segment.claimId
                      ? "bg-blue-500/25 text-white ring-1 ring-inset ring-blue-400/30"
                      : "bg-amber-500/15 text-amber-100 ring-1 ring-inset ring-amber-400/20 hover:bg-amber-500/20"
                  }`}
                  title={segment.claimText}
                >
                  {segment.text}
                </button>
              ) : (
                <span key={`text-${index}`}>{segment.text}</span>
              ),
            )}
          </p>
        ) : (
          <p className="text-sm leading-7 text-slate-400">
            FactLens could not align the extracted claim text back to the saved source text. This can
            happen when the extractor rewrites a sentence boundary or when the input was heavily cleaned
            during scraping.
          </p>
        )}
      </div>

      {isTruncated ? (
        <p className="mt-3 text-xs uppercase tracking-[0.18em] text-amber-300">
          The stored source text was truncated for performance, so later claims may not appear in this trace.
        </p>
      ) : null}
    </section>
  );
}

export default ClaimTracePanel;
