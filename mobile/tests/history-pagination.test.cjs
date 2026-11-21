const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/lib/history-pagination.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const exportsForTest = {};
vm.runInNewContext(source, { exports: exportsForTest, URLSearchParams, Map });
const { historyPage, mergeHistory, removeHistoryItem } = exportsForTest;

test('sessions and conversations remain reachable beyond 200 records', async () => {
  for (const path of ['/sessions?own_only=true', '/sessions/one/questions']) {
    const rows = Array.from({ length: 237 }, (_, i) => ({ id: String(i) }));
    let offset = 0, more = true, collected = [];
    const api = { async request(path) {
      const url = new URL(path, 'https://api.test');
      assert.equal(url.searchParams.get('limit'), '50');
      return rows.slice(Number(url.searchParams.get('offset')), Number(url.searchParams.get('offset')) + 50);
    } };
    while (more) {
      const page = await historyPage(api, path, offset);
      collected = mergeHistory(collected, page.items); offset = page.nextOffset; more = page.more;
    }
    assert.equal(offset, 237); assert.equal(collected.length, 237); assert.equal(collected.at(-1).id, '236');
  }
});

test('overlapping pages deduplicate rows while offsets count the raw server page', async () => {
  const page = await historyPage({ request: async () => [{ id: '49' }, { id: '50' }] }, '/sessions', 50);
  const result = mergeHistory([{ id: '49' }], page.items);
  assert.equal(result.length, 2); assert.equal(page.nextOffset, 52);
});

test('failed pages can be retried at the same offset without losing loaded history', async () => {
  const existing = [{ id: 'first' }];
  await assert.rejects(historyPage({ request: async () => { throw new Error('Offline'); } }, '/sessions', 50), /Offline/);
  assert.equal(existing.length, 1);
  const page = await historyPage({ request: async path => { assert.match(path, /offset=50/); return []; } }, '/sessions', 50);
  assert.equal(page.nextOffset, 50); assert.equal(page.more, false);
});

test('deleting a loaded session or image keeps the next unseen record reachable', async () => {
  for (const path of ['/sessions?own_only=true', '/sessions/one/frames']) {
    const server = Array.from({ length: 101 }, (_, index) => ({ id: String(index) }));
    const api = { request: async path => {
      const params = new URL(path, 'https://api.test').searchParams;
      const offset = Number(params.get('offset'));
      return server.slice(offset, offset + 50);
    } };
    const first = await historyPage(api, path);
    server.shift();
    const deleted = removeHistoryItem(first.items, '0', first.nextOffset);
    const second = await historyPage(api, path, deleted.nextOffset);
    assert.equal(second.items[0].id, '50');
    const third = await historyPage(api, path, second.nextOffset);
    const all = mergeHistory(mergeHistory(deleted.items, second.items), third.items);
    assert.equal(all.length, 100);
    assert.ok(server.every(item => all.some(loaded => loaded.id === item.id)));
  }
});

test('unknown or repeated deletions do not move the page offset again', () => {
  const first = removeHistoryItem([{ id: 'one' }, { id: 'two' }], 'one', 2);
  assert.equal(first.nextOffset, 1);
  assert.equal(removeHistoryItem(first.items, 'one', first.nextOffset).nextOffset, 1);
  assert.equal(removeHistoryItem(first.items, 'unknown', first.nextOffset).nextOffset, 1);
});
