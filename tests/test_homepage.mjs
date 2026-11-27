import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const read = path => fs.readFileSync(root + path, 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
async function activity(initialCount) {
  const state = { count: initialCount, requests: 0, fail: false };
  const events = {}, timers = [];
  const badges = ['部室に入る'].map(label => {
    const link = { dataset: { roomLabel: label }, attributes: {}, setAttribute(key, value) { this.attributes[key] = value; } };
    return { textContent: '', hidden: true, closest: () => link, link };
  });
  const document = { hidden: false, querySelectorAll: () => badges, addEventListener: (name, fn) => events[name] = fn };
  const context = vm.createContext({
    document, window: { addEventListener: (name, fn) => events[name] = fn }, AbortController,
    setTimeout: () => 1, clearTimeout: () => {}, setInterval: (fn, ms) => timers.push({ fn, ms }),
    fetch: async (url, options) => {
      state.requests++;
      assert.equal(url, 'https://shirokuma-writing-room.claska.chatgpt.site/api/room/activity');
      assert.equal(options.credentials, 'omit');
      assert.equal(options.cache, 'no-store');
      if (state.fail) throw Error('offline');
      return { ok: true, json: async () => ({ count: state.count }) };
    }
  });
  vm.runInContext(read('home/room-activity.js'), context);
  await flush();
  return { state, events, timers, badges, document };
}
test('activity is displayed in the room banner and refreshes every 30 seconds', async () => {
  const env = await activity(7);
  assert.equal(env.timers[0].ms, 30000);
  for (const badge of env.badges) {
    assert.equal(badge.textContent, '7人が活動中');
    assert.equal(badge.hidden, false);
    assert.match(badge.link.attributes['aria-label'], /（7人が活動中）$/);
  }
  env.state.count = 12;
  await env.timers[0].fn();
  assert.ok(env.badges.every(badge => badge.textContent === '12人が活動中'));
});
test('zero, invalid counts and network failures hide activity instead of showing stale numbers', async () => {
  const env = await activity(3);
  for (const count of [0, -1, '5', 1.5]) {
    env.state.count = count;
    await env.timers[0].fn();
    assert.ok(env.badges.every(badge => badge.hidden));
  }
  env.state.count = 4;
  await env.timers[0].fn();
  assert.ok(env.badges.every(badge => !badge.hidden));
  env.state.fail = true;
  await env.timers[0].fn();
  assert.ok(env.badges.every(badge => badge.hidden));
});
test('hidden pages pause activity requests and resume when visible or restored', async () => {
  const env = await activity(1);
  env.document.hidden = true;
  await env.timers[0].fn();
  assert.equal(env.state.requests, 1);
  env.document.hidden = false;
  env.events.visibilitychange();
  await flush();
  assert.equal(env.state.requests, 2);
  await env.events.pageshow();
  assert.equal(env.state.requests, 3);
});
test('the homepage links to the dedicated content pages and keeps the map noninteractive until launch', () => {
  const html = read('index.html');
  assert.equal((html.match(/<article class="content-card/g) || []).length, 4);
  assert.match(html, /href="\.\/featured\/"/);
  assert.match(html, /id="endrollEntry" aria-disabled="true" tabindex="-1"/);
  assert.equal((html.match(/data-room-activity hidden/g) || []).length, 1);
  assert.doesNotMatch(html.slice(html.indexOf('<header'), html.indexOf('</header>')), /みんなの部室|data-room-activity/);
  const coming = html.slice(html.indexOf('<article class="content-card coming-soon"'));
  assert.match(coming, /COMING SOON/);
  assert.doesNotMatch(coming.slice(0, coming.indexOf('</article>')), /<a\b/);
  assert.doesNotMatch(html, /weeklyTopic|heroBook|bookshelf/);
});
test('the credits entrance activates only for a confirmed published roll', async () => {
  async function check(data, ok = true) {
    const nodes = Object.fromEntries(['endrollEntry', 'endrollEntryLabel', 'endrollEntryStatus'].map(id => [id, {
      textContent: '準備中', hidden: true, attributes: { 'aria-disabled': 'true', tabindex: '-1' },
      removeAttribute(name) { delete this.attributes[name]; },
      setAttribute(name, value) { this.attributes[name] = value; }
    }]));
    const context = vm.createContext({
      document: { getElementById: id => nodes[id] },
      fetch: async () => ({ ok, status: ok ? 200 : 503, json: async () => data }),
      console: { info() {} }
    });
    const source = read('home/app.js');
    vm.runInContext(source.slice(0, source.lastIndexOf('loadHashtagCount();')), context);
    await vm.runInContext('loadEndrollStatus()', context);
    return nodes;
  }
  const published = await check({ version: 1, status: 'ready', workCount: 117 });
  assert.equal(published.endrollEntry.href, './twenty-credits/');
  assert.equal(published.endrollEntry.attributes['aria-disabled'], undefined);
  assert.equal(published.endrollEntryLabel.textContent, 'エンドロールを見る');
  for (const [data, ok] of [[{ version: 1, status: 'empty', workCount: 0 }, true], [{}, true], [null, false]]) {
    const nodes = await check(data, ok);
    assert.equal(nodes.endrollEntry.href, undefined);
    assert.equal(nodes.endrollEntry.attributes['aria-disabled'], 'true');
  }
});
