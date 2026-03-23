export const EMPTY_PROGRESS = { done: 0, total: 0 };

const STORAGE_KEY = "factlens:sessions";
const MAX_SAVED_SESSIONS = 20;
const INTERRUPTED_SESSION_ERROR = "This analysis was interrupted before it finished.";

function isReportObject(rawSession) {
  return Boolean(rawSession?.schema_version || rawSession?.created_at || rawSession?.pipeline_stage);
}

function normalizeRawSession(rawSession) {
  if (!rawSession || typeof rawSession !== "object") {
    return null;
  }

  if (isReportObject(rawSession)) {
    return {
      id: rawSession.id,
      reportId: rawSession.id,
      status: rawSession.status,
      createdAt: rawSession.created_at,
      completedAt: rawSession.completed_at,
      lastUpdatedAt: rawSession.updated_at,
      inputMode: rawSession.input_mode,
      inputValue: rawSession.input_value,
      sourceText: rawSession.source_text,
      sourceTextTruncated: rawSession.source_text_truncated,
      sourceCapture: rawSession.source_capture,
      claimExtraction: rawSession.claim_extraction,
      pipelineStage: rawSession.pipeline_stage,
      claims: rawSession.claims,
      results: rawSession.results,
      aiDetection: rawSession.ai_detection,
      mediaDetection: rawSession.media_detection,
      evaluation: rawSession.evaluation,
      error: rawSession.error,
      progress: rawSession.progress,
      isPinned: rawSession.is_pinned,
      isArchived: rawSession.is_archived,
      shareToken: rawSession.share_token,
      canManage: rawSession.viewer_can_manage,
    };
  }

  return rawSession;
}

export function normalizeSession(rawSession) {
  const normalized = normalizeRawSession(rawSession);
  if (!normalized) {
    return null;
  }

  return {
    id: normalized.id || `${Date.now()}`,
    reportId: normalized.reportId || normalized.report_id || null,
    status: normalized.status || "done",
    createdAt: normalized.createdAt || normalized.created_at || new Date().toISOString(),
    completedAt: normalized.completedAt || normalized.completed_at || null,
    lastUpdatedAt:
      normalized.lastUpdatedAt ||
      normalized.last_updated_at ||
      normalized.createdAt ||
      normalized.created_at ||
      new Date().toISOString(),
    inputMode: normalized.inputMode || normalized.input_mode || "text",
    inputValue: normalized.inputValue || normalized.input_value || "",
    sourceText: normalized.sourceText || normalized.source_text || "",
    sourceTextTruncated: Boolean(
      normalized.sourceTextTruncated ?? normalized.source_text_truncated ?? false,
    ),
    sourceCapture: normalized.sourceCapture || normalized.source_capture || null,
    claimExtraction: normalized.claimExtraction || normalized.claim_extraction || null,
    pipelineStage: normalized.pipelineStage || normalized.pipeline_stage || "idle",
    claims: Array.isArray(normalized.claims) ? normalized.claims : [],
    results: Array.isArray(normalized.results) ? normalized.results : [],
    aiDetection: normalized.aiDetection || normalized.ai_detection || null,
    mediaDetection: normalized.mediaDetection || normalized.media_detection || null,
    evaluation: normalized.evaluation || null,
    error: normalized.error || null,
    progress: normalized.progress || EMPTY_PROGRESS,
    isPinned: Boolean(normalized.isPinned ?? normalized.is_pinned ?? false),
    isArchived: Boolean(normalized.isArchived ?? normalized.is_archived ?? false),
    shareToken: normalized.shareToken || normalized.share_token || null,
    canManage: Boolean(normalized.canManage ?? normalized.viewer_can_manage ?? normalized.reportId == null),
  };
}

function isPersistableStoredSession(rawSession) {
  const normalized = normalizeRawSession(rawSession);
  if (!normalized) {
    return false;
  }

  // Running sessions cannot be resumed from local storage. Report-backed state
  // will be restored from the backend, so keep storage focused on stable sessions.
  if (normalized.status === "running") {
    return false;
  }

  // Clean up stale synthetic errors written by older clients that converted any
  // in-progress session into an interruption banner during persistence.
  if (normalized.status === "error" && normalized.error === INTERRUPTED_SESSION_ERROR) {
    return false;
  }

  return true;
}

function sessionKey(session) {
  return session.reportId ? `report:${session.reportId}` : `local:${session.id}`;
}

function newerSession(left, right) {
  return new Date(left.lastUpdatedAt || left.createdAt || 0) >=
    new Date(right.lastUpdatedAt || right.createdAt || 0)
    ? left
    : right;
}

function mergePair(existing, incoming) {
  const preferred = newerSession(existing, incoming);
  const fallback = preferred === existing ? incoming : existing;

  return {
    ...fallback,
    ...preferred,
    id: existing.id || preferred.id,
    reportId: preferred.reportId || existing.reportId || fallback.reportId || null,
  };
}

export function mergeSessions(currentSessions, incomingSessions) {
  const merged = new Map();

  for (const session of currentSessions.map(normalizeSession).filter(Boolean)) {
    merged.set(sessionKey(session), session);
  }

  for (const rawIncoming of incomingSessions) {
    const incoming = normalizeSession(rawIncoming);
    if (!incoming) {
      continue;
    }

    const existingByReportId = incoming.reportId ? merged.get(`report:${incoming.reportId}`) : null;
    const existingByLocalId = merged.get(`local:${incoming.id}`);
    const existing = existingByReportId || existingByLocalId;

    if (!existing) {
      merged.set(sessionKey(incoming), incoming);
      continue;
    }

    const next = mergePair(existing, incoming);
    merged.delete(sessionKey(existing));
    merged.set(sessionKey(next), next);
  }

  return [...merged.values()];
}

export function trimSessions(sessions) {
  return [...sessions]
    .map(normalizeSession)
    .filter(Boolean)
    .sort((left, right) => new Date(right.createdAt) - new Date(left.createdAt))
    .slice(0, MAX_SAVED_SESSIONS);
}

export function loadStoredSessions() {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];

    if (!Array.isArray(parsed)) {
      return [];
    }

    return trimSessions(parsed.filter(isPersistableStoredSession));
  } catch {
    return [];
  }
}

export function saveStoredSessions(sessions) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(trimSessions(sessions)));
}

export function createSession({ inputMode, inputValue }) {
  const createdAt = new Date().toISOString();

  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    reportId: null,
    status: "running",
    createdAt,
    completedAt: null,
    lastUpdatedAt: createdAt,
    inputMode,
    inputValue,
    sourceText: "",
    sourceTextTruncated: false,
    sourceCapture: null,
    claimExtraction: null,
    pipelineStage: inputMode === "url" ? "scraping" : "detecting",
    claims: [],
    results: [],
    aiDetection: null,
    mediaDetection: null,
    error: null,
    progress: EMPTY_PROGRESS,
    shareToken: null,
    canManage: true,
  };
}

export function sessionFromReport(report) {
  return normalizeSession(report);
}

export function getReportRouteId(session) {
  return session?.reportId || session?.id;
}

export function getSessionStats(session) {
  const claims = session?.claims || [];
  const results = session?.results || [];
  const counts = {
    TRUE: 0,
    FALSE: 0,
    PARTIALLY_TRUE: 0,
    UNVERIFIABLE: 0,
  };

  for (const result of results) {
    counts[result.verdict] = (counts[result.verdict] || 0) + 1;
  }

  return {
    totalClaims: claims.length,
    verifiedCount: results.length,
    unresolvedCount: counts.PARTIALLY_TRUE + counts.UNVERIFIABLE,
    timeSensitiveCount: claims.filter((claim) => claim.time_sensitive).length,
    conflictCount: results.filter((result) => result.conflict_detected).length,
    counts,
  };
}

export function getSessionTitle(session) {
  const firstClaim = session?.claims?.[0]?.claim?.trim();
  if (firstClaim) {
    return firstClaim.length > 88 ? `${firstClaim.slice(0, 88)}...` : firstClaim;
  }

  const input = String(session?.inputValue || "").trim();
  if (!input) {
    return "Untitled analysis";
  }

  return input.length > 88 ? `${input.slice(0, 88)}...` : input;
}

export function formatSessionDate(value) {
  const date = value ? new Date(value) : null;

  if (!date || Number.isNaN(date.getTime())) {
    return "Unknown date";
  }

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function getFreshestEvidence(results) {
  const dates = (results || [])
    .map((result) => result.retrieval_summary?.freshest_date)
    .filter((value) => value && value !== "unknown")
    .sort()
    .reverse();

  return dates[0] || "unknown";
}
