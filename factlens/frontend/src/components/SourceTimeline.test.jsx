import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import SourceTimeline from "./SourceTimeline";

describe("SourceTimeline", () => {
  it("shows recovery planner strategy and notes when a recovery pass ran", () => {
    render(
      <SourceTimeline
        result={{
          supporting_evidence: [
            {
              url: "https://records.example/budget",
              title: "Budget record",
              stance: "SUPPORT",
              domain: "records.example",
              published_label: "2026-03-22",
              overall_score: 0.91,
            },
          ],
          conflicting_evidence: [],
          mixed_evidence: [],
          neutral_evidence: [],
          conflict_detected: false,
          conflict_summary: {},
          retrieval_summary: {
            source_count: 1,
            dated_count: 1,
            distinct_domain_count: 1,
            recovery_triggered: true,
            recovery_strategy: "llm_planner",
            recovery_planner_notes: "The first pass lacked an authoritative dated source.",
          },
          query_variants: [
            {
              query: "city budget 2026",
              objective: "direct",
              phase: "primary",
              planner: "llm",
            },
            {
              query: "city budget 2026 official record",
              objective: "authoritative",
              phase: "recovery",
              planner: "llm",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText(/LLM-planned recovery/i)).toBeInTheDocument();
    expect(screen.getByText(/authoritative dated source/i)).toBeInTheDocument();
    expect(screen.getAllByText("Planner").length).toBeGreaterThan(0);
  });

  it("shows provider-attempt diagnostics and temporal risk for time-sensitive claims", () => {
    render(
      <SourceTimeline
        result={{
          claim: "The current CEO of ExampleCorp is Jane Doe.",
          time_sensitive: true,
          evidence_used: [
            {
              id: "S1",
              url: "https://example.com/about",
              title: "Leadership page",
              stance: "SUPPORT",
              domain: "example.com",
              published_label: "unknown",
              overall_score: 0.81,
            },
          ],
          supporting_evidence: [],
          conflicting_evidence: [],
          mixed_evidence: [],
          neutral_evidence: [],
          conflict_detected: false,
          conflict_summary: {},
          risk_flags: [
            "The claim appears time-sensitive but none of the relevant sources were date-stamped.",
          ],
          retrieval_summary: {
            source_count: 1,
            dated_count: 0,
            distinct_domain_count: 1,
            query_attempt_count: 1,
            failed_query_count: 1,
            freshest_date: "unknown",
            recovery_triggered: false,
            recovery_strategy: "not_needed",
          },
          query_variants: [
            {
              query: "ExampleCorp current CEO official",
              objective: "authoritative",
              phase: "primary",
              provider: "bing_html",
              status: "ok",
              warning: "HTTPError('432 Client Error')",
              provider_attempts: [
                { provider: "tavily", status: "error", result_count: 0 },
                { provider: "bing_html", status: "ok", result_count: 1 },
              ],
            },
          ],
        }}
      />,
    );

    expect(screen.getByText(/Temporal risk/i)).toBeInTheDocument();
    expect(screen.getByText(/provider instability/i)).toBeInTheDocument();
    expect(screen.getAllByText(/bing_html/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/tavily:\s*failed/i)).toBeInTheDocument();
  });

  it("shows contradiction-type labels when conflicting evidence is classified", () => {
    render(
      <SourceTimeline
        result={{
          supporting_evidence: [
            {
              url: "https://example.com/support",
              title: "Leadership page",
              stance: "SUPPORT",
              domain: "example.com",
              published_label: "2026-03-20",
              overall_score: 0.91,
            },
          ],
          conflicting_evidence: [
            {
              url: "https://example.org/check",
              title: "Fact check",
              stance: "CONFLICT",
              domain: "example.org",
              published_label: "2026-03-19",
              overall_score: 0.84,
            },
          ],
          mixed_evidence: [],
          neutral_evidence: [],
          conflict_detected: true,
          conflict_summary: {
            summary: "Supporting and conflicting sources disagree mainly because of direct debunking and entity mismatch.",
            contradiction_types: [
              { id: "direct_debunking", label: "Direct debunking" },
              { id: "entity_mismatch", label: "Entity mismatch" },
            ],
          },
          retrieval_summary: {
            source_count: 2,
            dated_count: 2,
            distinct_domain_count: 2,
          },
          query_variants: [],
        }}
      />,
    );

    expect(screen.getByText(/Disagreement lens/i)).toBeInTheDocument();
    expect(screen.getByText("Direct debunking")).toBeInTheDocument();
    expect(screen.getByText("Entity mismatch")).toBeInTheDocument();
  });
});
