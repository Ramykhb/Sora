const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/lib/history-pagination.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const exportsForTest = {};
vm.runInNewContext(source, { exports: exportsForTest, URLSearchParams, Map });
const { historyPage, mergeHistory } = exportsForTest;

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
