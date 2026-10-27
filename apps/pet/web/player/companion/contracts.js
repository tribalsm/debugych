export const defaults = { backendUrl: 'http://127.0.0.1:8000', frontendUrl: 'http://127.0.0.1:5173', projectId: '', runId: '', enabled: true, notifications: true, phrases: true, contextualAIEnabled: false };
export const uuid = (s) => typeof s === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s);
export function baseUrl(value) { const url = new URL(value); if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || !['', '/'].includes(url.pathname))
    throw Error('Укажите http(s) адрес сервера без пути, логина и параметров'); return url.origin; }
