"use strict";
const REPOSITORY="komakikosuke/shirokuma-bungeibu";
const API="https://api.github.com/repos/"+REPOSITORY+"/contents/data/admin-decisions.json";
const OWNER="komakikosuke";
const AUTHKEY="shirokuma-admin-session-token";
const $=id=>document.getElementById(id);
const notePattern=/^https:\/\/note\.com\/([a-zA-Z0-9_-]+)\/n\/n([a-zA-Z0-9]+)\/?$/;
let token="";
let candidates=[];
let published=[];
let decisions={};
let creators={};
let selected="all";
let saving=false;

const statusText={approved:"承認済み",draft:"保留",excluded:"除外"};
const safeWork=w=>w&&typeof w==="object"&&/^\d{4}-\d{2}$/.test(w.month)&&
  typeof w.handle==="string"&&/^[a-zA-Z0-9_-]{2,100}$/.test(w.handle)&&
  typeof w.title==="string"&&w.title.trim()&&w.title.length<=300&&
  typeof w.url==="string"&&notePattern.test(w.url)&&
  notePattern.exec(w.url)[1]===w.handle;
const keyOf=w=>w.month+"|"+w.handle;
function notify(t,error=false){
 $("message").textContent=t;$("message").classList.toggle("error",error);
}
function asLink(text,url){
 const a=document.createElement("a");a.textContent=text;a.href=url;a.target="_blank";
 a.rel="noopener noreferrer";a.referrerPolicy="no-referrer";return a;
}
function uniqWorks(){
 const m=new Map();
 for(const w of published)if(safeWork(w))m.set(keyOf(w),w);
 for(const w of candidates)if(safeWork(w))m.set(keyOf(w),w);
 return [...m.values()].sort((a,b)=>String(b.firstCommentAt||"").localeCompare(String(a.firstCommentAt||""))||b.month.localeCompare(a.month));
}
function stateOf(w){
 const manual=decisions[keyOf(w)]?.status;
 if(["draft","approved","excluded"].includes(manual))return manual;
 return published.some(x=>keyOf(x)===keyOf(w))?"approved":"draft";
}
function make(tag,cl="",text=null){
 const e=document.createElement(tag);if(cl)e.className=cl;
 if(text!==null)e.textContent=text;return e;
}
function draw(){
 const all=uniqWorks();
 const count=state=>all.filter(w=>stateOf(w)===state).length;
 $("count-total").textContent=String(all.length);
 $("count-draft").textContent=String(count("draft"));
 $("count-approved").textContent=String(count("approved"));
 $("count-excluded").textContent=String(count("excluded"));
 document.querySelectorAll("[data-filter]").forEach(b=>b.classList.toggle("selected",b.dataset.filter===selected));
 const query=$("search").value.trim().toLowerCase();
 const visible=all.filter(w=>{
   if(selected!=="all"&&stateOf(w)!==selected)return false;
   const display=creators[w.handle]?.name||"";
   return !query||[w.title,w.handle,display,w.month].some(x=>String(x).toLowerCase().includes(query));
 });
 const root=$("items");root.replaceChildren();
 if(!visible.length){
  root.append(make("div","empty",all.length?"条件に合う作品はありません。":"まだ候補データがありません。新規候補の自動取得結果を確認しています。"));
  return;
 }
 for(const w of visible){
   const item=make("article","card"),state=stateOf(w),head=make("div","card-top");
   head.append(make("span","status "+state,statusText[state]),make("span","month",w.month.replace("-","年")+"月"));
   item.append(head);
   item.append(make("h3","",w.title));
   const display=creators[w.handle]?.name;
   item.append(make("p","creator",display?display+"（@"+w.handle+"）":"@"+w.handle));
   const links=make("div","card-anchors");
   links.append(asLink("作品を見る ↗",w.url));
   if(typeof w.commentedNoteUrl==="string"&&notePattern.test(w.commentedNoteUrl)){
     links.append(asLink("最初のコメントが付いた記事 ↗",w.commentedNoteUrl));
   }
   item.append(links);
   const controls=make("div","card-controls");
   for(const next of ["approved","draft","excluded"]){
     const b=make("button",state===next?"active":"",statusText[next]);
     b.type="button";b.dataset.status=next;
     if(saving)b.disabled=true;
     if(state===next)b.setAttribute("aria-pressed","true");
     b.addEventListener("click",()=>change(w,next));
     controls.append(b);
   }
   item.append(controls);root.append(item);
 }
}
async function publicJSON(path){
 const response=await fetch("../data/"+path+"?v="+Date.now(),{cache:"no-store"});
 if(!response.ok)throw Error(path+" HTTP "+response.status);
 return response.json();
}
async function refresh(){
 $("updated").textContent="候補データを読み込み中…";
 const results=await Promise.allSettled([
  publicJSON("candidates.json"),publicJSON("works.json"),
  publicJSON("admin-decisions.json"),publicJSON("creators.json")
 ]);
 const [cand,works,dec,cr]=results;
 const missing=[];
 if(cand.status==="fulfilled"&&Array.isArray(cand.value.works))candidates=cand.value.works.filter(safeWork);
 else missing.push("候補の自動取得データ");
 if(works.status==="fulfilled"&&Array.isArray(works.value.works))published=works.value.works.filter(safeWork);
 else missing.push("従来の掲載データ");
 if(dec.status==="fulfilled"&&dec.value.version===1&&dec.value.decisions&&typeof dec.value.decisions==="object")decisions=dec.value.decisions;
 else missing.push("承認状態");
 if(cr.status==="fulfilled"&&cr.value.creators&&typeof cr.value.creators==="object")creators=cr.value.creators;
 const generated=cand.status==="fulfilled"?cand.value.generatedAt:null;
 const updated=generated?new Date(generated):null;
 const time=updated&&!Number.isNaN(updated.getTime())?new Intl.DateTimeFormat("ja-JP",{timeZone:"Asia/Tokyo",month:"numeric",day:"numeric",hour:"numeric",minute:"2-digit"}).format(updated):null;
 $("updated").textContent=missing.length?"取得できないデータ："+missing.join("、"):(time?"候補一覧 更新 "+time:"候補一覧を表示中");
 draw();
}
function setConnection(connected){
 $("auth-status").textContent=connected?"接続済み（"+OWNER+"）":"未接続";
 $("auth-status").classList.toggle("connected",connected);
 $("disconnect").hidden=!connected;
 $("connect").textContent=connected?"再接続":"接続する";
 if(connected)$("token").value="";
}
function githubHeaders(){
 return {"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"};
}
async function ghRequest(url,options={}){
 const r=await fetch(url,{...options,headers:{...githubHeaders(),...(options.headers||{})},cache:"no-store"});
 if(!r.ok){
   let detail="";
   try{detail=(await r.json()).message||""}catch{}
   const e=new Error("GitHub API "+r.status+(detail?"："+detail:""));e.status=r.status;throw e;
 }
 return r.json();
}
async function connect(){
 const entered=$("token").value.trim()||token;
 if(!entered){notify("GitHubのアクセストークンを入力してください。",true);$("token").focus();return}
 $("connect").disabled=true;
 try{
   token=entered;
   const user=await ghRequest("https://api.github.com/user");
   if(String(user.login).toLowerCase()!==OWNER.toLowerCase())throw Error("この管理画面は "+OWNER+" のGitHubアカウントだけが操作できます。");
   const doc=await ghRequest(API+"?ref=main");
   if(!doc.sha||!doc.content)throw Error("掲載状態のファイルにアクセスできません。Contents の読み書き権限をご確認ください。");
   if($("remember").checked)sessionStorage.setItem(AUTHKEY,token);
   else sessionStorage.removeItem(AUTHKEY);
   setConnection(true);
   notify("接続しました。承認・保留・除外を変更できます。");
 }catch(e){
   token="";sessionStorage.removeItem(AUTHKEY);
   setConnection(false);notify(String(e.message||e),true);
 }finally{$("connect").disabled=false}
}
function disconnect(){
 token="";sessionStorage.removeItem(AUTHKEY);setConnection(false);notify("GitHubとの接続を解除しました。");
}
function utf8base64(s){
 const bytes=new TextEncoder().encode(s);
 let bin="";
 for(let i=0;i<bytes.length;i+=8192)bin+=String.fromCharCode(...bytes.subarray(i,i+8192));
 return btoa(bin);
}
function fromBase64(s){
 const bytes=Uint8Array.from(atob(s.replace(/\s/g,"")),c=>c.charCodeAt(0));
 return new TextDecoder("utf-8",{fatal:true}).decode(bytes);
}
async function change(work,next){
 if(saving)return;
 if(!token){
   notify("変更するには、まずGitHubに接続してください。",true);
   $("token").focus();$("auth-status").scrollIntoView({behavior:"smooth",block:"center"});
   return;
 }
 if(stateOf(work)===next){notify("すでに「"+statusText[next]+"」になっています。");return}
 if(next==="excluded"&&!confirm("「"+work.title+"」を除外しますか？\nいつでも承認や保留に戻せます。"))return;
 const key=keyOf(work);
 saving=true;draw();notify("GitHubへ変更を保存しています…");
 try{
   for(let attempt=0;attempt<3;attempt++){
    const remote=await ghRequest(API+"?ref=main&v="+Date.now());
    const raw=JSON.parse(fromBase64(remote.content));
    if(raw.version!==1||!raw.decisions||typeof raw.decisions!=="object")throw Error("承認データの形式が不正です。");
    raw.decisions[key]={status:next,updatedAt:new Date().toISOString()};
    const content=utf8base64(JSON.stringify(raw,null,2)+"\n");
    try{
     await ghRequest(API,{
      method:"PUT",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({message:"Review featured work: "+key+" -> "+next,content,sha:remote.sha,branch:"main"})
     });
     decisions=raw.decisions;
     notify("「"+work.title+"」を「"+statusText[next]+"」に変更しました。公式サイトへの反映には少し時間がかかります。");
     return;
    }catch(e){if((e.status===409||e.status===422)&&attempt<2)continue;throw e}
   }
 }catch(e){notify("保存できませんでした："+String(e.message||e),true)}
 finally{saving=false;draw()}
}
$("connect").addEventListener("click",connect);
$("disconnect").addEventListener("click",disconnect);
$("refresh").addEventListener("click",()=>refresh().catch(e=>notify(e.message,true)));
$("search").addEventListener("input",draw);
$("token").addEventListener("keydown",e=>{if(e.key==="Enter")connect()});
$("remember").addEventListener("change",()=>{
 if(!token)return;
 if($("remember").checked)sessionStorage.setItem(AUTHKEY,token);
 else sessionStorage.removeItem(AUTHKEY);
});
document.querySelectorAll("[data-filter]").forEach(el=>el.addEventListener("click",()=>{selected=el.dataset.filter;draw()}));
refresh().catch(e=>notify(e.message,true));
const stored=sessionStorage.getItem(AUTHKEY);
if(stored){
 token=stored;$("remember").checked=true;
 connect();
}
