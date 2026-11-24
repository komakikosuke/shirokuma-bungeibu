(function () {
  "use strict";
  const TAG = "都道府県クリエイター図鑑";
  const PAGE_SIZE = 3;
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
    const codes = prefectures.filter(p => article.tags.includes(p.name)).map(p => p.code);
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
    if (!data || data.version !== 1 || data.purpose === "prefecture-atlas-preview" || data.tag !== TAG || !Array.isArray(data.articles)) throw Error("掲載データの形式が違います");
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
  function filterArticles(articles, state) {
    return articles.filter(article => {
      if (state.prefecture && !article.prefectures.includes(state.prefecture)) return false;
      return true;
    }).sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt) || a.key.localeCompare(b.key));
  }
  const model = Object.freeze({TAG, normalizeArticle, parseDocument, parseDebugDocument, summarize, colorLevel, filterArticles});
  if (typeof module !== "undefined" && module.exports) module.exports = model;
  if (typeof document === "undefined") return;

  const $ = id => document.getElementById(id);
  const number = new Intl.NumberFormat("ja-JP");
  const dateLabel = new Intl.DateTimeFormat("ja-JP", {timeZone: "Asia/Tokyo", month: "long", day: "numeric"});
  const updateLabel = new Intl.DateTimeFormat("ja-JP", {timeZone: "Asia/Tokyo", month: "numeric", day: "numeric", hour: "numeric", minute: "2-digit"});
  let prefectures = [], articles = [], stats, registry, mapGroups = new Map(), callouts, tooltip;
  let loaded = false;
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
  function selectPrefecture(code, scroll = false) {
    if (!loaded || (code && !prefectures.some(p => p.code === code))) return;
    state.prefecture = code; state.limit = PAGE_SIZE;
    writeHash(); renderMapCounts(); renderPrefectureList(); renderResults();
    if (scroll && matchMedia("(max-width: 960px)").matches) {
      $("resultsPanel").scrollIntoView({behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start"});
      $("resultsTitle").focus({preventScroll: true});
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
    for (const pref of prefectures) {
      const count = stats.counts.get(pref.code);
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
    const positions = {"01": [668, 80], "13": [608, 394], "40": [24, 506], "47": [24, 434]};
    for (const [code, position] of Object.entries(positions)) {
      const pref = prefectures.find(p => p.code === code), count = stats.counts.get(code).articles.size;
      if (!pref || !count || state.prefecture === code) continue;
      const [x, y] = position;
      const group = svg("g", {class: "map-callout"});
      group.append(svg("line", {x1: x + 47, y1: y + 16, x2: pref.point[0], y2: pref.point[1]}), svg("rect", {x, y, width: 98, height: 32, rx: 16}), svg("text", {x: x + 11, y: y + 21}, pref.name), svg("text", {x: x + 86, y: y + 21, "text-anchor": "end", class: "callout-count"}, number.format(count)));
      group.addEventListener("click", () => selectPrefecture(code, true));
      callouts.append(group);
    }
    const pref = currentPrefecture();
    if (pref) {
      const x = Math.max(10, Math.min(716, pref.point[0] - 78));
      const y = Math.max(15, pref.point[1] - 64);
      tooltip.append(svg("rect", {x, y, width: 128, height: 40, rx: 8}), svg("text", {x: x + 13, y: y + 26, class: "tooltip-name"}, pref.name));
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
    node.append(element("strong", "", pref ? pref.name + "の最初の記事を、あなたから。" : "最初のひと記事を、待っています。"), element("p", "", "ふるさとの話も、旅先の記憶も。タグをつけて、地図に色を添えてください。"));
    const link = element("a", "", "参加方法を見る"); link.href = "#participate"; node.append(link);
    return node;
  }
  function renderResults() {
    if (!loaded) return;
    const pref = currentPrefecture(), list = filterArticles(articles, state);
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
      const debugFeed = debugMeta?.content;
      const debugEnabled = new URLSearchParams(location.search).get("debug") === "komaki" && Boolean(debugFeed);
      const feedUrl = debugEnabled ? debugFeed : location.hostname === "komakikosuke.github.io"
        ? "https://raw.githubusercontent.com/komakikosuke/shirokuma-bungeibu/main/data/prefecture-atlas.json"
        : "../data/prefecture-atlas.json";
      const feed = getJson(feedUrl).catch(error => {
        if (debugEnabled && debugMeta.dataset.fallback) return getJson(debugMeta.dataset.fallback);
        throw error;
      });
      const [map, data] = await Promise.all([getJson("./map.json"), feed]);
      if (map.version !== 1 || !Array.isArray(map.prefectures) || map.prefectures.length !== 47 ||
          new Set(map.prefectures.map(p => p.code)).size !== 47 ||
          !map.prefectures.every(p => /^(0[1-9]|[1-3]\d|4[0-7])$/.test(p.code) && typeof p.name === "string" && /^[MLZ\d,.\s-]+$/.test(p.path) && Array.isArray(p.point) && p.point.length === 2 && p.point.every(Number.isFinite))) throw Error("地図データの形式が違います");
      registry = map; prefectures = map.prefectures;
      articles = debugEnabled ? parseDebugDocument(data) : parseDocument(data, prefectures);
      stats = summarize(articles, prefectures);
      loaded = true; readHash();
      if (debugEnabled && !state.prefecture) state.prefecture = "13";
      $("debugNotice").hidden = !debugEnabled;
      $("sampleNotice").hidden = data.sample !== true;
      $("articleTotal").textContent = number.format(stats.articles);
      $("creatorTotal").textContent = number.format(stats.creators);
      $("prefectureTotal").textContent = number.format(stats.prefectures);
      $("updatedAt").textContent = data.sample === true ? "画面確認用サンプル" : data.generatedAt && Number.isFinite(Date.parse(data.generatedAt)) ? (debugEnabled ? "デバッグ記事の取得 " : "最終更新 ") + updateLabel.format(new Date(data.generatedAt)) + "（日本時間）" : "これから記事が集まります";
      buildMap(); renderMapCounts(); renderPrefectureList(); renderView(); renderResults();
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
  $("mapTab").addEventListener("click", () => { state.view = "map"; writeHash(); renderView(); });
  $("listTab").addEventListener("click", () => { state.view = "list"; writeHash(); renderView(); });
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
    if (!loaded || location.hash === "#participate" || location.hash === "#explore") return;
    readHash(); state.limit = PAGE_SIZE;
    renderMapCounts(); renderPrefectureList(); renderView(); renderResults();
  });
  load();
})();
