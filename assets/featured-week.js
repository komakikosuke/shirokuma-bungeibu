/* Shared JST Thursday 20:00 editorial week key. */
(function(){
 "use strict";
 function weekStart(work){
  if(typeof work?.weekStart==="string"&&/^\d{4}-\d{2}-\d{2}$/.test(work.weekStart))return work.weekStart;
  const ms=Date.parse(work?.firstCommentAt||"");
  if(!Number.isFinite(ms))return "";
  const jst=new Date(ms+9*60*60*1000);
  const weekday=jst.getUTCDay(); // Sunday=0, Thursday=4
  const days=(weekday-4+7)%7;
  let start=Date.UTC(jst.getUTCFullYear(),jst.getUTCMonth(),jst.getUTCDate()-days,20);
  if(ms+9*60*60*1000<start)start-=7*24*60*60*1000;
  return new Date(start).toISOString().slice(0,10);
 }
 function key(work){return (weekStart(work)||work.month)+"|"+work.handle;}
 function legacyStatus(work,decisions){
  const primary=decisions[key(work)]?.status;
  if(primary)return primary;
  if(!work.weekStart)return decisions[work.month+"|"+work.handle]?.status;
  return null;
 }
 window.shirokumaWeekStart=weekStart;
 window.shirokumaWeekKey=key;
 window.shirokumaDecisionStatus=legacyStatus;
})();