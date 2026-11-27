"use strict";
// Keep candidate selection aligned with articles/app.js and the existing homepage.
const $ = id => document.getElementById(id);
const NOTE = /^https:\/\/note\.com\/[A-Za-z0-9_-]+\/n\/n[A-Za-z0-9]+\/?$/;
let names = {};
let loading = false;
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function safeWork(work) {
  if (!work || typeof work !== "object" || typeof work.month !== "string" || !/^\d{4}-\d{2}$/.test(work.month)) return false;
  if (typeof work.handle !== "string" || !/^[A-Za-z0-9_-]{2,100}$/.test(work.handle)) return false;
  if (typeof work.title !== "string" || !work.title.trim() || work.title.length > 500) return false;
  if (typeof work.url !== "string" || !NOTE.test(work.url)) return false;
  return new URL(work.url).pathname.split("/")[1] === work.handle;
}
function merge(works, candidates, decisions) {
  if (!works || works.version !== 1 || !Array.isArray(works.works) ||
      !candidates || candidates.version !== 1 || !Array.isArray(candidates.works) ||
      !decisions || decisions.version !== 1 || !decisions.decisions || typeof decisions.decisions !== "object") {
    throw Error("掲載データの形式が正しくありません");
  }
  const unique = new Map();
  for (const work of [...works.works, ...candidates.works]) {
    if (!safeWork(work)) continue;
    const key = window.shirokumaWeekKey(work), previous = unique.get(key);
    if (!previous || String(work.firstCommentAt || "") < String(previous.firstCommentAt || "")) unique.set(key, work);
  }
  for (const [key, work] of unique) {
    if (["draft", "excluded"].includes(window.shirokumaDecisionStatus(work, decisions.decisions))) unique.delete(key);
  }
  return [...unique.values()].sort((a, b) => String(b.firstCommentAt || "").localeCompare(String(a.firstCommentAt || "")) || b.month.localeCompare(a.month));
}
async function getData(name) {
  const response = await fetch("../data/" + name + "?v=" + Date.now(), { cache: "no-store" });
  if (!response.ok) throw Error(name + ": HTTP " + response.status);
  return response.json();
}
function articleCard(work) {
  const rawName = names[work.handle]?.name;
  const name = typeof rawName === "string" && rawName.trim() ? rawName.trim() : "クリエイター名を確認中";
  const card = element("article", "article-item");
  const coverLink = element("a", "cover-link");
  coverLink.href = work.url;
  coverLink.target = "_blank";
  coverLink.rel = "noopener noreferrer";
  coverLink.setAttribute("aria-label", name + "「" + work.title + "」を読む");
  const book = element("div", "mini-book");
  const content = element("div", "mini-content");
  const title = element("h3", "mini-title");
  title.title = work.title;
  title.append(element("span", "cover-fit-text", work.title));
  const rule = element("div", "mini-rule");
  rule.setAttribute("aria-hidden", "true");
  const byline = element("p", "mini-creator cover-fit");
  byline.append(element("span", "cover-fit-text", name));
  const imprint = element("div", "mini-footer");
  imprint.append(element("strong", "", "シロクマ文芸部"), element("small", "", "SHIROKUMA BUNGEIBU"));
  content.append(title, rule, byline, imprint);
  book.append(content);
  coverLink.append(book);
  const read = element("a", "read-link", "読む");
  read.href = work.url;
  read.target = "_blank";
  read.rel = "noopener noreferrer";
  read.setAttribute("aria-label", name + "「" + work.title + "」を読む");
  card.append(coverLink, read);
  return card;
}
function render(articles) {
  const lead = $("leadWork"), recent = $("recentWorks");
  lead.replaceChildren();
  recent.replaceChildren();
  if (articles.length) {
    lead.append(articleCard(articles[0]));
    for (const work of articles.slice(1, 6)) recent.append(articleCard(work));
  } else {
    lead.append(element("p", "lead-status", "注目記事は準備中です。"));
  }
  if (articles.length < 2) recent.append(element("p", "empty", "新しい注目記事が加わると、ここに並びます。"));
  window.shirokumaFitCovers?.();
}
async function loadWorks() {
  if (loading) return;
  loading = true;
  $("loadError").hidden = true;
  $("retryWorks").disabled = true;
  $("leadWork").setAttribute("aria-busy", "true");
  $("recentWorks").setAttribute("aria-busy", "true");
  try {
    const [works, candidates, decisions, creators] = await Promise.all([
      getData("works.json"), getData("candidates.json"), getData("admin-decisions.json"),
      getData("creators.json").catch(() => null)
    ]);
    names = creators?.version === 1 && creators.creators && typeof creators.creators === "object" ? creators.creators : {};
    render(merge(works, candidates, decisions));
  } catch (error) {
    console.error("注目記事の読み込みに失敗しました", error);
    $("loadError").hidden = false;
    $("leadWork").replaceChildren(element("p", "lead-status", "作品を読み込めませんでした。本棚の再読み込みボタンをお試しください。"));
    $("recentWorks").replaceChildren();
  } finally {
    $("leadWork").setAttribute("aria-busy", "false");
    $("recentWorks").setAttribute("aria-busy", "false");
    $("retryWorks").disabled = false;
    loading = false;
  }
}
async function loadWeeklyTopic() {
  try {
    const item = await getData("weekly-topic.json");
    if (typeof item.topic !== "string" || !item.topic.trim() || item.topic.length > 80 || typeof item.url !== "string") throw Error("Invalid weekly topic");
    const url = new URL(item.url);
    if (url.protocol !== "https:" || url.hostname !== "note.com" || !/^\/komaki_kousuke\/n\/n[A-Za-z0-9]+\/?$/.test(url.pathname)) throw Error("Invalid topic URL");
    $("weeklyTopicWord").textContent = "「" + item.topic + "」";
    $("weeklyTopicLink").href = url.href;
    $("weeklyTopicLink").textContent = "お題の記事を読む";
  } catch (error) {
    console.info("今週のお題を取得できませんでした", error);
    $("weeklyTopicWord").textContent = "今週のお題はnoteでご確認ください。";
  }
}
$("retryWorks").addEventListener("click", loadWorks);
loadWorks();
loadWeeklyTopic();
