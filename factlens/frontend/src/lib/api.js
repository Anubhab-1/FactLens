export function resolveApiUrl(
  configuredUrl = import.meta.env.VITE_API_URL,
  location = typeof window !== "undefined" ? window.location : null,
) {
  if (typeof configuredUrl === "string" && configuredUrl.trim()) {
    return configuredUrl.trim().replace(/\/$/, "");
  }

  if (location?.hostname) {
    const protocol = location.protocol === "https:" ? "https:" : "http:";
    return `${protocol}//${location.hostname}:8000`;
  }

  return "http://localhost:8000";
}

export const API_URL = resolveApiUrl();

function withCredentials(init = {}) {
  return {
    ...init,
    credentials: "include",
  };
}

function appendShareToken(url, shareToken) {
  if (!shareToken) {
    return url;
  }

  const nextUrl = new URL(url, window.location.origin);
  nextUrl.searchParams.set("share", shareToken);
  return nextUrl.toString();
}

async function parseErrorMessage(response) {
  let message = `Request failed with status ${response.status}.`;
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string" && payload.detail.trim()) {
      message = payload.detail.trim();
    }
  } catch {
    // Ignore non-JSON error bodies and keep the status-based message.
  }
  return message;
}

async function parseResponse(response) {
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return response.json();
}

export async function fetchReports({ limit = 20, offset = 0, includeArchived = false } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    include_archived: String(includeArchived),
  });
  const response = await fetch(`${API_URL}/reports?${params.toString()}`, withCredentials());
  return parseResponse(response);
}

export async function fetchReport(reportId, { shareToken } = {}) {
  const response = await fetch(
    appendShareToken(`${API_URL}/reports/${reportId}`, shareToken),
    withCredentials(),
  );
  return parseResponse(response);
}

export async function fetchClaimDraft(payload) {
  const response = await fetch(`${API_URL}/draft-claims`, {
    ...withCredentials(),
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function updateReport(reportId, payload) {
  const response = await fetch(`${API_URL}/reports/${reportId}`, {
    ...withCredentials(),
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function recalculateReportClaim(reportId, claimId, overrides) {
  const response = await fetch(`${API_URL}/reports/${reportId}/claims/${claimId}/recalculate`, {
    ...withCredentials(),
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      overrides,
    }),
  });
  return parseResponse(response);
}

export async function deleteReport(reportId) {
  const response = await fetch(`${API_URL}/reports/${reportId}`, withCredentials({
    method: "DELETE",
  }));
  return parseResponse(response);
}

export async function openAnalysisStream(payload, { reviewed = false } = {}) {
  const response = await fetch(`${API_URL}/${reviewed ? "analyze-reviewed" : "analyze"}`, {
    ...withCredentials(),
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    throw new Error(
      !response.ok ? await parseErrorMessage(response) : "The analysis stream could not be opened.",
    );
  }

  return response;
}

export function getReportExportUrl(reportId, { shareToken } = {}) {
  return appendShareToken(`${API_URL}/reports/${reportId}/export`, shareToken);
}

export function getReportPdfExportUrl(reportId, { shareToken } = {}) {
  return appendShareToken(`${API_URL}/reports/${reportId}/export/pdf`, shareToken);
}

export function getReportShareUrl(reportId, shareToken = null) {
  if (typeof window === "undefined") {
    return shareToken ? `/report/${reportId}?share=${encodeURIComponent(shareToken)}` : `/report/${reportId}`;
  }

  const nextUrl = new URL(`/report/${reportId}`, window.location.origin);
  if (shareToken) {
    nextUrl.searchParams.set("share", shareToken);
  }
  return nextUrl.toString();
}
