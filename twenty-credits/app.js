(() => {
  "use strict";

  const experience = document.getElementById("experience");
  const track = document.getElementById("creditsTrack");
  const timeline = document.getElementById("timelineFill");
  const loadingMessage = document.getElementById("loadingMessage");
  const toggleButton = document.getElementById("toggleButton");
  const toggleLabel = document.getElementById("toggleLabel");
  const restartButton = document.getElementById("restartButton");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const autoplayDisabled = new URLSearchParams(window.location.search).get("autoplay") === "0";
  let isReduced = reducedMotion.matches || autoplayDisabled;
  let resumeAfterVisibility = false;

  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const image = (className) => {
    const node = element("img", className);
    node.src = "../assets/polarbear-icon.png";
    node.alt = "";
    node.width = 120;
    node.height = 120;
    return node;
  };

  const intro = () => {
    const scene = element("article", "credit-scene credits-intro");
    scene.append(image("intro-mark"));
    scene.append(element("p", "intro-present", "SHIROKUMA LITERARY CLUB PRESENTS"));
    scene.append(element("h2", "", "20字小説"));
    scene.append(element("span", "intro-rule"));
    scene.append(element("p", "intro-copy", "一行目から、ひとつの世界へ。"));
    return scene;
  };

  const workScene = (work) => {
    const scene = element("article", "credit-scene credit-work");
    scene.append(element("p", "story-text", work.text));
    scene.append(element("span", "credit-rule"));

    const byline = element("div", "credit-byline");
    byline.append(element("span", "credit-byline-label", "WRITTEN BY"));
    byline.append(element("strong", "credit-author", work.authorName));
    scene.append(byline);
    return scene;
  };

  const interlude = () => {
    const scene = element("article", "credit-scene credits-interlude");
    scene.append(element("p", "interlude-en", "TWENTY CHARACTERS, A WHOLE WORLD"));
    scene.append(element("p", "interlude-copy", "二十字の向こうに、物語はつづく。"));
    return scene;
  };

  const outro = () => {
    const scene = element("article", "credit-scene credits-outro");
    scene.append(image("outro-mark"));
    scene.append(element("p", "outro-overline", "SHIROKUMA LITERARY CLUB"));
    scene.append(element("h2", "", "また、火曜日の夜に。"));
    scene.append(element("p", "outro-note", "20字小説 ─ THE END"));
    return scene;
  };

  const setMotionMode = (reduced) => {
    isReduced = reduced;
    document.documentElement.dataset.motion = reduced ? "reduced" : "auto";
    experience.classList.toggle("is-paused", reduced);
    toggleLabel.textContent = reduced ? "自動再生" : "一時停止";
  };

  const restart = () => {
    if (isReduced) {
      setMotionMode(false);
    }
    experience.classList.remove("is-ended", "is-paused");
    track.style.animation = "none";
    timeline.style.animation = "none";
    void track.offsetWidth;
    track.style.animation = "";
    timeline.style.animation = "";
    toggleLabel.textContent = "一時停止";
  };

  const togglePlayback = () => {
    if (isReduced || experience.classList.contains("is-ended")) {
      restart();
      return;
    }
    const paused = experience.classList.toggle("is-paused");
    toggleLabel.textContent = paused ? "再生する" : "一時停止";
  };

  const render = (data) => {
    if (!data || !Array.isArray(data.works) || data.works.length === 0) {
      throw new Error("表示できる作品がありません");
    }

    const fragment = document.createDocumentFragment();
    fragment.append(intro());
    data.works.forEach((work, index) => {
      fragment.append(workScene(work));
      if (index === Math.ceil(data.works.length / 2) - 1) fragment.append(interlude());
    });
    fragment.append(outro());
    track.replaceChildren(fragment);

    const duration = Math.max(66, 24 + data.works.length * 9);
    document.documentElement.style.setProperty("--duration", `${duration}s`);
    experience.classList.remove("is-loading");
    toggleButton.disabled = false;
    restartButton.disabled = false;
    setMotionMode(isReduced);
  };

  const showError = () => {
    loadingMessage.textContent = "作品を読み込めませんでした。時間をおいて再度お試しください。";
    loadingMessage.classList.add("error-message");
  };

  toggleButton.addEventListener("click", togglePlayback);
  restartButton.addEventListener("click", restart);
  track.addEventListener("animationend", (event) => {
    if (event.animationName !== "credits-roll") return;
    experience.classList.add("is-ended");
    toggleLabel.textContent = "もう一度";
  });
  document.addEventListener("keydown", (event) => {
    if (event.code === "Space" && !event.repeat && event.target === document.body) {
      event.preventDefault();
      togglePlayback();
    }
    if (event.key.toLowerCase() === "r" && !event.repeat) restart();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && !experience.classList.contains("is-paused") && !isReduced) {
      resumeAfterVisibility = true;
      experience.classList.add("is-paused");
    } else if (!document.hidden && resumeAfterVisibility) {
      resumeAfterVisibility = false;
      experience.classList.remove("is-paused");
    }
  });

  fetch("./data/works.json", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then(render)
    .catch(showError);
})();
