import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import SourceReviewPanel from "./SourceReviewPanel";

function buildResult(overrides = {}) {
  return {
    claim_id: "1",
    evidence_used: [
      {
        id: "S1",
        url: "https://example.gov/support",
        title: "Government statement",
        domain: "example.gov",
        stance: overrides.currentStanceOne || "SUPPORT",
        assessment_summary: "Supports the claim.",
        overall_score: 0.92,
      },
      {
        id: "S2",
        url: "https://example.org/conflict",
        title: "Independent audit",
        domain: "example.org",
        stance: "CONFLICT",
        assessment_summary: "Conflicts with the claim.",
        overall_score: 0.86,
      },
    ],
    base_source_assessments: [
      {
        source_id: "S1",
        url: "https://example.gov/support",
        stance: "SUPPORT",
        strength: 0.94,
        summary: "Supports the claim.",
        snippet_used: "The claim is correct.",
      },
      {
        source_id: "S2",
        url: "https://example.org/conflict",
        stance: "CONFLICT",
        strength: 0.9,
        summary: "Conflicts with the claim.",
        snippet_used: "The claim is incorrect.",
      },
    ],
    manual_override: overrides.manualOverride || null,
  };
}

describe("SourceReviewPanel", () => {
  it("submits only the stances that differ from the model baseline", async () => {
    const user = userEvent.setup();
    const onApplyOverrides = vi.fn();

    render(
      <SourceReviewPanel
        result={buildResult()}
        canManage
        onApplyOverrides={onApplyOverrides}
      />,
    );

    const sourceCard = screen.getByText("Government statement").closest("article");
    await user.click(within(sourceCard).getByRole("button", { name: "Conflict" }));
    await user.click(screen.getByRole("button", { name: "Apply review" }));

    expect(onApplyOverrides).toHaveBeenCalledWith("1", [
      {
        source_id: "S1",
        source_url: "https://example.gov/support",
        stance: "CONFLICT",
      },
    ]);
  });

  it("allows the owner to restore the original model verdict", async () => {
    const user = userEvent.setup();
    const onApplyOverrides = vi.fn();

    render(
      <SourceReviewPanel
        result={buildResult({
          currentStanceOne: "CONFLICT",
          manualOverride: {
            active: true,
            override_count: 1,
            base_verdict: "PARTIALLY_TRUE",
            base_confidence: 0.72,
          },
        })}
        canManage
        onApplyOverrides={onApplyOverrides}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Restore model verdict" }));

    expect(onApplyOverrides).toHaveBeenCalledWith("1", []);
  });

  it("hides editing controls for shared viewers", () => {
    render(
      <SourceReviewPanel
        result={buildResult()}
        canManage={false}
        onApplyOverrides={vi.fn()}
      />,
    );

    expect(screen.getByText(/Only the report owner can adjust source stances/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply review" })).not.toBeInTheDocument();
  });
});
