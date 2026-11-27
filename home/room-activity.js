(() => {
  "use strict";
  const badges = Array.from(document.querySelectorAll("[data-room-activity]"));
  if (!badges.length) return;
  let pending = false;
  function show(count) {
    const label = count > 0 ? `${count.toLocaleString("ja-JP")}人が活動中` : "";
    for (const badge of badges) {
      if (badge.textContent !== label) badge.textContent = label;
      badge.hidden = !label;
      const link = badge.closest("a[data-room-label]");
      if (link) link.setAttribute("aria-label", link.dataset.roomLabel + (label ? `（${label}）` : ""));
    }
  }
  async function update() {
    if (document.hidden || pending) return;
    pending = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch("https://shirokuma-writing-room.komakikosuke.chatgpt.site/api/room/activity", {
        credentials: "omit", mode: "cors", cache: "no-store", signal: controller.signal,
      });
      if (!response.ok) throw new Error("Activity unavailable");
      const data = await response.json();
      if (!Number.isSafeInteger(data.count) || data.count < 0) throw new Error("Invalid activity count");
      show(data.count);
    } catch { show(0); }
    finally { clearTimeout(timeout); pending = false; }
  }
  void update();
  setInterval(update, 30000);
  window.addEventListener("pageshow", update);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) void update(); });
})();
