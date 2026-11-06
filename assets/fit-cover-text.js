/* Shared responsive cover typography for the homepage and article archive. */
(function () {
 "use strict";
 function fitOne(block) {
  const text = block.querySelector(".cover-fit-text");
  if (!text || block.clientHeight === 0 || block.clientWidth === 0) return;
  block.style.removeProperty("font-size");
  const max = parseFloat(getComputedStyle(block).fontSize);
  if (!Number.isFinite(max) || max <= 0) return;
  // Measure the real, fully wrapped text rather than the clipped parent.
  const fits = () => {
   const bounds = text.getBoundingClientRect();
   return bounds.height <= block.clientHeight + 0.8 &&
          bounds.width <= block.clientWidth + 0.8 &&
          text.scrollWidth <= block.clientWidth + 0.8;
  };
  if (fits()) return;
  let low = Math.min(9, max), high = max;
  block.style.fontSize = low + "px";
  if (!fits()) {
   block.dataset.coverOverflow = "true";
   // Very unusual titles remain available in full on the article link.
   return;
  }
  for (let i = 0; i < 15; i++) {
   const mid = (low + high) / 2;
   block.style.fontSize = mid + "px";
   if (fits()) low = mid; else high = mid;
  }
  block.style.fontSize = Math.max(9,low-.2).toFixed(2) + "px";
  delete block.dataset.coverOverflow;
 }
 let scheduled = false;
 function refit() {
  if (scheduled) return;
  scheduled = true;
  requestAnimationFrame(() => {
   scheduled = false;
   document.querySelectorAll(".cover-fit").forEach(fitOne);
  });
 }
 window.shirokumaFitCovers = refit;
 window.addEventListener("resize",refit,{passive:true});
 if (document.fonts && document.fonts.ready) document.fonts.ready.then(refit);
})();
