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

// --- ShadowPrompt Lab API ---

export async function testLLMConnection(baseUrl, model, apiKey) {
  const response = await api.post('/lab/connect',
    { base_url: baseUrl, model },
    { headers: { 'X-LLM-API-Key': apiKey } }
  );
  return response.data;
}

export async function createCampaign(baseUrl, model, selectedLevels, apiKey) {
  const response = await api.post('/lab/campaigns',
    { base_url: baseUrl, model, selected_levels: selectedLevels },
    { headers: { 'X-LLM-API-Key': apiKey }, timeout: 60000 }
  );
  return response.data;
}

export function streamCampaign(campaignId, apiKey, onEvent, onError, onComplete) {
  // Use fetch + ReadableStream for SSE since EventSource doesn't support custom headers
  const controller = new AbortController();

  fetch(`/api/v1/lab/campaigns/${campaignId}/stream`, {
    headers: { 'X-LLM-API-Key': apiKey },
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Stream failed' }));
        onError(err.detail || `HTTP ${response.status}`);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let eventType = '';
        let eventData = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            eventData = line.slice(6).trim();
          } else if (line === '' && eventType && eventData) {
            try {
              const data = JSON.parse(eventData);
              onEvent(eventType, data);
              if (eventType === 'campaign_complete' || eventType === 'campaign_cancelled' || eventType === 'campaign_error') {
                onComplete(eventType, data);
              }
            } catch (e) {
              console.error('SSE parse error:', e);
            }
            eventType = '';
            eventData = '';
          }
        }
      }

      // Stream ended
      if (!controller.signal.aborted) {
        onComplete('stream_end', {});
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message || 'Stream connection failed');
      }
    });

  // Return cancel function
  return () => controller.abort();
}

export async function getCampaign(campaignId) {
  const response = await api.get(`/lab/campaigns/${campaignId}`);
  return response.data;
}

export async function cancelCampaign(campaignId) {
  const response = await api.post(`/lab/campaigns/${campaignId}/cancel`);
  return response.data;
}

export async function listCampaigns(page = 1, perPage = 20, status = null) {
  const params = { page, per_page: perPage };
  if (status) params.status = status;
  const response = await api.get('/lab/campaigns', { params });
  return response.data;
}

export async function getPayloads(level = null) {
  const params = {};
  if (level) params.level = level;
  const response = await api.get('/lab/payloads', { params });
  return response.data;
}

export async function generateLabReport(campaignId) {
  const response = await api.get(`/lab/campaigns/${campaignId}/report/pdf`, {
    responseType: 'blob',
  });
  return response.data;
}

export default api;
