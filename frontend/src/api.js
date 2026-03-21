// Local dev: leave unset → same-origin + Vite proxy to backend.
// Production (e.g. Vercel): set VITE_API_URL=https://oncall-rca-api.onrender.com in the host env.
const BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '');

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204 || res.headers.get('content-length') === '0') return null;
  return res.json();
}

export const api = {
  services: {
    list: () => request('/api/services'),
    get: (id) => request(`/api/services/${id}`),
    create: (body) => request('/api/services', { method: 'POST', body: JSON.stringify(body) }),
    update: (id, body) => request(`/api/services/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    delete: (id) => request(`/api/services/${id}`, { method: 'DELETE' }),
  },
  entries: {
    list: (serviceId) => request(serviceId != null ? `/api/entries?service_id=${serviceId}` : '/api/entries'),
    get: (id) => request(`/api/entries/${id}`),
    create: (body) => request('/api/entries', { method: 'POST', body: JSON.stringify(body) }),
    update: (id, body) => request(`/api/entries/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    delete: (id) => request(`/api/entries/${id}`, { method: 'DELETE' }),
  },
  search: (body) => request('/api/search', { method: 'POST', body: JSON.stringify(body) }),
  upload: (file, serviceId, updateExisting = false) => {
    const form = new FormData();
    form.append('file', file);
    form.append('service_id', String(serviceId));
    form.append('update_existing', updateExisting ? 'true' : 'false');
    return fetch(`${BASE}/api/upload`, { method: 'POST', body: form }).then(async (r) => {
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || r.statusText);
      }
      return r.json();
    });
  },
};
