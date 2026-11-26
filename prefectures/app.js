(function () {
  "use strict";
  const TAG = "記事で塗る日本地図";
  const PAGE_SIZE = 3;
  const MOBILE_SELECTION_DELAY = 450;
  const SVG_NS = "http://www.w3.org/2000/svg";
  const normalize = value => String(value || "").normalize("NFKC").trim();
  const tagName = value => normalize(value).replace(/^[#＃]/, "");
  const imageUrl = value => {
    try {
      const url = new URL(value);
      return url.protocol === "https:" && !url.username && !url.password &&
        /(^|\.)(st-note\.com|note\.com|note\.mu|amazonaws\.com)$/.test(url.hostname) ? url.href : "";
    } catch (_) { return ""; }
  };
  function normalizePublicMetadata(raw) {
    if (!raw || typeof raw !== "object" || !/^n[A-Za-z0-9]+$/.test(raw.key)) return null;
    const author = raw.author;
    if (!author || !/^[A-Za-z0-9_-]{1,100}$/.test(author.handle) || typeof author.name !== "string" || !author.name.trim()) return null;
    const url = "https://note.com/" + author.handle + "/n/" + raw.key;
    if (raw.url !== url || typeof raw.title !== "string" || !raw.title.trim() || !Number.isFinite(Date.parse(raw.publishedAt))) return null;
    const tags = [...new Set((Array.isArray(raw.tags) ? raw.tags : []).filter(t => typeof t === "string").map(tagName))];
    return {
      key: raw.key, url, title: raw.title.slice(0, 500), publishedAt: raw.publishedAt,
      author: {handle: author.handle, name: author.name.slice(0, 150), avatarUrl: imageUrl(author.avatarUrl)},
      imageUrl: imageUrl(raw.imageUrl), tags, isPaid: raw.isPaid === true
    };
  }
  function normalizeArticle(raw, prefectures) {
    const article = normalizePublicMetadata(raw);
    if (!article) return null;
    const codes = prefectures.filter(p => article.tags.includes(p.name) || article.tags.includes(p.name.replace(/[都府県]$/, ""))).map(p => p.code);
    if (!article.tags.includes(TAG) || !codes.length) return null;
    return {...article, prefectures: codes};
  }
  function parseDebugDocument(data) {
    if (!data || data.version !== 1 || data.purpose !== "prefecture-atlas-preview" ||
        data.creator !== "komaki_kousuke" || !Array.isArray(data.articles) || !data.articles.length) throw Error("デバッグ記事の形式が違います");
    const unique = new Map();
    for (const raw of data.articles) {
      const article = normalizePublicMetadata(raw);
      if (!article || article.author.handle !== "komaki_kousuke") throw Error("デバッグ記事の投稿者を確認できません");
      unique.set(article.key, {...article, prefectures: ["13"], debug: true});
    }
    return [...unique.values()].sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt) || a.key.localeCompare(b.key)).slice(0, 3);
  }
  function parseDocument(data, prefectures) {
    if (!data || data.version !== 1 || (data.purpose === "prefecture-atlas-preview" || data.purpose === "prefecture-atlas-history-demo") || data.tag !== TAG || !Array.isArray(data.articles)) throw Error("掲載データの形式が違います");
    const unique = new Map();
    for (const raw of data.articles) {
      const article = normalizeArticle(raw, prefectures);
      if (article) unique.set(article.key, article);
    }
    if (data.articles.length && !unique.size) throw Error("掲載データを確認できません");
    return [...unique.values()];
  }
  function summarize(articles, prefectures) {
    const unique = new Map(articles.map(a => [a.key, a]));
    const counts = new Map(prefectures.map(p => [p.code, {articles: new Set(), creators: new Set()}]));
    const creators = new Set();
    for (const article of unique.values()) {
      creators.add(article.author.handle);
      for (const code of article.prefectures) {
        const count = counts.get(code);
        if (count) { count.articles.add(article.key); count.creators.add(article.author.handle); }
      }
    }
    return {articles: unique.size, creators: creators.size, prefectures: [...counts.values()].filter(c => c.articles.size).length, counts};
  }
  const colorLevel = count => count === 0 ? 0 : count < 5 ? 1 : count < 10 ? 2 : count < 20 ? 3 : 4;
  function topPrefectures(prefectures, stats) {
    return prefectures.map(prefecture => ({prefecture, count: stats.counts.get(prefecture.code).articles.size}))
      .filter(item => item.count > 0)
      .sort((a, b) => b.count - a.count || a.prefecture.code.localeCompare(b.prefecture.code))
      .slice(0, 3);
  }
  function filterArticles(articles, state) {
    return articles.filter(article => {
      if (state.prefecture && !article.prefectures.includes(state.prefecture)) return false;
      return true;
    }).sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt) || a.key.localeCompare(b.key));
  }
  function buildHistoryDemo(prefectures) {
    // Synthetic map counts only: no fabricated article URLs or real feed writes.
    const start = Date.UTC(2026, 10, 30, 15), history = [];
    const ordered = [...prefectures].sort((a, b) => a.code.localeCompare(b.code));
    for (let step = 0; step <= 32; step++) {
      const counts = Object.fromEntries(ordered.map((pref, index) => {
        const first = 1 + Math.floor(index * 23 / ordered.length);
        const age = Math.max(0, step - first + 1);
        return [pref.code, age ? 1 + Math.floor(age * (1 + index % 5) / 3) : 0];
      }));
      history.push({at: new Date(start + step * 3 * 3600000).toISOString(), counts});
    }
    return {version: 1, tag: TAG, purpose: "prefecture-atlas-history-demo", generatedAt: history.at(-1).at, articles: [], history};
  }
  function parseHistory(data, prefectures) {
    if (!Array.isArray(data.history) || !Number.isFinite(Date.parse(data.generatedAt))) return [];
    const codes = prefectures.map(p => p.code), frames = [];
    let previous = -Infinity;
    for (const frame of data.history) {
      const time = Date.parse(frame?.at);
      if (!Number.isFinite(time) || time <= previous || time > Date.parse(data.generatedAt) ||
          !frame.counts || Object.keys(frame.counts).length !== codes.length ||
          !codes.every(code => Number.isSafeInteger(frame.counts[code]) && frame.counts[code] >= 0)) return [];
      frames.push({at: frame.at, counts: {...frame.counts}}); previous = time;
    }
    return frames;
  }
  const model = Object.freeze({TAG, normalizeArticle, parseDocument, parseDebugDocument, summarize, colorLevel, filterArticles, topPrefectures, parseHistory, buildHistoryDemo});
  if (typeof module !== "undefined" && module.exports) module.exports = model;
  if (typeof document === "undefined") return;

  const $ = id => document.getElementById(id);
  const number = new Intl.NumberFormat("ja-JP");
  const dateLabel = new Intl.DateTimeFormat("ja-JP", {timeZone: "Asia/Tokyo", month: "long", day: "numeric"});
  const updateLabel = new Intl.DateTimeFormat("ja-JP", {timeZone: "Asia/Tokyo", month: "numeric", day: "numeric", hour: "numeric", minute: "2-digit"});
  let prefectures = [], articles = [], stats, registry, mapGroups = new Map(), callouts, tooltip;
  let loaded = false;
  let resultsScrollTimer;
  let historyDemo = false;
  let historyFrames = [], historyFrame = null, historyAnimation = 0;
  const state = {prefecture: "", view: "map", limit: PAGE_SIZE};
  function element(name, className, text) {
    const node = document.createElement(name);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function svg(name, attrs = {}, text) {
    const node = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function externalLink(text, url, className) {
    const node = element("a", className, text);
    node.href = url; node.target = "_blank"; node.rel = "noopener noreferrer";
    return node;
  }
  const currentPrefecture = () => prefectures.find(p => p.code === state.prefecture);
  function readHash() {
    const params = new URLSearchParams(location.hash.slice(1));
    state.prefecture = prefectures.some(p => p.code === params.get("pref")) ? params.get("pref") : "";
    state.view = params.get("view") === "list" ? "list" : "map";
  }
  function writeHash() {
    const params = new URLSearchParams();
    if (state.prefecture) params.set("pref", state.prefecture);
    if (state.view === "list") params.set("view", "list");
    const hash = params.toString();
    history.replaceState(null, "", location.pathname + location.search + (hash ? "#" + hash : ""));
  }
  function setTabs(first, second, active) {
    [first, second].forEach((id, index) => {
      $(id).setAttribute("aria-selected", String(index === active));
      $(id).tabIndex = index === active ? 0 : -1;
    });
  }
  function cancelResultsScroll() {
    clearTimeout(resultsScrollTimer);
    resultsScrollTimer = undefined;
  }
  function selectPrefecture(code, scroll = false) {
    if (!loaded || (code && !prefectures.some(p => p.code === code))) return;
    cancelResultsScroll();
    closeHistory();
    state.prefecture = code; state.limit = PAGE_SIZE;
    writeHash(); renderMapCounts(); renderPrefectureList(); renderResults();
    if (scroll && matchMedia("(max-width: 960px)").matches) {
      resultsScrollTimer = setTimeout(() => {
        resultsScrollTimer = undefined;
        if (state.prefecture !== code || !matchMedia("(max-width: 960px)").matches) return;
        $("resultsPanel").scrollIntoView({behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start"});
        $("resultsTitle").focus({preventScroll: true});
      }, MOBILE_SELECTION_DELAY);
    }
  }
  function buildMap() {
    const root = svg("svg", {viewBox: registry.viewBox, role: "group", "aria-label": "都道府県ごとの記事数を示す日本地図"});
    const regions = svg("g");
    mapGroups = new Map();
    for (const pref of prefectures) {
      const group = svg("g", {class: "prefecture", role: "button", tabindex: "0", "data-prefecture": pref.code});
      group.append(svg("title"), svg("path", {d: pref.path}));
      group.addEventListener("click", () => selectPrefecture(pref.code, true));
      group.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectPrefecture(pref.code, true); }
      });
      regions.append(group); mapGroups.set(pref.code, group);
    }
    root.append(regions, svg("path", {d: "M94 363H212L232 383V445H94Z", class: "map-inset", "aria-hidden": "true"}), svg("text", {x: 98, y: 354, class: "map-inset-label", "aria-hidden": "true"}, "沖縄"));
    callouts = svg("g", {"aria-hidden": "true"});
    tooltip = svg("g", {class: "selection-tooltip", "aria-hidden": "true"});
    root.append(callouts, tooltip);
    $("japanMap").replaceChildren(root);
    $("japanMap").setAttribute("aria-busy", "false");
  }
  function renderMapCounts() {
    const displayed = historyFrame ? {counts: new Map(prefectures.map(p => [p.code, {articles: {size: historyFrame.counts[p.code]}}]))} : stats;
    for (const pref of prefectures) {
      const count = displayed.counts.get(pref.code);
      const group = mapGroups.get(pref.code);
      group.setAttribute("aria-pressed", String(state.prefecture === pref.code));
      const label = pref.name + "の記事を読む";
      group.setAttribute("aria-label", label);
      group.querySelector("title").textContent = label;
      group.querySelector("path").setAttribute("class", "level-" + colorLevel(count.articles.size));
    }
    const selected = mapGroups.get(state.prefecture);
    if (selected) selected.parentNode.append(selected);
    callouts.replaceChildren(); tooltip.replaceChildren();
    const leaders = topPrefectures(prefectures, displayed);
    const pref = currentPrefecture();
    const [mapX, mapY, mapWidth, mapHeight] = registry.viewBox.split(/\s+/).map(Number);
    const selectionWidth = pref ? pref.name.length * 18 + 24 : 0;
    const selectionBox = pref && !leaders.some(item => item.prefecture.code === pref.code) ? {
      x: Math.max(mapX + 10, Math.min(mapX + mapWidth - selectionWidth - 10, pref.point[0] - selectionWidth / 2)),
      y: Math.max(mapY + 15, pref.point[1] - 64), width: selectionWidth, height: 40
    } : null;
    const occupied = selectionBox ? [selectionBox] : [];
    for (const {prefecture: leader, count} of [...leaders].sort((a, b) => a.prefecture.point[1] - b.prefecture.point[1])) {
      const countText = number.format(count), width = Math.max(112, leader.name.length * 13 + countText.length * 8 + 30), height = 32;
      const right = leader.point[0] >= mapX + mapWidth / 2;
      // Place western labels in the sea below the Okinawa inset so they do not cover neighboring prefectures.
      const x = Math.max(mapX + 10, Math.min(mapX + mapWidth - width - 10, right ? leader.point[0] + 70 : mapX + 16));
      const minY = right ? mapY + 15 : mapY + 450;
      const candidates = [0, 44, -44, 88, -88, 132, -132].map(offset =>
        Math.max(minY, Math.min(mapY + mapHeight - height - 15, leader.point[1] - height / 2 + offset)));
      const y = candidates.find(candidate => occupied.every(box =>
        x + width + 8 <= box.x || x >= box.x + box.width + 8 || candidate + height + 8 <= box.y || candidate >= box.y + box.height + 8)) ?? candidates[0];
      occupied.push({x, y, width, height});
      const group = svg("g", {class: "map-callout" + (state.prefecture === leader.code ? " is-selected" : ""), "data-prefecture": leader.code});
      group.append(svg("line", {x1: right ? x : x + width, y1: y + height / 2, x2: leader.point[0], y2: leader.point[1]}), svg("rect", {x, y, width, height, rx: 16}), svg("text", {x: x + 12, y: y + 21}, leader.name), svg("text", {x: x + width - 12, y: y + 21, "text-anchor": "end", class: "callout-count"}, countText));
      group.addEventListener("click", () => selectPrefecture(leader.code, true));
      callouts.append(group);
    }
    if (selectionBox) {
      const {x, y, width, height} = selectionBox;
      tooltip.append(svg("rect", {x, y, width, height, rx: 8}), svg("text", {x: x + width / 2, y: y + 26, "text-anchor": "middle", class: "tooltip-name"}, pref.name));
    }
  }
  function renderPrefectureList() {
    $("listView").replaceChildren();
    for (const region of [...new Set(prefectures.map(p => p.region))]) {
      const group = element("section", "region-group");
      group.append(element("h3", "", region));
      const buttons = element("div", "region-buttons");
      for (const pref of prefectures.filter(p => p.region === region)) {
        const count = stats.counts.get(pref.code).articles.size;
        const button = element("button", "prefecture-button");
        button.type = "button";
        button.setAttribute("aria-pressed", String(pref.code === state.prefecture));
        button.setAttribute("aria-label", pref.name + "、" + count + "記事");
        button.append(element("span", "", pref.name), element("span", "count", number.format(count)));
        button.addEventListener("click", () => selectPrefecture(pref.code, true));
        buttons.append(button);
      }
      group.append(buttons); $("listView").append(group);
    }
  }
  function renderView() {
    setTabs("mapTab", "listTab", state.view === "map" ? 0 : 1);
    $("mapView").hidden = state.view !== "map";
    $("listView").hidden = state.view !== "list";
  }
  function avatar(author) {
    const node = element("span", "avatar", [...author.name][0] || "文");
    node.setAttribute("aria-hidden", "true");
    if (author.avatarUrl) {
      const img = element("img"); img.src = author.avatarUrl; img.alt = ""; img.loading = "lazy"; img.referrerPolicy = "no-referrer";
      img.addEventListener("error", () => node.replaceChildren(document.createTextNode([...author.name][0] || "文")), {once: true});
      node.replaceChildren(img);
    }
    return node;
  }
  function authorLink(author) {
    const link = externalLink("", "https://note.com/" + author.handle, "article-author");
    link.append(avatar(author), element("span", "article-author-name", author.name));
    return link;
  }
  function articleCard(article) {
    const card = element("article", "article-card");
    card.append(authorLink(article.author));
    const body = externalLink("", article.url, "article-body");
    body.append(element("h3", "", article.title));
    const thumb = element("span", "article-thumbnail");
    thumb.setAttribute("aria-hidden", "true");
    if (article.imageUrl) {
      const img = element("img"); img.src = article.imageUrl; img.alt = ""; img.loading = "lazy"; img.referrerPolicy = "no-referrer";
      img.addEventListener("error", () => img.remove(), {once: true});
      thumb.append(img);
    }
    body.append(thumb); card.append(body);
    const meta = element("div", "article-meta");
    const date = element("time", "", dateLabel.format(new Date(article.publishedAt))); date.dateTime = article.publishedAt; meta.append(date);
    if (article.isPaid) meta.append(element("span", "paid-label", "有料"));
    meta.append(externalLink("noteで読む", article.url, "article-read")); card.append(meta);
    return card;
  }
  function emptyMessage() {
    const node = element("div", "empty-message");
    const pref = currentPrefecture();
    const description = element("p", "", "ふるさとの話も、旅先の記憶も。");
    description.append(document.createElement("br"), document.createTextNode("あなたの記事で、日本地図に色がつきます。"));
    node.append(element("strong", "", pref ? pref.name + "の最初の記事を書こう。" : "最初のひと記事を、待っています。"), description);
    const link = element("a", "", "参加方法を見る"); link.href = "#participate"; node.append(link);
    return node;
  }
  function renderResults() {
    if (!loaded) return;
    const pref = currentPrefecture(), list = filterArticles(articles, state);
    if (historyDemo) {
      $("resultsEnglish").textContent = "HISTORY DEMO";
      $("resultsTitle").textContent = pref?.name || "変化のデバッグ";
      $("clearPrefecture").hidden = !pref;
      const message = element("div", "empty-message");
      message.append(element("strong", "", "仮データで確認中"), element("p", "", "地図の色と記事数は動作確認用です。実際の掲載記事・履歴には影響しません。"));
      $("resultsList").replaceChildren(message);
      $("loadMore").hidden = true;
      $("resultAnnouncement").textContent = "仮の記事数で地図の変化を表示しています。";
      return;
    }
    $("resultsEnglish").textContent = pref?.englishName || "ALL JAPAN";
    $("resultsTitle").textContent = pref?.name || "全国の新着記事";
    $("clearPrefecture").hidden = !pref;
    $("resultsList").replaceChildren();
    if (!list.length) $("resultsList").append(emptyMessage());
    else for (const article of list.slice(0, state.limit)) $("resultsList").append(articleCard(article));
    $("loadMore").hidden = state.limit >= list.length;
    $("loadMore").textContent = "さらに" + Math.min(6, list.length - state.limit) + "記事を見る";
    $("resultAnnouncement").textContent = (pref?.name || "全国") + "の記事を表示しました。";
  }
  function pauseHistory() {
    cancelAnimationFrame(historyAnimation); historyAnimation = 0;
  }
  function showHistoryFrame(index) {
    const frame = historyFrames[index];
    if (!frame) return;
    historyFrame = frame;
    $("historyRange").value = String(index);
    $("historyDate").dateTime = frame.at;
    $("historyDate").textContent = updateLabel.format(new Date(frame.at)) + "（日本時間）";
    $("historyRange").setAttribute("aria-valuetext", $("historyDate").textContent);
    renderMapCounts();
  }
  function playHistory() {
    if (historyFrames.length < 2) return;
    pauseHistory();
    const last = historyFrames.length - 1;
    showHistoryFrame(0);
    const start = performance.now(), duration = 12000;
    function tick(now) {
      const index = Math.min(last, Math.floor(last * Math.max(0, now - start) / duration));
      if (index !== Number($("historyRange").value)) showHistoryFrame(index);
      if (index < last) historyAnimation = requestAnimationFrame(tick);
      else pauseHistory();
    }
    historyAnimation = requestAnimationFrame(tick);
  }
  function closeHistory() {
    pauseHistory(); historyFrame = null;
    $("historyPanel").hidden = true;
    $("historyToggle").setAttribute("aria-expanded", "false");
    if (loaded) renderMapCounts();
  }
  function configureHistory(data, debugEnabled) {
    closeHistory();
    historyFrames = debugEnabled || data.sample ? [] : parseHistory(data, prefectures);
    $("historyToggle").hidden = debugEnabled || data.sample === true;
    $("historyDemoLink").hidden = historyDemo || !document.querySelector('meta[name="atlas-debug-feed"]');
    const available = historyFrames.length >= 2;
    $("historyControls").hidden = !available;
    $("historyEmpty").hidden = available;
    $("historyRange").max = String(Math.max(0, historyFrames.length - 1));
    $("historyRange").value = "0";
  }
  async function getJson(url) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(url, {cache: "no-store", signal: controller.signal});
      if (!response.ok) throw Error("読み込みに失敗しました: " + response.status);
      return await response.json();
    } finally { clearTimeout(timer); }
  }
  async function load() {
    $("retryButton").disabled = true;
    $("loadError").hidden = true;
    $("resultsPanel").setAttribute("aria-busy", "true");
    try {
      // Data commits made by GitHub Actions need not rebuild the Pages HTML.
      // Read the current feed directly on the public origin, as the home counter does.
      const debugMeta = document.querySelector('meta[name="atlas-debug-feed"]');
      const normalMeta = document.querySelector('meta[name="atlas-feed"]');
      const debugFeed = debugMeta?.content;
      const debugMode = new URLSearchParams(location.search).get("debug");
      const debugEnabled = debugMode === "komaki" && Boolean(debugFeed);
      historyDemo = debugMode === "history" && Boolean(debugFeed);
      const feedUrl = debugEnabled ? debugFeed : normalMeta?.content || (location.hostname === "komakikosuke.github.io"
        ? "https://raw.githubusercontent.com/komakikosuke/shirokuma-bungeibu/main/data/prefecture-atlas.json"
        : "../data/prefecture-atlas.json");
      const feedMeta = debugEnabled ? debugMeta : normalMeta;
      const feed = historyDemo ? Promise.resolve(null) : getJson(feedUrl).catch(error => {
        if (feedMeta?.dataset.fallback) return getJson(feedMeta.dataset.fallback);
        throw error;
      });
      const [map, feedData] = await Promise.all([getJson("./map.json"), feed]);
      if (map.version !== 1 || !Array.isArray(map.prefectures) || map.prefectures.length !== 47 ||
          new Set(map.prefectures.map(p => p.code)).size !== 47 ||
          !map.prefectures.every(p => /^(0[1-9]|[1-3]\d|4[0-7])$/.test(p.code) && typeof p.name === "string" && /^[MLZ\d,.\s-]+$/.test(p.path) && Array.isArray(p.point) && p.point.length === 2 && p.point.every(Number.isFinite))) throw Error("地図データの形式が違います");
      registry = map; prefectures = map.prefectures;
      const data = historyDemo ? buildHistoryDemo(prefectures) : feedData;
      articles = historyDemo ? [] : debugEnabled ? parseDebugDocument(data) : parseDocument(data, prefectures);
      stats = summarize(articles, prefectures);
      if (historyDemo) {
        const counts = data.history.at(-1).counts;
        stats = {articles: Object.values(counts).reduce((sum, count) => sum + count, 0), creators: 0,
          prefectures: Object.values(counts).filter(count => count > 0).length,
          counts: new Map(prefectures.map(pref => [pref.code, {articles: {size: counts[pref.code]}, creators: new Set()}]))};
      }
      loaded = true; readHash();
      if (debugEnabled && !state.prefecture) state.prefecture = "13";
      $("debugNotice").hidden = !debugEnabled && !historyDemo;
      $("debugNotice").querySelector("span").textContent = historyDemo ? "デバッグ表示：動作確認用の仮データです。" : "デバッグ表示：小牧幸助の最新記事を東京に仮表示しています。";
      $("debugNotice").querySelector("a").href = historyDemo ? "./" : "./#pref=13";
      $("articleTotal").textContent = number.format(stats.articles);
      $("creatorTotal").textContent = historyDemo ? "—" : number.format(stats.creators);
      $("prefectureTotal").textContent = number.format(stats.prefectures);
      $("updatedAt").hidden = data.sample === true || historyDemo;
      $("updatedAt").textContent = data.sample === true ? "" : data.generatedAt && Number.isFinite(Date.parse(data.generatedAt)) ? (debugEnabled ? "デバッグ記事の取得 " : "最終更新 ") + updateLabel.format(new Date(data.generatedAt)) + "（日本時間）" : "これから記事が集まります";
      buildMap(); configureHistory(data, debugEnabled); renderMapCounts(); renderPrefectureList(); renderView(); renderResults();
      if (historyDemo) {
        $("historyToggle").click();
        $("historyPanel").scrollIntoView({behavior: "instant", block: "start"});
      }
    } catch (error) {
      console.error("図鑑の読み込みに失敗しました", error);
      $("loadError").hidden = false;
      if (!loaded) {
        $("japanMap").replaceChildren(element("p", "map-loading", "地図と記事を読み込めませんでした。"));
        $("japanMap").setAttribute("aria-busy", "false");
        $("resultsList").replaceChildren(element("p", "empty-message", "「もう一度読み込む」からお試しください。"));
        $("updatedAt").textContent = "掲載データを確認できません";
      }
    } finally {
      $("retryButton").disabled = false;
      $("resultsPanel").setAttribute("aria-busy", "false");
    }
  }
  function bindTabKeys(ids) {
    for (const id of ids) $(id).addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const index = event.key === "Home" ? 0 : event.key === "End" ? ids.length - 1 : (ids.indexOf(id) + (event.key === "ArrowLeft" ? -1 : 1) + ids.length) % ids.length;
      $(ids[index]).click(); $(ids[index]).focus();
    });
  }
  $("historyToggle").addEventListener("click", () => {
    if (!$("historyPanel").hidden) { closeHistory(); return; }
    cancelResultsScroll();
    state.view = "map"; writeHash(); renderView();
    $("historyPanel").hidden = false;
    $("historyToggle").setAttribute("aria-expanded", "true");
    if (historyFrames.length >= 2) {
      showHistoryFrame(0);
      if (!matchMedia("(prefers-reduced-motion: reduce)").matches) playHistory();
    }
  });
  $("historyDemoLink").addEventListener("click", () => {
    const url = new URL(location.href);
    url.searchParams.set("debug", "history"); url.hash = "";
    history.replaceState(null, "", url); load();
  });
  $("historyRange").addEventListener("input", () => { pauseHistory(); showHistoryFrame(Number($("historyRange").value)); });
  ["pointerdown", "touchstart", "keydown"].forEach(type => $("historyRange").addEventListener(type, pauseHistory, {passive: true}));
  document.addEventListener("visibilitychange", () => { if (document.hidden) pauseHistory(); });
  $("mapTab").addEventListener("click", () => { cancelResultsScroll(); state.view = "map"; writeHash(); renderView(); });
  $("listTab").addEventListener("click", () => { cancelResultsScroll(); closeHistory(); state.view = "list"; writeHash(); renderView(); });
  bindTabKeys(["mapTab", "listTab"]);
  $("clearPrefecture").addEventListener("click", () => selectPrefecture(""));
  $("loadMore").addEventListener("click", () => { state.limit += 6; renderResults(); });
  $("retryButton").addEventListener("click", load);
  document.querySelectorAll("[data-copy]").forEach(button => button.addEventListener("click", async () => {
    const text = "#" + button.dataset.copy;
    try {
      if (!navigator.clipboard?.writeText) throw Error("Clipboard unavailable");
      await navigator.clipboard.writeText(text);
      $("copyStatus").textContent = text + " をコピーしました。";
    } catch (_) {
      const range = document.createRange(); range.selectNodeContents(button.firstElementChild);
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      $("copyStatus").textContent = "タグを選択しました。コピーしてお使いください。";
    }
  }));
  window.addEventListener("hashchange", () => {
    cancelResultsScroll(); closeHistory();
    if (!loaded || location.hash === "#participate" || location.hash === "#explore") return;
    readHash(); state.limit = PAGE_SIZE;
    renderMapCounts(); renderPrefectureList(); renderView(); renderResults();
  });
  load();
})();
