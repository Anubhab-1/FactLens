import { beforeEach, describe, expect, it } from "vitest";

import {
  getAverageResultConfidence,
  getCredibilityScore,
  loadStoredSessions,
  normalizeSession,
  sessionFromReport,
} from "./sessions";

describe("sessions", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("preserves actively running sessions during normalization", () => {
    const session = normalizeSession({
      id: "local-running",
      status: "running",
      createdAt: "2026-03-22T10:00:00.000Z",
      lastUpdatedAt: "2026-03-22T10:00:01.000Z",
      inputMode: "text",
      inputValue: "Example input",
    });

    expect(session.status).toBe("running");
    expect(session.error).toBeNull();
  });

  it("preserves running report state from the backend", () => {
    const session = sessionFromReport({
      id: "report-1",
      status: "running",
      created_at: "2026-03-22T10:00:00.000Z",
      updated_at: "2026-03-22T10:00:01.000Z",
      input_mode: "text",
      input_value: "Example input",
      pipeline_stage: "retrieving",
      claims: [],
      results: [],
    });

    expect(session.status).toBe("running");
    expect(session.pipelineStage).toBe("retrieving");
    expect(session.error).toBeNull();
  });

  it("drops stale interrupted sessions from local storage", () => {
    window.localStorage.setItem(
      "factlens:sessions",
      JSON.stringify([
        {
          id: "stale-running",
          status: "running",
          createdAt: "2026-03-22T10:00:00.000Z",
          lastUpdatedAt: "2026-03-22T10:00:05.000Z",
          inputMode: "text",
          inputValue: "Old input",
        },
        {
          id: "legacy-interrupted",
          status: "error",
          error: "This analysis was interrupted before it finished.",
          createdAt: "2026-03-22T10:01:00.000Z",
          lastUpdatedAt: "2026-03-22T10:01:05.000Z",
          inputMode: "text",
          inputValue: "Interrupted input",
        },
        {
          id: "done-report",
          status: "done",
          createdAt: "2026-03-22T10:02:00.000Z",
          lastUpdatedAt: "2026-03-22T10:02:05.000Z",
          inputMode: "text",
          inputValue: "Completed input",
        },
      ]),
    );

    const sessions = loadStoredSessions();

    expect(sessions).toHaveLength(1);
    expect(sessions[0].id).toBe("done-report");
    expect(sessions[0].status).toBe("done");
  });

  it("computes credibility score consistently from weighted verdicts and confidence", () => {
    const results = [
      { verdict: "TRUE", confidence: 0.9 },
      { verdict: "PARTIALLY_TRUE", confidence: 0.7 },
      { verdict: "UNVERIFIABLE", confidence: 0.5 },
      { verdict: "FALSE", confidence: 0.8 },
    ];

    expect(getAverageResultConfidence(results)).toBe(0.725);
    expect(getCredibilityScore(results)).toBe(31);
  });

  it("returns zero credibility for empty result sets", () => {
    expect(getAverageResultConfidence([])).toBe(0);
    expect(getCredibilityScore([])).toBe(0);
  });
});
