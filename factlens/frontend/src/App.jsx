import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router-dom";

import TopNavigation from "./components/TopNavigation";
import { fetchClaimDraft, fetchReports, openAnalysisStream } from "./lib/api";
import {
  createSession,
  loadStoredSessions,
  mergeSessions,
  saveStoredSessions,
  sessionFromReport,
  trimSessions,
} from "./lib/sessions";

const HomePage = lazy(() => import("./pages/HomePage"));
const DemoPage = lazy(() => import("./pages/DemoPage"));
const HistoryPage = lazy(() => import("./pages/HistoryPage"));
const MethodologyPage = lazy(() => import("./pages/MethodologyPage"));
const ReportPage = lazy(() => import("./pages/ReportPage"));
const WorkspacePage = lazy(() => import("./pages/WorkspacePage"));

function claimSortKey(value) {
  const text = String(value || "").trim();
  if (/^\d+$/.test(text)) {
    return [0, Number(text)];
  }
  return [1, text];
}

function applyPayloadToSession(session, payload) {
  const timestamp = new Date().toISOString();

  switch (payload.type) {
    case "report_created":
      return {
        ...session,
        reportId: payload.data?.report_id || session.reportId,
        lastUpdatedAt: timestamp,
      };
    case "scraping_done":
      return {
        ...session,
        pipelineStage: "detecting",
        sourceCapture: payload.data?.source_capture ?? session.sourceCapture ?? null,
        lastUpdatedAt: timestamp,
      };
    case "source_text_ready":
      return {
        ...session,
        sourceText: payload.data?.source_text ?? "",
        sourceTextTruncated: Boolean(payload.data?.source_text_truncated),
        lastUpdatedAt: timestamp,
      };
    case "media_detection_start":
      return {
        ...session,
        pipelineStage: "media_detecting",
        lastUpdatedAt: timestamp,
      };
    case "media_detection_result":
      return {
        ...session,
        mediaDetection: payload.data,
        lastUpdatedAt: timestamp,
      };
    case "ai_detection_start":
      return {
        ...session,
        pipelineStage: "detecting",
        lastUpdatedAt: timestamp,
      };
    case "ai_detection_result":
      return {
        ...session,
        aiDetection: payload.data,
        lastUpdatedAt: timestamp,
      };
    case "extracting_start":
      return {
        ...session,
        pipelineStage: "extracting",
        lastUpdatedAt: timestamp,
      };
    case "extracting_done":
      return {
        ...session,
        claims: payload.data?.claims ?? [],
        claimExtraction: payload.data?.claim_extraction ?? session.claimExtraction ?? null,
        lastUpdatedAt: timestamp,
      };
    case "review_required":
      return {
        ...session,
        status: "needs_review",
        pipelineStage: "extracting",
        claims: payload.data?.claims ?? session.claims,
        claimExtraction: payload.data?.claim_extraction ?? session.claimExtraction ?? null,
        sourceText: payload.data?.source_text ?? session.sourceText,
        sourceTextTruncated: Boolean(
          payload.data?.source_text_truncated ?? session.sourceTextTruncated,
        ),
        sourceCapture: payload.data?.source_capture ?? session.sourceCapture ?? null,
        aiDetection: payload.data?.ai_detection ?? session.aiDetection ?? null,
        mediaDetection: payload.data?.media_detection ?? session.mediaDetection ?? null,
        completedAt: timestamp,
        lastUpdatedAt: timestamp,
      };
    case "retrieving_start":
      return {
        ...session,
        pipelineStage: "retrieving",
        progress: { done: 0, total: payload.data?.total ?? 0 },
        lastUpdatedAt: timestamp,
      };
    case "retrieving_progress":
      return {
        ...session,
        pipelineStage: "retrieving",
        progress: {
          done: payload.data?.done ?? 0,
          total: payload.data?.total ?? 0,
        },
        lastUpdatedAt: timestamp,
      };
    case "verifying_start":
      return {
        ...session,
        pipelineStage: "verifying",
        progress: { done: 0, total: payload.data?.total ?? 0 },
        lastUpdatedAt: timestamp,
      };
    case "verifying_progress": {
      const nextResults = [
        ...session.results.filter((item) => item.claim_id !== payload.data.claim_id),
        payload.data,
      ].sort((left, right) => {
        const leftKey = claimSortKey(left.claim_id);
        const rightKey = claimSortKey(right.claim_id);
        if (leftKey[0] !== rightKey[0]) {
          return leftKey[0] - rightKey[0];
        }
        if (typeof leftKey[1] === "number" && typeof rightKey[1] === "number") {
          return leftKey[1] - rightKey[1];
        }
        return String(leftKey[1]).localeCompare(String(rightKey[1]));
      });

      return {
        ...session,
        pipelineStage: "verifying",
        results: nextResults,
        progress: {
          done: nextResults.length,
          total: session.progress.total || session.claims.length || nextResults.length,
        },
        lastUpdatedAt: timestamp,
      };
    }
    case "verifying_status":
      return {
        ...session,
        pipelineStage: "verifying",
        progress: {
          done: payload.data?.done ?? 0,
          total: payload.data?.total ?? 0,
        },
        lastUpdatedAt: timestamp,
      };
    case "reflecting_start":
      return {
        ...session,
        pipelineStage: "reflecting",
        lastUpdatedAt: timestamp,
      };
    case "done":
      return {
        ...session,
        pipelineStage: "done",
        status: "done",
        completedAt: timestamp,
        lastUpdatedAt: timestamp,
      };
    case "error":
      return {
        ...session,
        status: "error",
        error: payload.message || "The analysis failed.",
        completedAt: timestamp,
        lastUpdatedAt: timestamp,
      };
    default:
      return session;
  }
}

function App() {
  return (
    <BrowserRouter>
      <FactLensApp />
    </BrowserRouter>
  );
}

function FactLensApp() {
  const navigate = useNavigate();
  const [inputMode, setInputMode] = useState("text");
  const [inputValue, setInputValue] = useState("");
  const [sessions, setSessions] = useState(() => loadStoredSessions());
  const [workspaceSessionId, setWorkspaceSessionId] = useState(null);
  const [claimDraft, setClaimDraft] = useState(null);
  const [isPreparingDraft, setIsPreparingDraft] = useState(false);
  const [isSubmittingReviewedClaims, setIsSubmittingReviewedClaims] = useState(false);

  useEffect(() => {
    let active = true;

    fetchReports()
      .then((payload) => {
        if (!active) {
          return;
        }

        setSessions((current) =>
          trimSessions(
            mergeSessions(current, (payload.reports || []).map(sessionFromReport)).filter(
              (session) => !session.isArchived,
            ),
          ),
        );
      })
      .catch(() => {});

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    saveStoredSessions(sessions);
  }, [sessions]);

  useEffect(() => {
    if (!workspaceSessionId && sessions.length) {
      setWorkspaceSessionId(sessions[0].id);
    }
  }, [workspaceSessionId, sessions]);

  const workspaceSession = sessions.find((session) => session.id === workspaceSessionId) || null;

  const clearClaimDraft = useCallback(() => {
    setClaimDraft(null);
  }, []);

  const buildClaimDraft = useCallback((payload, fallbackInputMode, fallbackInputValue) => {
    return {
      status: "ready",
      inputMode: payload.input_mode || fallbackInputMode,
      inputValue: payload.input_value || fallbackInputValue,
      sourceText: payload.source_text || "",
      sourceTextTruncated: Boolean(payload.source_text_truncated),
      sourceCapture: payload.source_capture || null,
      claimExtraction: payload.claim_extraction || null,
      claims: (payload.claims || []).map((claim, index) => ({
        id: claim.id || `draft-${index + 1}`,
        claim: claim.claim || "",
        context: claim.context || claim.claim || "",
        time_sensitive: Boolean(claim.time_sensitive),
        claim_type: claim.claim_type || "entity",
      })),
      aiDetection: payload.ai_detection || null,
      mediaDetection: payload.media_detection || null,
      reviewRequired: Boolean(payload.review_required),
      reviewRequiredReason: payload.review_required_message || null,
      error: null,
    };
  }, []);

  const updateSession = (sessionId, updater) => {
    setSessions((current) =>
      trimSessions(
        current.map((session) => (session.id === sessionId ? updater(session) : session)),
      ),
    );
  };

  const addSession = (session) => {
    setSessions((current) =>
      trimSessions([session, ...current.filter((item) => item.id !== session.id)]),
    );
  };

  const upsertReportSession = useCallback((report) => {
    const incoming = sessionFromReport(report);
    setSessions((current) =>
      trimSessions(mergeSessions(current, [incoming])).filter((session) => !session.isArchived),
    );
  }, []);

  const removeReportSession = useCallback((reportId) => {
    setSessions((current) =>
      trimSessions(current.filter((session) => session.reportId !== reportId && session.id !== reportId)),
    );
  }, []);

  const removeSessionById = useCallback((sessionId) => {
    setSessions((current) => trimSessions(current.filter((session) => session.id !== sessionId)));
  }, []);

  const setDraftFromSample = (sample) => {
    clearClaimDraft();
    setInputMode(sample.mode);
    setInputValue(sample.value);
    navigate("/workspace");
  };

  const reuseSessionInput = (session) => {
    clearClaimDraft();
    setInputMode(session.inputMode || "text");
    setInputValue(session.inputValue || "");
    setWorkspaceSessionId(session.id);
    navigate("/workspace");
  };

  const markSessionFailure = (sessionId, message) => {
    updateSession(sessionId, (session) => ({
      ...session,
      status: "error",
      error: message,
      completedAt: new Date().toISOString(),
      lastUpdatedAt: new Date().toISOString(),
    }));
  };

  const readAnalysisStream = async ({ session, payload, reviewed = false }) => {
    const response = await openAnalysisStream(payload, { reviewed });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let serverReportId = null;
    let reviewRequiredPayload = null;

    const flushBuffer = () => {
      let boundaryIndex = buffer.indexOf("\n\n");

      while (boundaryIndex !== -1) {
        const eventBlock = buffer.slice(0, boundaryIndex).trim();
        buffer = buffer.slice(boundaryIndex + 2);

        for (const line of eventBlock.split("\n")) {
          if (!line.startsWith("data: ")) {
            continue;
          }

          const eventPayload = JSON.parse(line.slice(6));
          if (eventPayload.type === "report_created") {
            serverReportId = eventPayload.data?.report_id || serverReportId;
          }
          if (eventPayload.type === "review_required") {
            reviewRequiredPayload = eventPayload;
          }
          updateSession(session.id, (current) => applyPayloadToSession(current, eventPayload));

          if (eventPayload.type === "done") {
            navigate(`/report/${eventPayload.data?.report_id || serverReportId || session.id}`);
          }
        }

        boundaryIndex = buffer.indexOf("\n\n");
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      flushBuffer();

      if (done) {
        buffer += decoder.decode();
        flushBuffer();
        break;
      }
    }

    return {
      reviewRequired: reviewRequiredPayload,
    };
  };

  const handleSubmit = async () => {
    if (
      !inputValue.trim() ||
      workspaceSession?.status === "running" ||
      isPreparingDraft ||
      isSubmittingReviewedClaims
    ) {
      return;
    }

    clearClaimDraft();

    const session = createSession({
      inputMode,
      inputValue,
    });

    addSession(session);
    setWorkspaceSessionId(session.id);
    navigate("/workspace");

    const payload =
      inputMode === "url"
        ? { url: inputValue.trim() }
        : { text: inputValue.trim() };

    try {
      const streamResult = await readAnalysisStream({ session, payload });
      if (streamResult?.reviewRequired?.data) {
        setClaimDraft(
          buildClaimDraft(
            {
              ...streamResult.reviewRequired.data,
              review_required_message: streamResult.reviewRequired.message || null,
            },
            inputMode,
            inputValue,
          ),
        );
        removeSessionById(session.id);
        setWorkspaceSessionId(null);
        navigate("/workspace");
      }
    } catch (streamError) {
      markSessionFailure(session.id, streamError.message || "The analysis failed.");
    }
  };

  const handlePrepareClaimDraft = async () => {
    if (
      !inputValue.trim() ||
      workspaceSession?.status === "running" ||
      isPreparingDraft ||
      isSubmittingReviewedClaims
    ) {
      return;
    }

    setIsPreparingDraft(true);
    setClaimDraft(null);
    navigate("/workspace");

    const payload =
      inputMode === "url"
        ? { url: inputValue.trim() }
        : { text: inputValue.trim() };

    try {
      const draft = await fetchClaimDraft(payload);
      setClaimDraft(buildClaimDraft(draft, inputMode, inputValue));
    } catch (error) {
      setClaimDraft({
        status: "error",
        inputMode,
        inputValue,
        sourceText: "",
        sourceTextTruncated: false,
        sourceCapture: null,
        claims: [],
        claimExtraction: null,
        aiDetection: null,
        mediaDetection: null,
        error: error.message || "The claim draft could not be prepared.",
      });
    } finally {
      setIsPreparingDraft(false);
    }
  };

  const updateDraftClaim = (claimId, changes) => {
    setClaimDraft((current) => {
      if (!current) {
        return current;
      }

      return {
        ...current,
        claims: current.claims.map((claim) =>
          claim.id === claimId ? { ...claim, ...changes } : claim,
        ),
      };
    });
  };

  const addDraftClaim = () => {
    setClaimDraft((current) => {
      if (!current) {
        return current;
      }

      return {
        ...current,
        claims: [
          ...current.claims,
          {
            id: `manual-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            claim: "",
            context: "",
            time_sensitive: false,
            claim_type: "entity",
          },
        ],
      };
    });
  };

  const removeDraftClaim = (claimId) => {
    setClaimDraft((current) => {
      if (!current) {
        return current;
      }

      return {
        ...current,
        claims: current.claims.filter((claim) => claim.id !== claimId),
      };
    });
  };

  const handleVerifyReviewedClaims = async () => {
    if (!claimDraft || isSubmittingReviewedClaims || workspaceSession?.status === "running") {
      return;
    }

    const reviewedClaims = claimDraft.claims
      .map((claim) => ({
        ...claim,
        claim: claim.claim.trim(),
        context: (claim.context || claim.claim).trim(),
      }))
      .filter((claim) => claim.claim);

    if (!reviewedClaims.length) {
      setClaimDraft((current) =>
        current
          ? { ...current, status: "error", error: "Add at least one non-empty claim before verification." }
          : current,
      );
      return;
    }

    setIsSubmittingReviewedClaims(true);
    const session = {
      ...createSession({
        inputMode: claimDraft.inputMode,
        inputValue: claimDraft.inputValue,
      }),
      sourceText: claimDraft.sourceText,
      sourceTextTruncated: claimDraft.sourceTextTruncated,
      sourceCapture: claimDraft.sourceCapture,
      claimExtraction: claimDraft.claimExtraction,
      claims: reviewedClaims,
      aiDetection: claimDraft.aiDetection,
      mediaDetection: claimDraft.mediaDetection,
      pipelineStage: "extracting",
    };

    addSession(session);
    setWorkspaceSessionId(session.id);
    setClaimDraft(null);
    navigate("/workspace");

    try {
      await readAnalysisStream({
        session,
        reviewed: true,
        payload: {
          input_mode: claimDraft.inputMode,
          input_value: claimDraft.inputValue,
          source_text: claimDraft.sourceText,
          source_capture: claimDraft.sourceCapture,
          claims: reviewedClaims,
          claim_extraction: claimDraft.claimExtraction,
          ai_detection: claimDraft.aiDetection,
          media_detection: claimDraft.mediaDetection,
        },
      });
    } catch (streamError) {
      markSessionFailure(session.id, streamError.message || "The analysis failed.");
    } finally {
      setIsSubmittingReviewedClaims(false);
    }
  };

  const handleSetInputMode = (mode) => {
    clearClaimDraft();
    setInputMode(mode);
  };

  const handleSetInputValue = (value) => {
    clearClaimDraft();
    setInputValue(value);
  };

  const pageFallback = (
    <div className="page-wrapper">
      <div className="glass-card-static p-6 text-sm" style={{ color: "var(--ink-2)" }}>
        Loading page...
      </div>
    </div>
  );

  return (
    <>
      <TopNavigation sessionCount={sessions.length} />
      <Suspense fallback={pageFallback}>
        <Routes>
          <Route
            path="/"
            element={
              <HomePage
                sessions={sessions}
                onUseSample={setDraftFromSample}
                onReuseSession={reuseSessionInput}
              />
            }
          />
          <Route
            path="/workspace"
            element={
              <WorkspacePage
                inputMode={inputMode}
                setInputMode={handleSetInputMode}
                inputValue={inputValue}
                setInputValue={handleSetInputValue}
                onSubmit={handleSubmit}
                onReviewClaims={handlePrepareClaimDraft}
                activeSession={workspaceSession}
                claimDraft={claimDraft}
                isPreparingDraft={isPreparingDraft}
                isSubmittingReviewedClaims={isSubmittingReviewedClaims}
                onUpdateDraftClaim={updateDraftClaim}
                onAddDraftClaim={addDraftClaim}
                onRemoveDraftClaim={removeDraftClaim}
                onDiscardDraft={clearClaimDraft}
                onVerifyReviewedClaims={handleVerifyReviewedClaims}
                sessions={sessions}
                onUseSample={setDraftFromSample}
                onReuseSession={reuseSessionInput}
              />
            }
          />
          <Route
            path="/demo"
            element={<DemoPage onUseSample={setDraftFromSample} />}
          />
          <Route
            path="/report/:sessionId"
            element={
              <ReportPage
                sessions={sessions}
                onHydrateReport={upsertReportSession}
                onRemoveReport={removeReportSession}
                onUpsertReport={upsertReportSession}
                onReuseSession={reuseSessionInput}
                onUseSample={setDraftFromSample}
              />
            }
          />
          <Route
            path="/history"
            element={
              <HistoryPage
                sessions={sessions}
                onRemoveReport={removeReportSession}
                onUpsertReport={upsertReportSession}
                onReuseSession={reuseSessionInput}
              />
            }
          />
          <Route path="/methodology" element={<MethodologyPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </>
  );
}

export default App;
