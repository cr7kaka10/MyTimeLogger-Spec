const originalFetch = global.fetch;
global.fetch = async (url, options = {}) => {
  const requestUrl = String(url);
  if (/\/auth\/(?:login|me)(?:\?|$)/.test(requestUrl) || /\/api\/sync\//.test(requestUrl)) {
    const path = requestUrl; let body = {};
    if (path.endsWith('/auth/login')) body = { status: 'ok', token: 'isolated-server-token', username: 'isolated' };
    else if (path.includes('/auth/me')) body = { status: 'ok', username: 'isolated' };
    else if (path.includes('/api/sync/pull')) body = { status: 'ok', tables: {}, changes: [], from_version: 0, to_version: 0, server_time: '2026-07-11 16:00:00' };
    else if (path.includes('/api/sync/push')) body = { status: 'ok', operation_results: [], server_time: '2026-07-11 16:00:00' };
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }
  if (!requestUrl.startsWith('https://app.atimelogger.pro')) return originalFetch(url, options);
  await new Promise(resolve => setTimeout(resolve, 250));
  const path = requestUrl; const method = options.method || 'GET'; let body = {};
  if (path.endsWith('/api/types')) body = [{ id: 'type-input', name: '输入', group: false, deleted: false, archived: false }];
  else if (path.includes('/api/intervals')) body = { content: [] };
  else if (path.endsWith('/api/activities') && method === 'GET') body = [];
  else body = { id: `slow-${Date.now()}`, typeId: 'type-input', status: 'STOPPED', intervals: [{ id: `interval-${Date.now()}` }] };
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
};
