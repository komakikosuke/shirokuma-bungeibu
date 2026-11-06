"use strict";
// The archive uses exactly the same candidate/decision merge rules as the homepage.
// Excluded and previously held ("draft") works stay hidden across refreshes.
const $=id=>document.getElementById(id);
const NOTE=/^https:\/\/note\.com\/[A-Za-z0-9_-]+\/n\/n[A-Za-z0-9]+\/?$/;
const PAGE_SIZE=20;
let articles=[];
let names={};
let visibleCount=PAGE_SIZE;
const labelOf=work=>names[work.handle]?.name?.trim()||"クリエイター名を確認中";
function safeWork(w){
 if(!w||typeof w!=="object"||typeof w.month!=="string"||!/^\d{4}-\d{2}$/.test(w.month))return false;
 if(typeof w.handle!=="string"||!/^[A-Za-z0-9_-]{2,100}$/.test(w.handle))return false;
 if(typeof w.title!=="string"||!w.title.trim()||w.title.length>500)return false;
 if(typeof w.url!=="string"||!NOTE.test(w.url))return false;
 return new URL(w.url).pathname.split("/")[1]===w.handle;
}
function element(tag,className,text){
 const e=document.createElement(tag);
 if(className)e.className=className;
 if(text!==undefined)e.textContent=text;
 return e;
}
function link(text,url,className){
 const a=element("a",className,text);
 a.href=url;a.target="_blank";a.rel="noopener noreferrer";
 return a;
}
async function getData(name){
 const r=await fetch("../data/"+name+"?v="+Date.now(),{cache:"no-store"});
 if(!r.ok)throw Error(name+"の読み込みに失敗しました (HTTP "+r.status+")");
 return r.json();
}
function merge(works,candidates,decisions){
 if(!works||works.version!==1||!Array.isArray(works.works)||
    !candidates||candidates.version!==1||!Array.isArray(candidates.works)||
    !decisions||decisions.version!==1||!decisions.decisions||typeof decisions.decisions!=="object"){
   throw Error("掲載データの形式が正しくありません");
 }
 const m=new Map();
 for(const w of works.works)if(safeWork(w))m.set(w.month+"|"+w.handle,w);
 for(const w of candidates.works)if(safeWork(w))m.set(w.month+"|"+w.handle,w);
 for(const [key] of m){
   if(["draft","excluded"].includes(decisions.decisions[key]?.status))m.delete(key);
 }
 return [...m.values()].sort((a,b)=>String(b.firstCommentAt||"").localeCompare(String(a.firstCommentAt||""))||b.month.localeCompare(a.month));
}
function articleCard(w){
 const card=element("article","article-item");
 const coverLink=link("",w.url,"cover-link");
 const name=labelOf(w);
 coverLink.setAttribute("aria-label",name+"「"+w.title+"」を読む");
 const book=element("div","mini-book");
 const content=element("div","mini-content");
 const title=element("h2","mini-title",w.title);
 const n=[...w.title].length;
 if(n>39)title.classList.add("very-long");
 else if(n>22)title.classList.add("long");
 const rule=element("div","mini-rule");
 rule.setAttribute("aria-hidden","true");
 const byline=element("p","mini-creator",name);
 if([...name].length>17)byline.classList.add("long");
 const imprint=element("div","mini-footer");
 imprint.append(element("strong","", "シロクマ文芸部"),element("small","","SHIROKUMA BUNGEIBU"));
 content.append(title,rule,byline,imprint);
 book.append(content);coverLink.append(book);card.append(coverLink);
 const read=link("作品を読む　→",w.url,"read-link");
 read.setAttribute("aria-label",name+"「"+w.title+"」を読む");
 card.append(read);
 return card;
}
function render(){
 const grid=$("articleGrid");
 const batch=articles.slice(0,visibleCount);
 grid.replaceChildren();
 if(!batch.length){
   grid.append(element("div","empty","掲載中の作品はまだありません。"));
 }else{
   for(const work of batch)grid.append(articleCard(work));
 }
 $("itemTotal").textContent="全"+new Intl.NumberFormat("ja-JP").format(articles.length)+"作品";
 $("loadMore").hidden=visibleCount>=articles.length;
 const remainder=articles.length-visibleCount;
 if(remainder>0)$("loadMore").firstChild.textContent="さらに"+Math.min(PAGE_SIZE,remainder)+"作品を見る ";
}
async function init(){
 try{
   const [works,candidates,decisions,creators]=await Promise.all([
     getData("works.json"),getData("candidates.json"),getData("admin-decisions.json"),getData("creators.json")
   ]);
   names=creators?.creators&&typeof creators.creators==="object"?creators.creators:{};
   articles=merge(works,candidates,decisions);
   render();
 }catch(err){
   console.error("注目記事一覧の読み込みに失敗しました",err);
   $("itemTotal").textContent="作品を取得できませんでした";
   $("articleGrid").replaceChildren(element("div","empty","作品を取得できませんでした。ページを再読み込みしてください。"));
   $("loadMore").hidden=true;
 }
}
$("loadMore").addEventListener("click",()=>{visibleCount+=PAGE_SIZE;render()});
init();
