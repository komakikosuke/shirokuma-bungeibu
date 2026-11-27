"use strict";
async function loadHashtagCount() {
  const count = document.getElementById("asideCount");
  const updated = document.getElementById("asideUpdated");
  const urls = [
    "https://raw.githubusercontent.com/komakikosuke/shirokuma-bungeibu/main/data/hashtag-total.json",
    "./data/hashtag-total.json"
  ];
  for (const url of urls) {
    try {
      const response = await fetch(url + "?t=" + Math.floor(Date.now() / 300000), { cache: "no-store" });
      if (!response.ok) continue;
      const data = await response.json();
      if (data.tag !== "シロクマ文芸部" || !Number.isSafeInteger(data.count) || data.count < 0) continue;
      count.textContent = new Intl.NumberFormat("ja-JP").format(data.count);
      if (data.updatedAt && !Number.isNaN(Date.parse(data.updatedAt))) {
        const date = new Intl.DateTimeFormat("ja-JP", { timeZone: "Asia/Tokyo", month: "numeric", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(data.updatedAt));
        updated.textContent = "更新 " + date;
        updated.dateTime = new Date(data.updatedAt).toISOString();
        updated.hidden = false;
      }
      return;
    } catch (error) { console.info("累計記事数の取得を再試行します", error); }
  }
  count.setAttribute("aria-label", "累計記事数を取得できませんでした");
}
async function loadEndrollStatus() {
  const entry = document.getElementById("endrollEntry");
  const label = document.getElementById("endrollEntryLabel");
  const status = document.getElementById("endrollEntryStatus");
  try {
    const response = await fetch("./data/twenty-char-status.json?v=" + Date.now(), { cache: "no-store" });
    if (!response.ok) throw Error("HTTP " + response.status);
    const data = await response.json();
    if (data.version !== 1 || typeof data.status !== "string" || !Number.isSafeInteger(data.workCount) || data.workCount < 0) throw Error("Invalid end-roll status");
    if (data.status === "ready" && data.workCount > 0) {
      entry.href = "./twenty-credits/";
      entry.removeAttribute("aria-disabled");
      entry.removeAttribute("tabindex");
      label.textContent = "エンドロールを見る";
      return;
    }
    entry.removeAttribute("href");
    entry.setAttribute("aria-disabled", "true");
    label.textContent = data.status === "empty" ? "対象作品なし" : "準備中";
    status.hidden = false;
    status.textContent = "次回の公開をお待ちください。";
  } catch (error) {
    // Preserve the disabled entrance until a published roll has been confirmed.
    console.info("エンドロールの公開状況を取得できませんでした", error);
  }
}
loadHashtagCount();
loadEndrollStatus();
