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

async function player({ audioDuration = 646, failAudio = false } = {}) {
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
  const audio = new Element(); Object.assign(audio, { duration: audioDuration, currentTime: 0, playbackRate: 1,
    muted: false, volume: 1, paused: true, play: async () => { if (failAudio) throw Error("audio unavailable"); audio.paused = false; },
    pause: () => { audio.paused = true; } });
  ids.set("soundtrack", audio);
  let now = 0, nextFrame = 0; const frames = new Map();
  const document = { hidden: false, documentElement: new Element(), body: new Element(),
    getElementById: id => ids.get(id), querySelector: () => new Element(), createElement: () => new Element(),
    createDocumentFragment: () => new Element(), addEventListener() {} };
  runInNewContext(source, { document, HTMLElement: Element, URLSearchParams,
    window: { location: { search: "" }, matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} },
    performance: { now: () => now }, requestAnimationFrame: fn => { frames.set(++nextFrame, fn); return nextFrame; },
    cancelAnimationFrame: id => frames.delete(id), fetch: async () => ({ ok: true, json: async () => publicData }),
  });
  const settle = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
  await settle();
  const click = async id => { ids.get(id).events.get("click")(); await settle(); };
  const step = time => {
    audio.currentTime = time; now = time * 1000;
    const pending = [...frames.values()]; frames.clear(); pending.forEach(fn => fn(now));
  };
  return { ids, audio, click, step, setWallClock: value => { now = value; } };
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
