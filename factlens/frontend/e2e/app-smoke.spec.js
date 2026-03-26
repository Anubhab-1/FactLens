import { expect, test } from "@playwright/test";

const API_ORIGIN = "http://localhost:8000";

function buildBaseSources() {
  return [
    {
      id: "S1",
      title: "City records office",
      url: "https://records.example/support",
      domain: "records.example",
      source_type: "web",
      published_date: "2026-03-22",
      published_label: "2026-03-22",
      snippet: "The city budget was approved at $18 million.",
      snippet_used: "The city budget was approved at $18 million.",
      assessment_summary: "Directly supports the claim.",
      stance: "SUPPORT",
      strength: 0.92,
      overall_score: 0.91,
      authority_score: 0.95,
      relevance_score: 0.9,
      recency_score: 0.94,
      evidence_passages: [
        {
          text: "The city budget was approved at $18 million.",
          score: 0.91,
          kind: "sentence",
        },
      ],
    },
    {
      id: "S2",
      title: "Independent audit bulletin",
      url: "https://audit.example/conflict",
      domain: "audit.example",
      source_type: "web",
      published_date: "2026-03-20",
      published_label: "2026-03-20",
      snippet: "An audit listed the approved budget at $17.2 million.",
      snippet_used: "An audit listed the approved budget at $17.2 million.",
      assessment_summary: "Conflicts with the claim amount.",
      stance: "CONFLICT",
      strength: 0.84,
      overall_score: 0.82,
      authority_score: 0.83,
      relevance_score: 0.88,
      recency_score: 0.81,
      evidence_passages: [
        {
          text: "An audit listed the approved budget at $17.2 million.",
          score: 0.84,
          kind: "sentence",
        },
      ],
    },
  ];
}

function buildReport({
  reportId = "report-qa",
  isPinned = false,
  isArchived = false,
  resultOverride = {},
} = {}) {
  const sources = buildBaseSources();
  const baseResult = {
    claim_id: "1",
    claim: "The city approved an $18 million budget in 2026.",
    claim_type: "numeric",
    time_sensitive: true,
    claim_requires_recency: true,
    verdict: "TRUE",
    confidence: 0.86,
    reasoning: "The strongest recent source supports the $18 million figure.",
    supporting_sources: [sources[0].url],
    conflicting_sources: [sources[1].url],
    conflict_detected: true,
    supporting_evidence: [sources[0]],
    conflicting_evidence: [sources[1]],
    mixed_evidence: [],
    neutral_evidence: [],
    conflict_summary: {
      summary: "The sources disagree on the exact approved amount.",
      drivers: ["numeric disagreement"],
      supporting_count: 1,
      conflicting_count: 1,
      mixed_count: 0,
      supporting_newest: "2026-03-22",
      conflicting_newest: "2026-03-20",
      supporting_avg_authority: 0.95,
      conflicting_avg_authority: 0.83,
    },
    confidence_breakdown: {
      support_score: 0.91,
      conflict_score: 0.68,
      source_quality: 0.89,
      freshness: 0.9,
      evidence_coverage: 0.7,
      clarity: 0.82,
    },
    risk_flags: ["Conflicting sources disagree on the amount."],
    query_variants: [
      {
        query: "city approved 18 million budget 2026",
        objective: "direct",
        phase: "primary",
        status: "ok",
        result_count: 6,
        added_source_count: 2,
      },
    ],
    retrieval_summary: {
      source_count: 2,
      authoritative_count: 2,
      recent_count: 2,
      dated_count: 2,
      distinct_domain_count: 2,
      freshest_date: "2026-03-22",
      domains: ["records.example", "audit.example"],
      query_attempt_count: 1,
      failed_query_count: 0,
      recovery_triggered: false,
      recovery_query_count: 0,
      recovery_reason: [],
    },
    evidence_used: sources,
    base_source_assessments: [
      {
        source_id: "S1",
        url: sources[0].url,
        stance: "SUPPORT",
        strength: 0.92,
        summary: "Directly supports the claim.",
        snippet_used: sources[0].snippet_used,
      },
      {
        source_id: "S2",
        url: sources[1].url,
        stance: "CONFLICT",
        strength: 0.84,
        summary: "Conflicts with the claim amount.",
        snippet_used: sources[1].snippet_used,
      },
    ],
    manual_override: null,
  };

  return {
    id: reportId,
    schema_version: 1,
    status: "done",
    created_at: "2026-03-22T09:00:00+00:00",
    updated_at: "2026-03-22T09:05:00+00:00",
    completed_at: "2026-03-22T09:05:00+00:00",
    input_mode: "text",
    input_value: "The city approved an $18 million budget in 2026.",
    owner_session_id: "owner-a",
    share_token: "share-token",
    pipeline_stage: "done",
    progress: { done: 1, total: 1 },
    is_pinned: isPinned,
    is_archived: isArchived,
    claims: [
      {
        id: "1",
        claim: "The city approved an $18 million budget in 2026.",
        context: "The city approved an $18 million budget in 2026.",
        time_sensitive: true,
        claim_type: "numeric",
      },
    ],
    results: [{ ...baseResult, ...resultOverride }],
    source_text: "The city approved an $18 million budget in 2026.",
    source_text_truncated: false,
    source_capture: null,
    claim_extraction: {
      mode: "llm",
      source_mode: null,
      provider: "google",
      provider_label: "Google Gemini",
      model: "gemini-1.5-pro",
      warnings: [],
      error: null,
      claim_count: 1,
    },
    ai_detection: {
      label: "LIKELY_HUMAN",
      ai_probability: 0.18,
      signals_found: ["specific phrasing"],
      explanation: "The wording looks more human than templated.",
      analysis_mode: "text_llm_stylistic_review",
      provider: "google",
      provider_label: "Google Gemini",
      model: "gemini-1.5-pro",
      review_recommended: false,
      warnings: [],
      limitations: ["This is a stylistic estimate, not proof of authorship."],
    },
    media_detection: null,
    error: null,
    viewer_can_manage: true,
  };
}

function buildRecalculatedReport(report) {
  const updatedSources = buildBaseSources().map((source) =>
    source.id === "S1"
      ? {
          ...source,
          stance: "CONFLICT",
          assessment_summary: "Manual review reclassified this as conflicting evidence.",
        }
      : source,
  );

  return {
    ...report,
    updated_at: "2026-03-22T09:10:00+00:00",
    results: [
      {
        ...report.results[0],
        verdict: "FALSE",
        confidence: 0.74,
        reasoning: "Verdict recalculated after manually reclassifying 1 source.",
        supporting_sources: [],
        conflicting_sources: updatedSources.map((source) => source.url),
        supporting_evidence: [],
        conflicting_evidence: updatedSources,
        mixed_evidence: [],
        neutral_evidence: [],
        evidence_used: updatedSources,
        conflict_detected: true,
        confidence_breakdown: {
          support_score: 0.0,
          conflict_score: 0.89,
          source_quality: 0.89,
          freshness: 0.9,
          evidence_coverage: 0.7,
          clarity: 0.78,
        },
        conflict_summary: {
          summary: "Manual review now treats both key sources as conflicting.",
          drivers: ["manual override", "numeric disagreement"],
          supporting_count: 0,
          conflicting_count: 2,
          mixed_count: 0,
          supporting_newest: "unknown",
          conflicting_newest: "2026-03-22",
          supporting_avg_authority: 0.0,
          conflicting_avg_authority: 0.89,
        },
        risk_flags: [
          "Conflicting sources disagree on the amount.",
          "Manual review changed 1 source stance.",
        ],
        manual_override: {
          active: true,
          updated_at: "2026-03-22T09:10:00+00:00",
          override_count: 1,
          overrides: [
            {
              source_id: "S1",
              url: "https://records.example/support",
              from_stance: "SUPPORT",
              to_stance: "CONFLICT",
            },
          ],
          base_verdict: "TRUE",
          base_confidence: 0.86,
        },
      },
    ],
  };
}

async function fulfillJson(route, payload, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

async function installMockApi(page, state) {
  await page.route(`${API_ORIGIN}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();

    if (url.pathname === "/reports" && method === "GET") {
      const includeArchived = url.searchParams.get("include_archived") === "true";
      const offset = Number(url.searchParams.get("offset") || "0");
      const limit = Number(url.searchParams.get("limit") || "20");
      const visibleReports = state.reports.filter((report) => includeArchived || !report.is_archived);
      const pageReports = visibleReports.slice(offset, offset + limit);
      await fulfillJson(route, {
        reports: pageReports,
        total: visibleReports.length,
        limit,
        offset,
        has_more: offset + pageReports.length < visibleReports.length,
      });
      return;
    }

    if (url.pathname === "/draft-claims" && method === "POST") {
      await fulfillJson(route, state.claimDraft);
      return;
    }

    const reportMatch = url.pathname.match(/^\/reports\/([^/]+)$/);
    if (reportMatch && method === "GET") {
      const report = state.reports.find((item) => item.id === reportMatch[1]);
      await fulfillJson(route, report || { detail: "Report not found." }, report ? 200 : 404);
      return;
    }

    if (reportMatch && method === "PATCH") {
      const report = state.reports.find((item) => item.id === reportMatch[1]);
      const payload = JSON.parse(request.postData() || "{}");
      if (!report) {
        await fulfillJson(route, { detail: "Report not found." }, 404);
        return;
      }
      if (typeof payload.is_pinned === "boolean") {
        report.is_pinned = payload.is_pinned;
      }
      if (typeof payload.is_archived === "boolean") {
        report.is_archived = payload.is_archived;
      }
      report.updated_at = "2026-03-22T09:12:00+00:00";
      await fulfillJson(route, report);
      return;
    }

    if (reportMatch && method === "DELETE") {
      state.reports = state.reports.filter((item) => item.id !== reportMatch[1]);
      await fulfillJson(route, { deleted: true, report_id: reportMatch[1] });
      return;
    }

    const recalcMatch = url.pathname.match(/^\/reports\/([^/]+)\/claims\/([^/]+)\/recalculate$/);
    if (recalcMatch && method === "POST") {
      const index = state.reports.findIndex((item) => item.id === recalcMatch[1]);
      if (index === -1) {
        await fulfillJson(route, { detail: "Report not found." }, 404);
        return;
      }
      state.reports[index] = buildRecalculatedReport(state.reports[index]);
      await fulfillJson(route, state.reports[index]);
      return;
    }

    await fulfillJson(route, { detail: `Unhandled mock route for ${method} ${url.pathname}` }, 404);
  });
}

test("workspace review flow renders extraction and authenticity panels", async ({ page }) => {
  const state = {
    reports: [],
    claimDraft: {
      input_mode: "text",
      input_value: "The city approved an $18 million budget in 2026.",
      source_text: "The city approved an $18 million budget in 2026.",
      source_text_truncated: false,
      source_capture: null,
      claims: [
        {
          id: "1",
          claim: "The city approved an $18 million budget in 2026.",
          context: "The city approved an $18 million budget in 2026.",
          time_sensitive: true,
          claim_type: "numeric",
        },
      ],
      claim_extraction: {
        mode: "heuristic",
        source_mode: null,
        provider: null,
        provider_label: null,
        model: null,
        warnings: ["Heuristic extraction was used."],
        error: null,
        claim_count: 1,
      },
      review_required: true,
      ai_detection: {
        label: "LIKELY_HUMAN",
        ai_probability: 0.12,
        signals_found: ["specific phrasing"],
        explanation: "The passage has uneven phrasing and reads like a human draft.",
        analysis_mode: "text_llm_stylistic_review",
        provider: "google",
        provider_label: "Google Gemini",
        model: "gemini-1.5-pro",
        review_recommended: false,
        warnings: [],
        limitations: ["This is a stylistic estimate, not proof of authorship."],
      },
      media_detection: null,
    },
  };

  await installMockApi(page, state);
  await page.goto("/workspace");

  await page
    .getByPlaceholder("Paste an article, transcript, or social post to extract and verify its claims.")
    .fill("The city approved an $18 million budget in 2026.");
  await page.getByRole("button", { name: "Extract & Review" }).click();

  await expect(page.getByRole("heading", { name: /Edit the extracted claims before verification/i })).toBeVisible();
  await expect(page.getByText("Explicit review is required before verification.")).toBeVisible();
  await expect(page.getByText("Likely human-written text")).toBeVisible();
  await expect(page.getByRole("button", { name: "Verify reviewed claims" })).toBeVisible();
});

test("report page recalculates a claim after manual source review", async ({ page }) => {
  const state = {
    reports: [buildReport()],
    claimDraft: null,
  };

  await installMockApi(page, state);
  await page.goto("/report/report-qa");

  await expect(page.getByRole("heading", { name: /Source stance override/i })).toBeVisible();
  await expect(page.getByText("Current SUPPORT")).toBeVisible();

  const reviewPanel = page.locator("section").filter({ hasText: "Source stance override" }).first();
  const sourceCard = reviewPanel.locator("article").filter({ hasText: "City records office" }).first();
  await sourceCard.getByRole("button", { name: "Conflict" }).click();
  await expect(sourceCard.getByText("Current CONFLICT")).toBeVisible();
  await page.getByRole("button", { name: "Apply review" }).click();

  await expect(page.getByText("Manual review is active.")).toBeVisible();
  await expect(page.getByText(/Model verdict: TRUE at 86% confidence./i)).toBeVisible();
  await expect(page.locator("#claim-1")).toContainText("Factually False");
  await expect(page.getByRole("link", { name: "JSON" })).toHaveAttribute(
    "href",
    `${API_ORIGIN}/reports/report-qa/export?share=share-token`,
  );
});

test("history actions stay usable on mobile without horizontal overflow", async ({ page }) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width: 390, height: 844 });

  const state = {
    reports: [buildReport({ reportId: "report-history" })],
    claimDraft: null,
  };

  await installMockApi(page, state);
  await page.addInitScript(() => {
    window.confirm = () => true;
  });
  await page.goto("/history");

  await expect(page.getByRole("heading", { name: /Saved analyses/i })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();

  await page.getByRole("button", { name: "Pin" }).click();
  await expect(page.getByText("Pinned")).toBeVisible();

  await page.getByRole("button", { name: "Archive" }).click();
  await expect(page.getByText(/No active analyses right now/i)).toBeVisible();

  await page.getByRole("button", { name: "All reports" }).click();
  await expect(page.getByRole("button", { name: "Delete" })).toBeVisible();
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("There are no saved reports yet.")).toBeVisible();
});
