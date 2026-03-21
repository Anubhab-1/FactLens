export const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

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

async function parseResponse(response) {
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}.`);
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

export async function deleteReport(reportId) {
  const response = await fetch(`${API_URL}/reports/${reportId}`, withCredentials({
    method: "DELETE",
  }));
  return parseResponse(response);
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
