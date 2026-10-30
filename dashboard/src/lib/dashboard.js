export async function loadDashboard(api, userId, signal) {
  const [sessions, summary, metrics] = await Promise.allSettled([
    api.request('/sessions?own_only=true&limit=200', 'GET', undefined, signal),
    api.request('/dashboard?own_only=true&limit=200', 'GET', undefined, signal),
    api.request('/dashboard/statistics?own_only=true', 'GET', undefined, signal),
  ]);
  if (sessions.status === 'rejected') throw sessions.reason;
  const byId = new Map(summary.status === 'fulfilled' ? summary.value.sessions.map(item => [item.session_id, item]) : []);
  const warnings = [];
  if (summary.status === 'rejected') warnings.push('Session summaries could not load.');
  if (metrics.status === 'rejected') warnings.push('Session statistics could not load.');
  return {
    sessions: sessions.value.filter(item => item.owner_id === userId).map(item => ({ ...item, ...byId.get(item.id) })),
    metrics: metrics.status === 'fulfilled' ? metrics.value : null,
    warning: warnings.join(' '),
  };
}
