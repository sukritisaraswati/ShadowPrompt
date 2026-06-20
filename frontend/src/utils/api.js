import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Response interceptor for consistent error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.data?.detail) {
      const detail = error.response.data.detail;
      if (typeof detail === 'object') {
        error.userMessage = detail.error || 'An error occurred';
        error.errorCode = detail.error_code || 'UNKNOWN';
      } else {
        error.userMessage = detail;
        error.errorCode = 'UNKNOWN';
      }
    } else if (error.code === 'ECONNABORTED') {
      error.userMessage = 'Request timed out. The target may be slow to respond.';
      error.errorCode = 'TIMEOUT';
    } else if (!error.response) {
      error.userMessage = 'Cannot connect to the server. Please ensure the backend is running.';
      error.errorCode = 'NETWORK_ERROR';
    } else {
      error.userMessage = `Server error (${error.response.status})`;
      error.errorCode = 'SERVER_ERROR';
    }
    return Promise.reject(error);
  }
);

// --- ShadowScan API ---

export async function scanUrl(url) {
  const response = await api.post('/scan/url', { url });
  return response.data;
}

export async function scanFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/scan/html', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

export async function getScanResult(scanId) {
  const response = await api.get(`/scan/results/${scanId}`);
  return response.data;
}

export async function listScanResults(page = 1, limit = 20, severity = null) {
  const params = { page, limit };
  if (severity) params.severity = severity;
  const response = await api.get('/scan/results', { params });
  return response.data;
}

export async function getDemoPages() {
  const response = await api.get('/scan/demo-pages');
  return response.data;
}

export async function scanDemoPage(pageId) {
  const response = await api.post(`/scan/demo-pages/${pageId}/scan`);
  return response.data;
}

export async function generateReport(scanId) {
  const response = await api.post('/scan/reports', { scan_id: scanId }, {
    responseType: 'blob',
  });
  return response.data;
}

export async function getHealth() {
  const response = await api.get('/health');
  return response.data;
}

export default api;
