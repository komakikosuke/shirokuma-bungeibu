import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const read = path => fs.readFileSync(root + path, 'utf8');
function merger(path, stop) {
  const context = vm.createContext({ window: {}, URL });
  vm.runInContext(read('assets/featured-week.js'), context);
  const source = read(path);
  vm.runInContext(source.slice(0, source.indexOf(stop)), context);
  return (...args) => JSON.parse(JSON.stringify(vm.runInContext('merge', context)(...args)));
}
const featured = merger('featured/app.js', '$("retryWorks").addEventListener');
const archive = merger('articles/app.js', '$("loadMore").addEventListener');
const wrap = works => ({ version: 1, works });
const decisions = value => ({ version: 1, decisions: value });
const work = (handle, firstCommentAt, extra = {}) => ({ month: '2026-11', handle, title: '参加作品', url: `https://note.com/${handle}/n/n123`, firstCommentAt, ...extra });

test('the dedicated page selects the same published works and order as the archive', () => {
  const args = ['data/works.json', 'data/candidates.json', 'data/admin-decisions.json'].map(path => JSON.parse(read(path)));
  assert.deepEqual(featured(...args), archive(...args));
});
test('duplicate comments in one editorial week keep one work; a later week may feature the writer again', () => {
  const early = work('writer_a', '2026-11-19T12:00:00Z');
  const duplicate = work('writer_a', '2026-11-20T12:00:00Z', { title: '別の作品' });
  const nextWeek = work('writer_a', '2026-11-26T12:00:00Z');
  assert.deepEqual(featured(wrap([early]), wrap([duplicate, nextWeek]), decisions({})), [nextWeek, early]);
});
test('held, excluded and legacy excluded works remain hidden', () => {
  const held = work('held_writer', '2026-11-26T12:00:00Z', { weekStart: '2026-11-26' });
  const excluded = work('excluded_writer', '2026-11-26T12:01:00Z', { weekStart: '2026-11-26' });
  const legacy = work('legacy_writer', '2026-11-19T12:00:00Z');
  const allowed = work('allowed_writer', '2026-11-26T12:03:00Z');
  assert.deepEqual(featured(wrap([held, excluded, legacy, allowed]), wrap([]), decisions({
    '2026-11-26|held_writer': { status: 'draft' },
    '2026-11-26|excluded_writer': { status: 'excluded' },
    '2026-11|legacy_writer': { status: 'excluded' }
  })), [allowed]);
});
test('unsafe or mismatched article links are rejected, and missing editorial state fails closed', () => {
  const good = work('writer_a', '2026-11-26T12:00:00Z');
  const bad = [work('writer_a', '', { url: 'javascript:alert(1)' }), work('writer_a', '', { url: 'https://note.com/other_writer/n/n123' })];
  assert.deepEqual(featured(wrap([good, ...bad]), wrap([]), decisions({})), [good]);
  assert.throws(() => featured(wrap([good]), wrap([]), null));
});
