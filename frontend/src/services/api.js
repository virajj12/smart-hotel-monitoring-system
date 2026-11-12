/**
 * API service for Smart Hotel Monitoring System
 */

const BASE_URL = '';

async function fetchJson(url, options = {}) {
  try {
    const res = await fetch(`${BASE_URL}${url}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      ...options,
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || `HTTP ${res.status}: ${res.statusText}`);
    }
    return await res.json();
  } catch (err) {
    console.error(`API Error [${url}]:`, err);
    throw err;
  }
}

export const api = {
  // Cameras
  getCameras: () => fetchJson('/cameras'),
  addCamera: (data) => fetchJson('/cameras', { method: 'POST', body: JSON.stringify(data) }),
  deleteCamera: (id) => fetchJson(`/cameras/${id}`, { method: 'DELETE' }),
  testCamera: (source, sourceType) =>
    fetchJson('/cameras/test', {
      method: 'POST',
      body: JSON.stringify({ source, source_type: sourceType }),
    }),

  // Telemetry & Logs
  getLogs: (cameraId) => fetchJson(`/logs${cameraId ? `?camera_id=${cameraId}` : ''}`),
  clearLogs: (cameraId) => fetchJson(`/clear_logs${cameraId ? `?camera_id=${cameraId}` : ''}`, { method: 'DELETE' }),
  getStats: (cameraId) => fetchJson(`/stats${cameraId ? `?camera_id=${cameraId}` : ''}`),
  getAmfvStatus: (cameraId) => fetchJson(`/amfv_status${cameraId ? `?camera_id=${cameraId}` : ''}`),
  getSystemInfo: () => fetchJson('/system_info'),

  // Analytics & Evidence
  getAnalytics: (cameraId) => fetchJson(`/analytics${cameraId ? `?camera_id=${cameraId}` : ''}`),
  getSnapshots: (cameraId, label) => {
    const params = new URLSearchParams();
    if (cameraId) params.append('camera_id', cameraId);
    if (label) params.append('label', label);
    const qs = params.toString();
    return fetchJson(`/snapshots_list${qs ? `?${qs}` : ''}`);
  },
  acknowledgeViolation: (id) => fetchJson(`/violations/${id}/acknowledge`, { method: 'POST' }),

  // System Settings
  getSettings: () => fetchJson('/settings'),
  updateSettings: (payload) =>
    fetchJson('/settings', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Export URL helper
  getCsvExportUrl: (cameraId) => `/export/csv${cameraId ? `?camera_id=${cameraId}` : ''}`,
};

