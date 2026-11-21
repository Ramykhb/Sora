import type { ApiClient } from './api';

export const HISTORY_PAGE_SIZE = 50;

export async function historyPage<T>(api: Pick<ApiClient, 'request'>, path: string, offset = 0) {
  const params = new URLSearchParams({ limit: String(HISTORY_PAGE_SIZE), offset: String(offset) });
  const items = await api.request<T[]>(`${path}${path.includes('?') ? '&' : '?'}${params}`);
  return { items, nextOffset: offset + items.length, more: items.length === HISTORY_PAGE_SIZE };
}

export function mergeHistory<T extends { id: string }>(previous: T[], incoming: T[]) {
  return [...new Map([...previous, ...incoming].map(item => [item.id, item])).values()];
}

export function removeHistoryItem<T extends { id: string }>(items: T[], id: string, offset: number) {
  const loaded = items.some(item => item.id === id);
  return { items: items.filter(item => item.id !== id), nextOffset: Math.max(0, offset - Number(loaded)) };
}
