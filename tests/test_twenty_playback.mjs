import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { test } from "node:test";

const source = readFileSync(new URL("../twenty-credits/app.js", import.meta.url), "utf8");
// Stable private fixture; weekly public data can contain any number of works.
const publicData = { works: Array.from({ length: 90 }, (_, index) => ({
  text: "今日は昨日の私が置いた鍵で明日を開ける。", authorName: "テスト作者",
  creditGroup: index < 9 ? "membership" : "club",
})) };

async function player({ audioDuration = 646, failAudio = false, pendingAudio = false, pendingContext = false } = {}) {
  class Element {
    constructor() {
      this.children = []; this.style = {}; this.dataset = {}; this.events = new Map(); this.disabled = true;
      this.clientHeight = 800; this.offsetHeight = 12000; this.textContent = "";
      const classes = new Set();
      this.classList = { add: (...xs) => xs.forEach(x => classes.add(x)), remove: (...xs) => xs.forEach(x => classes.delete(x)),
        contains: x => classes.has(x), toggle: (x, force) => {
          const next = force ?? !classes.has(x); next ? classes.add(x) : classes.delete(x); return next;
        } };
    }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute() {}
    addEventListener(name, fn) { this.events.set(name, fn); }
  }
  const ids = new Map(["experience", "creditsTrack", "timelineFill", "loadingMessage", "toggleButton", "toggleLabel",
    "restartButton", "soundButton", "startGate", "startWithSound", "startWithoutSound", "musicStatus"].map(id => [id, new Element()]));
  let playCalls = 0;
  const audio = new Element(); Object.assign(audio, { duration: audioDuration, currentTime: 0, playbackRate: 1,
    muted: false, volume: 1, paused: true, play: () => {
      playCalls++;
      if (pendingAudio) return new Promise(() => {});
      if (failAudio) return Promise.reject(Error("audio unavailable"));
      audio.paused = false;
      return Promise.resolve();
    },
    pause: () => { audio.paused = true; } });
  ids.set("soundtrack", audio);
  let now = 0, nextFrame = 0, nextTimer = 0; const frames = new Map(), timers = new Map();
  const document = { hidden: false, documentElement: new Element(), body: new Element(),
    getElementById: id => ids.get(id), querySelector: () => new Element(), createElement: () => new Element(),
    createDocumentFragment: () => new Element(), addEventListener() {} };
  const browser = { location: { search: "" }, matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} };
  if (pendingContext) browser.AudioContext = class {
    constructor() { this.state = "suspended"; this.destination = {}; }
    createMediaElementSource() { return { connect() {} }; }
    createGain() { return { gain: { value: 0 }, connect() {} }; }
    resume() { return new Promise(() => {}); }
  };
  runInNewContext(source, { document, HTMLElement: Element, URLSearchParams,
    window: browser,
    performance: { now: () => now }, requestAnimationFrame: fn => { frames.set(++nextFrame, fn); return nextFrame; },
    cancelAnimationFrame: id => frames.delete(id), fetch: async () => ({ ok: true, json: async () => publicData }),
    setTimeout: (fn, delay) => { timers.set(++nextTimer, { fn, at: now + delay }); return nextTimer; },
    clearTimeout: id => timers.delete(id),
  });
  const settle = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
  await settle();
  const click = async id => { ids.get(id).events.get("click")(); await settle(); };
  const step = time => {
    audio.currentTime = time; now = time * 1000;
    const pending = [...frames.values()]; frames.clear(); pending.forEach(fn => fn(now));
  };
  const advance = async seconds => {
    now += seconds * 1000;
    for (const [id, timer] of timers) if (timer.at <= now) { timers.delete(id); timer.fn(); }
    await settle();
    const pending = [...frames.values()]; frames.clear(); pending.forEach(fn => fn(now));
  };
  return { ids, audio, click, step, advance, playCalls: () => playCalls, setWallClock: value => { now = value; } };
}

await test("90 real works scroll at double speed while a long soundtrack stays at normal speed", async () => {
  const p = await player();
  assert(p.ids.get("experience").classList.contains("is-awaiting-start") === false || p.audio.paused);
  await p.click("startWithSound");
  assert.equal(p.audio.playbackRate, 1); assert.equal(p.audio.loop, false);
  // Previous duration: 90 * 8 + 2 * 7 = 734 seconds. New duration: 367.
  p.step(183.5); assert.equal(p.ids.get("timelineFill").style.width, "50%");
  p.step(359); assert.equal(p.audio.volume, 0.58);
  p.step(363); assert.equal(p.audio.volume, 0.29);
  p.step(367); assert.equal(p.ids.get("timelineFill").style.width, "100%");
  assert.equal(p.audio.volume, 0); assert(p.audio.paused);
  assert(p.ids.get("experience").classList.contains("is-ended"));
});

await test("pause, resume and restart keep music aligned with the faster credits", async () => {
  const p = await player(); await p.click("startWithSound"); p.step(120);
  await p.click("toggleButton"); assert(p.audio.paused);
  p.setWallClock(240000); await p.click("toggleButton");
  assert.equal(p.audio.currentTime, 120); assert.equal(p.audio.playbackRate, 1);
  await p.click("restartButton"); assert.equal(p.audio.currentTime, 0);
  assert.equal(p.ids.get("timelineFill").style.width, "0%");
});

await test("a longer audio file never lengthens the credits and silent playback still finishes", async () => {
  for (const options of [{ audioDuration: 1200 }, { failAudio: true }]) {
    const p = await player(options); await p.click("startWithSound"); p.step(367);
    assert(p.ids.get("experience").classList.contains("is-ended"));
    assert.equal(p.audio.playbackRate, 1);
  }
});

await test("silent viewing starts and finishes without invoking audio playback", async () => {
  const p = await player({ pendingAudio: true, pendingContext: true });
  await p.click("startWithoutSound");
  assert.equal(p.playCalls(), 0);
  assert.equal(p.ids.get("experience").classList.contains("is-starting"), false);
  await p.advance(183.5);
  assert.equal(p.ids.get("timelineFill").style.width, "50%");
  await p.advance(183.5);
  assert(p.ids.get("experience").classList.contains("is-ended"));
});

await test("an audio request or suspended Web Audio context that never settles cannot block the stories", async () => {
  for (const options of [{ pendingAudio: true }, { pendingContext: true }]) {
    const p = await player(options);
    await p.click("startWithSound");
    assert(p.ids.get("experience").classList.contains("is-starting"));
    await p.advance(4);
    assert.equal(p.ids.get("experience").classList.contains("is-starting"), false);
    assert(p.audio.muted);
    assert.match(p.ids.get("musicStatus").textContent, /無音/);
    await p.advance(183.5);
    assert.equal(p.ids.get("timelineFill").style.width, "50%");
  }
});

await test("switching to silent playback releases a pending audio start immediately", async () => {
  const p = await player({ pendingAudio: true });
  await p.click("startWithSound");
  await p.click("soundButton");
  assert.equal(p.ids.get("experience").classList.contains("is-starting"), false);
  await p.advance(183.5);
  assert.equal(p.ids.get("timelineFill").style.width, "50%");
  assert.equal(p.playCalls(), 1);
});

await test("a soundtrack that stops advancing mid-roll falls back without freezing or jumping", async () => {
  const p = await player();
  await p.click("startWithSound");
  p.step(100);
  const before = p.ids.get("timelineFill").style.width;
  await p.advance(4);
  assert(p.audio.muted);
  assert.equal(p.ids.get("timelineFill").style.width, before);
  await p.advance(10);
  assert.equal(p.ids.get("timelineFill").style.width, `${110 / 367 * 100}%`);
});
