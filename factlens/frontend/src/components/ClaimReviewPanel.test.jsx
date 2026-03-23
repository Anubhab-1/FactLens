import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ClaimReviewPanel from "./ClaimReviewPanel";

describe("ClaimReviewPanel", () => {
  it("shows an explicit verification gate when the draft is heuristic", () => {
    render(
      <ClaimReviewPanel
        draft={{
          claims: [
            {
              id: "1",
              claim: "Mars has two moons named Phobos and Deimos.",
              context: "Mars has two moons named Phobos and Deimos.",
              claim_type: "entity",
              time_sensitive: false,
            },
          ],
          sourceTextTruncated: false,
          reviewRequired: true,
          reviewRequiredReason:
            "Automatic verification paused because FactLens had to use a heuristic claim draft.",
          claimExtraction: {
            mode: "heuristic",
          },
        }}
        onUpdateClaim={vi.fn()}
        onAddClaim={vi.fn()}
        onRemoveClaim={vi.fn()}
        onVerifyReviewedClaims={vi.fn()}
        onDiscardDraft={vi.fn()}
      />,
    );

    expect(screen.getByText("Explicit review is required before verification.")).toBeInTheDocument();
    expect(screen.getByText(/Automatic verification paused because FactLens had to use a heuristic claim draft/i)).toBeInTheDocument();
  });
});
