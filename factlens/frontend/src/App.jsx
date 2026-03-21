import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router-dom";

import TopNavigation from "./components/TopNavigation";
import HomePage from "./pages/HomePage";
import HistoryPage from "./pages/HistoryPage";
import MethodologyPage from "./pages/MethodologyPage";
import ReportPage from "./pages/ReportPage";
import WorkspacePage from "./pages/WorkspacePage";
import { API_URL, fetchReports } from "./lib/api";
import {
  createSession,
  loadStoredSessions,
  mergeSessions,
  saveStoredSessions,
  sessionFromReport,
  trimSessions,
} from "./lib/sessions";

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
      ].sort((left, right) => Number(left.claim_id) - Number(right.claim_id));

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

  const setDraftFromSample = (sample) => {
    setInputMode(sample.mode);
    setInputValue(sample.value);
    navigate("/workspace");
  };

  const reuseSessionInput = (session) => {
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

  const handleSubmit = async () => {
    if (!inputValue.trim() || workspaceSession?.status === "running") {
      return;
    }

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
      const response = await fetch(`${API_URL}/analyze`, {
        credentials: "include",
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok || !response.body) {
        throw new Error("The analysis stream could not be opened.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let serverReportId = null;

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
    } catch (streamError) {
      markSessionFailure(session.id, streamError.message || "The analysis failed.");
    }
  };

  return (
    <div className="min-h-screen px-4 py-6 text-slate-50 sm:px-6 lg:px-8">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <TopNavigation sessionCount={sessions.length} />

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
                setInputMode={setInputMode}
                inputValue={inputValue}
                setInputValue={setInputValue}
                onSubmit={handleSubmit}
                activeSession={workspaceSession}
                sessions={sessions}
                onUseSample={setDraftFromSample}
                onReuseSession={reuseSessionInput}
              />
            }
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
      </div>
    </div>
  );
}

export default App;
