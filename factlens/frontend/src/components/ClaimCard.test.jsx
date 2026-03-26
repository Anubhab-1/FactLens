import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ClaimCard from "./ClaimCard";

function buildResult() {
  return {
    claim_id: "1",
    claim: "Example claim",
    verdict: "FALSE",
    claim_type: "entity",
    time_sensitive: false,
    confidence: 0.87,
    confidence_breakdown: {
      support_score: 0,
      conflict_score: 1.86,
      source_quality: 0.89,
      freshness: 0.9,
    },
    retrieval_summary: {
      source_count: 2,
      authoritative_count: 2,
      dated_count: 2,
      distinct_domain_count: 2,
      recent_count: 2,
      freshest_date: "2026-03-20",
    },
    temporal_context: {
      status: "aging",
      requires_recency: true,
      dated_source_count: 2,
      freshest_date: "2026-03-20",
      oldest_date: "2026-03-18",
      summary: "This claim is time-sensitive; the newest dated evidence is from 2026-03-20, so the verdict should be treated as aging.",
    },
    subclaim_summary: {
      count: 2,
      mixed_support: true,
      verdict_breakdown: { TRUE: 1, FALSE: 1 },
      synthesis_note: "Subclaim review found that different parts of this claim resolve differently.",
    },
    subclaim_results: [
      {
        subclaim_id: "1-sub1",
        claim: "Example subclaim one",
        verdict: "TRUE",
        confidence: 0.81,
      },
      {
        subclaim_id: "1-sub2",
        claim: "Example subclaim two",
        verdict: "FALSE",
        confidence: 0.76,
      },
    ],
    conflict_summary: {
      summary: "Supporting and conflicting sources disagree mainly because of direct debunking and entity mismatch.",
      contradiction_types: [
        { id: "direct_debunking", label: "Direct debunking" },
        { id: "entity_mismatch", label: "Entity mismatch" },
      ],
    },
    conflict_detected: true,
    query_variants: [],
    risk_flags: [],
    reasoning: "The strongest available evidence contradicts the claim.",
    evidence_used: [
      {
        id: "S1",
        title: "Primary source",
        url: "https://example.com/source",
        domain: "example.com",
        published_label: "2026-03-20",
        authority_score: 0.91,
        relevance_score: 0.86,
        overall_score: 0.88,
        source_origin: "first_party",
        independence_group_size: 2,
        independence_weight: 0.82,
      },
    ],
    evidence_provenance: [
      {
        source_id: "S1",
        source_title: "Primary source",
        url: "https://example.com/source",
        domain: "example.com",
        stance: "CONFLICT",
        primary_quote: "A grounded quoted passage for the claim.",
        snapshot_id: "snapshot-abc123",
        captured_at: "2026-03-23T10:30:00Z",
        content_hash: "deadbeefcafe1234",
        top_passages: [
          {
            id: "passage-1",
            text: "A grounded quoted passage for the claim.",
            score: 0.88,
            kind: "sentence",
          },
        ],
      },
    ],
    supporting_evidence: [],
    conflicting_evidence: [],
    mixed_evidence: [],
    neutral_evidence: [],
    manual_override: {
      active: true,
      override_count: 1,
      base_verdict: "PARTIALLY_TRUE",
      base_confidence: 0.72,
    },
  };
}

describe("ClaimCard", () => {
  it("renders the collapsed verification summary", () => {
    render(
      <ClaimCard
        anchorId="claim-1"
        result={buildResult()}
        claim={{
          id: "1",
          claim: "Example claim",
          context: "Example claim with extra context.",
        }}
      />,
    );

    expect(screen.getByText("Factually False")).toBeInTheDocument();
    expect(screen.getByText("87% Consensus")).toBeInTheDocument();
    expect(screen.getByText("1 evidence nodes")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /expand verification trail/i })).toBeInTheDocument();
    expect(screen.queryByText("Synthesis")).not.toBeInTheDocument();
  });

  it("shows the reasoning and evidence suite when expanded", () => {
    render(
      <ClaimCard
        anchorId="claim-1"
        result={buildResult()}
        claim={{
          id: "1",
          claim: "Example claim",
          context: "Example claim with extra context.",
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /expand verification trail/i }));

    expect(screen.getByRole("button", { name: /condense analysis/i })).toBeInTheDocument();
    expect(screen.getByText("Synthesis")).toBeInTheDocument();
    expect(screen.getByText("The strongest available evidence contradicts the claim.")).toBeInTheDocument();
    expect(screen.getByText("Evidence Suite")).toBeInTheDocument();
    expect(screen.getByText("Primary source")).toBeInTheDocument();
    expect(screen.getByText("example.com")).toBeInTheDocument();
    expect(screen.getByText("High authority")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /access/i })).toHaveAttribute("href", "https://example.com/source");
  });
});
