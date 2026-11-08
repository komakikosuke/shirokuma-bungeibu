/* シロクマ文芸部 note マガジン連携 — Safariのnote.comコンソール用
 * 実行: scriptを貼る → 表示された「開始」をクリックする
 * 最初の実行は既存掲載作品を基準登録するだけ。次回以降、新規作品を最大5件ずつ追加。
 * noteの非公開API、認証情報、他のマガジンは操作しない。
 */
(async () => {
  "use strict";
  const TARGET = "注目記事｜シロクマ文芸部";
  const FEED = "https://komakikosuke.github.io/shirokuma-bungeibu/data/magazine-eligible.json";
  const STORE = "shirokuma:note-magazine:v1";
  const MAX = 5;
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const text = el => (el?.innerText || el?.textContent || "").trim();
  const canonical = url => {
    try {
      const u = new URL(url);
      const m = u.pathname.match(/^\/[a-zA-Z0-9_-]+\/n\/n[a-zA-Z0-9]+\/?$/);
      if (u.hostname !== "note.com" || !m) return null;
      return u.origin + u.pathname.replace(/\/$/, "");
    } catch { return null; }
  };
  if (location.hostname !== "note.com") {
    console.error("note.comでログインした記事ページのコンソールから実行してください。");
    return;
  }
  let feed;
  try {
    const res = await fetch(FEED + "?t=" + Date.now(), {cache:"no-store"});
    if (!res.ok) throw Error("HTTP " + res.status);
    feed = await res.json();
    if (feed.magazineUrl !== "https://note.com/komaki_kousuke/m/mc02c43cae693" || !Array.isArray(feed.works)) throw Error("対象マガジンのデータ不一致");
  } catch(err) {
    console.error("掲載データを取得できません（追加は行いません）",err); return;
  }
  const works = [...new Map(feed.works.map(w => [canonical(w.url),w]).filter(([u])=>u))].map(([url,w])=>({...w,url}));
  const state = (() => {
    try {return JSON.parse(localStorage.getItem(STORE)) || null;}
    catch {return null;}
  })();
  const save = s => localStorage.setItem(STORE,JSON.stringify(s));
  if (!state) {
    // Old content is deliberately NOT backfilled (avoid mass notifications).
    save({version:1,createdAt:new Date().toISOString(),seen:works.map(w=>w.url),added:[],failed:[]});
    console.info("初期設定完了：現在の掲載作品", works.length, "件を登録。今回はnoteへの追加なし。次の新規掲載から対象になります。");
    return;
  }
  const seen = new Set(state.seen || []);
  const added = new Set(state.added || []);
  const pending = works.filter(w=>!seen.has(w.url) && !added.has(w.url)).slice(0,MAX);
  if (!pending.length) {console.info("新しい掲載作品はありません。マガジン追加は不要です。");return;}
  console.table(pending.map(w=>({title:w.title,url:w.url})));
  const control = document.createElement("button");
  control.textContent = "シロクマ文芸部：新規" + pending.length + "件をマガジンに追加";
  control.style.cssText="position:fixed;right:18px;bottom:20px;z-index:2147483647;padding:14px 18px;background:#14627c;color:white;border:2px solid white;border-radius:12px;font-weight:bold;cursor:pointer;box-shadow:0 5px 20px #3335";
  document.body.append(control);
  console.info("画面右下のボタンをクリックして開始。1件ごとに実際の『追加済』表示まで確認します。");
  let running = false;
  const findRow = doc => {
    const rows = [...doc.querySelectorAll("button")].filter(b=>/^(追加|追加済)$/.test(text(b)));
    const matches=[];
    for (const button of rows) {
      let node=button.parentElement;
      for(let depth=0; node && depth<9; depth++,node=node.parentElement) {
        const lines=text(node).split("\n").map(x=>x.trim()).filter(Boolean);
        if(lines.includes(TARGET) && node.querySelectorAll("button").length===1) {
          matches.push({button,node}); break;
        }
      }
    }
    return matches;
  };
  const waitFor = async (fn,timeout=16000,interval=350) => {
    const start=Date.now();
    while(Date.now()-start<timeout) {
      let value;try{value=fn();}catch{}
      if(value) return value;
      await sleep(interval);
    }
    return null;
  };
  const addOne = async (win,w) => {
    win.location.replace(w.url);
    const loaded=await waitFor(()=>{
      const url=canonical(win.location.href);
      if(url!==w.url || win.document.readyState!=="complete")return null;
      return win.document;
    },26000);
    if(!loaded) throw Error("記事ページの読み込みを確認できませんでした");
    let row = await waitFor(()=>{
      const m=findRow(win.document);return m.length===1 ? m[0] : null;
    },1400);
    if (!row) {
      const openers=[...win.document.querySelectorAll("button,[role=button]")].filter(b=>{
        const name=[text(b),b.getAttribute("aria-label"),b.getAttribute("title")].join(" ");
        return /記事を保存|マガジンに追加|マガジン追加/.test(name);
      });
      if(openers.length!==1)throw Error("『記事を保存』が一意に見つかりません: "+openers.length);
      openers[0].scrollIntoView({block:"center"});
      openers[0].click();
      row=await waitFor(()=>{
        const matches=findRow(win.document);
        if(matches.length>1)throw Error("マガジン欄が重複しています");
        return matches.length===1?matches[0]:null;
      });
    }
    if(!row)throw Error("対象マガジンの行が見つかりません");
    if(text(row.button)==="追加済")return "already";
    if(text(row.button)!=="追加")throw Error("予期しないボタン表示");
    row.button.click();
    const confirmed=await waitFor(()=>{
      const matches=findRow(win.document);
      return matches.length===1 && text(matches[0].button)==="追加済";
    },13000);
    if(!confirmed)throw Error("追加後に『追加済』を確認できません");
    return "added";
  };
  control.addEventListener("click", async()=>{
    if(running)return;running=true;
    control.disabled=true;control.textContent="処理中…";
    const win=window.open("about:blank","shirokuma-magazine-sync-worker","width=960,height=800");
    if(!win){console.error("別ウィンドウがブロックされました。Safariのポップアップ設定を確認してください。");control.remove();return;}
    const results=[];
    for(const w of pending) {
      try {
        const status=await addOne(win,w);
        seen.add(w.url);if(status==="added"||status==="already")added.add(w.url);
        state.seen=[...seen];state.added=[...added];save(state);
        results.push({title:w.title,status,url:w.url});
        console.info("[マガジン]",status,w.title);
      } catch(err) {
        console.error("安全のためここで停止:",w.url,err);
        results.push({title:w.title,status:"ERROR: "+err.message,url:w.url});
        (state.failed ||= []).push({url:w.url,at:new Date().toISOString(),message:String(err.message)});
        save(state);break;
      }
      await sleep(5000);
    }
    console.table(results);
    control.remove();
    // Keep the worker open when an error occurs, so the operator can inspect it.
    if(results.length && !String(results.at(-1).status).startsWith("ERROR"))try{win.close()}catch{}
  },{once:true});
})();
