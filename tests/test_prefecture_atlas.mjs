import test from "node:test";
import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {readFileSync} from "node:fs";
const require = createRequire(import.meta.url);
const model = require("../prefectures/app.js");
const {prefectures} = JSON.parse(readFileSync(new URL("../prefectures/map.json", import.meta.url), "utf8"));
const sample = (key, handle, tags, extra = {}) => ({
  key, url: "https://note.com/" + handle + "/n/" + key, title: "京都の旅",
  publishedAt: "2026-11-24T20:00:00+09:00",
  author: {handle, name: "旅人"}, tags: [model.TAG, ...tags], ...extra
});

test("multiple prefectures count once globally and once in each prefecture", () => {
  const data = {version: 1, tag: model.TAG, articles: [sample("n111", "writer", ["東京都", "京都府"]), sample("n111", "writer", ["東京都", "京都府"]), sample("n222", "writer", ["北海道"])]};
  const stats = model.summarize(model.parseDocument(data, prefectures), prefectures);
  assert.equal(stats.articles, 2); assert.equal(stats.creators, 1); assert.equal(stats.prefectures, 3);
  assert.equal(stats.counts.get("13").articles.size, 1); assert.equal(stats.counts.get("26").creators.size, 1);
});
test("eligibility is derived from exact registered tags, not supplied prefecture codes", () => {
  assert.equal(model.normalizeArticle(sample("n111", "writer", ["京都"], {prefectures: ["26"]}), prefectures), null);
  assert.equal(model.normalizeArticle(sample("n111", "writer", ["京都府"], {tags: ["京都府"]}), prefectures), null);
});
test("unsafe article destinations and image URLs are rejected", () => {
  assert.equal(model.normalizeArticle(sample("n111", "writer", ["京都府"], {url: "javascript:alert(1)"}), prefectures), null);
  assert.equal(model.normalizeArticle(sample("n111", "writer", ["京都府"], {url: "https://note.com/other/n/n111"}), prefectures), null);
  const article = model.normalizeArticle(sample("n111", "writer", ["京都府"], {imageUrl: "https://st-note.com.evil.example/image.png"}), prefectures);
  assert.equal(article.imageUrl, "");
});
test("prefecture selection and chronological ordering work together", () => {
  const articles = [
    model.normalizeArticle(sample("n111", "writer", ["京都府", "旅"], {title: "京都 ＣＡＦＥ", author: {handle: "writer", name: "森のしおり"}}), prefectures),
    model.normalizeArticle(sample("n222", "other", ["東京都", "食"], {publishedAt: "2026-11-25T10:00:00+09:00"}), prefectures)
  ];
  assert.deepEqual(model.filterArticles(articles, {prefecture: "26"}).map(a => a.key), ["n111"]);
  assert.deepEqual(model.filterArticles(articles, {}).map(a => a.key), ["n222", "n111"]);
});
test("Komaki preview is isolated from normal hashtag eligibility", () => {
  const article = sample("n333", "komaki_kousuke", [], {tags: ["20字小説"]});
  const debug = {version: 1, purpose: "prefecture-atlas-preview", creator: "komaki_kousuke", articles: [article]};
  assert.equal(model.normalizeArticle(article, prefectures), null);
  const preview = model.parseDebugDocument(debug);
  assert.deepEqual(preview[0].prefectures, ["13"]);
  assert.deepEqual(preview[0].tags, ["20字小説"]);
  assert.equal(preview[0].debug, true);
  assert.throws(() => model.parseDocument({...debug, tag: model.TAG}, prefectures));
});
test("debug mode only accepts the requested creator's public article identity", () => {
  const debug = {version: 1, purpose: "prefecture-atlas-preview", creator: "komaki_kousuke", articles: [sample("n333", "someone_else", ["東京都"])]};
  assert.throws(() => model.parseDebugDocument(debug));
});
test("all five color intervals include their boundary values", () => {
  assert.deepEqual([0,1,4,5,9,10,19,20,100].map(model.colorLevel), [0,1,1,2,2,3,3,4,4]);
});
test("map contains exactly the 47 official prefectures and usable geometry", () => {
  assert.equal(prefectures.length, 47);
  assert.deepEqual(prefectures.map(p => p.code), Array.from({length: 47}, (_, i) => String(i + 1).padStart(2, "0")));
  for (const pref of prefectures) {
    assert.match(pref.path, /^M/); assert.match(pref.path, /^[MLZ\d,.\s-]+$/);
    assert.equal(pref.point.length, 2); assert.ok(pref.point.every(Number.isFinite));
  }
});
test("initial production data is real and contains no demo records", () => {
  const data = JSON.parse(readFileSync(new URL("../data/prefecture-atlas.json", import.meta.url), "utf8"));
  assert.notEqual(data.sample, true);
  assert.doesNotThrow(() => model.parseDocument(data, prefectures));
});
