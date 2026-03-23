import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import EvaluationPanel from "./EvaluationPanel";

describe("EvaluationPanel", () => {
  it("renders extraction, retrieval, verification, and quality-flag diagnostics", () => {
    render(
      <EvaluationPanel
        evaluation={{
          summary: {
            total_claims: 4,
            average_confidence: 0.73,
            conservative_claim_rate: 0.5,
          },
          extraction: {
            mode: "manual_review",
            warning_count: 2,
            compound_claim_count: 1,
            atomic_claim_rate: 0.75,
          },
          retrieval: {
            recovery_rate: 0.5,
            avg_query_attempt_count: 3.5,
            avg_sources_per_claim: 2.8,
            avg_independent_source_count: 2.2,
            provider_instability_claim_count: 1,
          },
          verification: {
            low_confidence_claim_count: 1,
            high_confidence_claim_count: 2,
            manual_override_claim_count: 1,
            reflection_adjusted_claim_count: 1,
            contradiction_type_breakdown: [
              { id: "date_drift", label: "Date drift", count: 2 },
              { id: "scope_mismatch", label: "Scope mismatch", count: 1 },
            ],
          },
          quality_flags: [
            "Claims were manually reviewed before verification.",
            "Retrieval relied heavily on recovery search.",
          ],
        }}
      />,
    );

    expect(screen.getByText(/Calibration snapshot/i)).toBeInTheDocument();
    expect(screen.getByText("Mode: manual review")).toBeInTheDocument();
    expect(screen.getByText("Avg queries: 3.5")).toBeInTheDocument();
    expect(screen.getByText("Date drift: 2")).toBeInTheDocument();
    expect(screen.getByText(/Retrieval relied heavily on recovery search/i)).toBeInTheDocument();
  });
});
