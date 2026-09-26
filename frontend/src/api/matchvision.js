const configured = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
export const API_BASE = configured;
const summaries = new Map();

export class ApiError extends Error {
  constructor(message, status = 0, detail = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function matchPath(id) {
  if (!/^[0-9a-f]{32}$/.test(id || '')) throw new ApiError('This analysis link is not valid.', 404);
  return `/api/matches/${id}`;
}

function errorMessage(detail, status) {
  if (status === 404) return 'This analysis or file is unavailable. The local backend forgets jobs after a restart; please upload the video again.';
  if (status === 413) return 'This video exceeds the upload size allowed by the backend. Choose a smaller file or ask the operator to increase the limit.';
  if (status === 503) return 'The analysis queue is full or the server is shutting down. Please try again later.';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => item.msg).filter(Boolean).join(' · ') || 'Please check the submitted fields.';
  return detail?.error || detail?.message || `The request could not be completed (HTTP ${status}).`;
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(API_BASE + path, options);
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new ApiError('Cannot reach MatchVision. Check that the backend is running and the configured backend URL and CORS origins are correct.');
  }
  let data;
  try {
    data = await response.json();
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new ApiError('The backend returned an unreadable response. Check the backend address and server log.', response.status);
  }
  if (!response.ok) throw new ApiError(errorMessage(data.detail, response.status), response.status, data.detail);
  return data;
}

export function uploadMatch(file, calibration, { signal } = {}) {
  const body = new FormData();
  body.append('file', file);
  if (calibration?.trim()) body.append('shot_calibration', calibration.trim());
  return request('/api/matches/upload', { method: 'POST', body, signal });
}

export function getAnalysisStatus(id, { signal } = {}) {
  return request(matchPath(id) + '/status', { signal });
}

export async function getAnalysisSummary(id, { signal, refresh = false } = {}) {
  const path = matchPath(id) + '/summary';
  if (!refresh && summaries.has(id)) return summaries.get(id);
  const result = await request(path, { signal });
  if (result.status === 'completed') {
    if (summaries.size >= 8) summaries.delete(summaries.keys().next().value);
    summaries.set(id, result);
  }
  return result;
}

// Deliberately not called by dashboard mounting or tab changes.
export function getFullResults(id, { signal } = {}) {
  return request(matchPath(id) + '/results', { signal });
}

export const getVideoUrl = id => API_BASE + matchPath(id) + '/video';
export const getHeatmapUrl = (id, name) => API_BASE + matchPath(id) + '/heatmaps/' + encodeURIComponent(name);
export const getHighlightUrl = (id, name) => API_BASE + matchPath(id) + '/highlights/' + encodeURIComponent(name);

export function mediaUrl(reference, id) {
  if (!reference || typeof reference !== 'string') return null;
  try {
    const base = new URL(API_BASE);
    const url = new URL(reference, base);
    if (!['http:', 'https:'].includes(url.protocol) || url.origin !== base.origin ||
        !url.pathname.startsWith(matchPath(id) + '/')) return null;
    return url.href;
  } catch {
    return null;
  }
}

