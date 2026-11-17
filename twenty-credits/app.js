(() => {
  "use strict";

  const experience = document.getElementById("experience");
  const creditsWindow = document.querySelector(".credits-window");
  const track = document.getElementById("creditsTrack");
  const timeline = document.getElementById("timelineFill");
  const loadingMessage = document.getElementById("loadingMessage");
  const toggleButton = document.getElementById("toggleButton");
  const toggleLabel = document.getElementById("toggleLabel");
  const restartButton = document.getElementById("restartButton");
  const soundButton = document.getElementById("soundButton");
  const soundtrack = document.getElementById("soundtrack");
  const startGate = document.getElementById("startGate");
  const startWithSound = document.getElementById("startWithSound");
  const startWithoutSound = document.getElementById("startWithoutSound");
  const musicStatus = document.getElementById("musicStatus");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const autoplayDisabled = new URLSearchParams(window.location.search).get("autoplay") === "0";
  const DEFAULT_DURATION = 87.053333;
  const DEFAULT_SOUNDTRACK_DURATION = 646.109333;
  const ROLL_SPEED = 2;
  const FADE_SECONDS = 8;
  const BASE_VOLUME = 0.58;
  let isReduced = reducedMotion.matches || autoplayDisabled;
  let hasStarted = false;
  let isPlaying = false;
  let hasWorks = false;
  let mediaClock = false;
  let resumeAfterVisibility = false;
  let frame = 0;
  let operation = 0;
  let position = 0;
  let anchorPosition = 0;
  let anchorTime = 0;
  let startY = 0;
  let endY = 0;
  let minimumRollDuration = 0;
  let lastMediaTime = 0;
  let mediaOffset = 0;
  let audioContext;
  let gain;

  const creditGroups = [
    { key: "membership", label: "MEMBERSHIP MEMBERS" },
    { key: "club", label: "CLUB MEMBERS" },
  ];

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
    scene.append(element("p", "intro-copy", "すぐ書ける。すぐ読める。"));
    return scene;
  };

  const groupScene = (group) => {
    const scene = element("article", `credit-scene credits-group-heading credits-group-heading--${group.key}`);
    scene.append(element("p", "group-kicker", "SHIROKUMA LITERARY CLUB"));
    scene.append(element("h2", "group-title", group.label));
    scene.append(element("span", "group-rule"));
    return scene;
  };

  const workScene = (work, groupKey) => {
    const scene = element("article", `credit-scene credit-work credit-work--${groupKey}`);
    scene.append(element("p", "story-text", work.text));
    scene.append(element("span", "credit-rule"));

    const byline = element("div", "credit-byline");
    if (groupKey === "membership") {
      byline.append(element("span", "credit-byline-label", "WRITTEN BY"));
    }
    byline.append(element("strong", "credit-author", work.authorName));
    scene.append(byline);
    return scene;
  };

  const emptyScene = () => {
    const scene = element("article", "credit-scene credits-group-heading");
    scene.append(element("p", "group-kicker", "EVERY TUESDAY / 20:00"));
    scene.append(element("h2", "group-title", "準備中"));
    scene.append(element("span", "group-rule"));
    return scene;
  };

  const outro = () => {
    const scene = element("article", "credit-scene credits-outro");
    scene.append(image("outro-mark"));
    scene.append(element("p", "outro-overline", "SHIROKUMA LITERARY CLUB"));
    scene.append(element("h2", "", "また、火曜日の夜に。"));
    scene.append(element("p", "outro-note", "20字小説 ─ THE END"));
    scene.append(element("p", "outro-music", "MUSIC　『在りし日の停留所』 / BGMer"));
    return scene;
  };

  const soundtrackDuration = () => Number.isFinite(soundtrack.duration) && soundtrack.duration > 0
    ? soundtrack.duration : DEFAULT_SOUNDTRACK_DURATION;
  // Credits run twice as fast; a longer soundtrack never stretches the roll.
  const duration = () => Math.max(DEFAULT_DURATION, minimumRollDuration) / ROLL_SPEED;

  const updateSoundState = () => {
    experience.classList.toggle("is-muted", soundtrack.muted);
    soundButton.setAttribute("aria-pressed", String(soundtrack.muted));
    soundButton.setAttribute("aria-label", soundtrack.muted ? "音楽を流す" : "音楽を消す");
  };

  const measure = () => {
    const height = experience.clientHeight;
    startY = height * 0.72;
    endY = height * 0.92 - track.offsetHeight;
  };

  const paint = () => {
    const progress = Math.max(0, Math.min(1, position / duration()));
    const fadeRatio = Math.max(0, Math.min(1, (duration() - position) / FADE_SECONDS));
    track.style.transform = isReduced ? "none"
      : "translate3d(0," + (startY + (endY - startY) * progress) + "px,0)";
    timeline.style.width = (progress * 100) + "%";
    creditsWindow.style.opacity = isReduced ? "1" : String(fadeRatio);
    // GainNode also supports the fade on Safari devices with fixed media volume.
    if (gain) gain.gain.value = BASE_VOLUME * fadeRatio;
    else soundtrack.volume = BASE_VOLUME * fadeRatio;
  };

  const readClock = () => {
    if (!mediaClock) return anchorPosition + (performance.now() - anchorTime) / 1000;
    const currentTime = soundtrack.currentTime;
    if (currentTime < lastMediaTime - soundtrackDuration() / 2) {
      mediaOffset += soundtrackDuration();
    }
    lastMediaTime = currentTime;
    return mediaOffset + currentTime;
  };

  const stopFrame = () => {
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
  };

  const finish = () => {
    operation += 1;
    isPlaying = false;
    soundtrack.pause();
    stopFrame();
    position = duration();
    paint();
    experience.classList.remove("is-paused", "is-starting");
    experience.classList.add("is-ended");
    toggleLabel.textContent = "もう一度";
  };

  const tick = () => {
    if (!isPlaying) return;
    position = Math.min(duration(), readClock());
    paint();
    if (position >= duration()) finish();
    else frame = requestAnimationFrame(tick);
  };

  const prepareAudio = async () => {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (AudioContext && !audioContext) {
      try {
        audioContext = new AudioContext();
        const source = audioContext.createMediaElementSource(soundtrack);
        gain = audioContext.createGain();
        gain.gain.value = BASE_VOLUME * Math.max(0, Math.min(1, (duration() - position) / FADE_SECONDS));
        source.connect(gain);
        gain.connect(audioContext.destination);
        soundtrack.volume = 1;
      } catch {
        audioContext = undefined;
        gain = undefined;
      }
    }
    if (audioContext && audioContext.state === "suspended") {
      await audioContext.resume();
    }
  };

  const play = async () => {
    if (!hasWorks || isPlaying) return;
    const currentOperation = ++operation;
    isPlaying = true;
    experience.classList.remove("is-paused", "is-ended");
    experience.classList.add("is-starting");
    toggleLabel.textContent = "一時停止";
    paint();
    try {
      // Both audio and scrolling start from this position after playback is ready.
      mediaOffset = Math.floor(position / soundtrackDuration()) * soundtrackDuration();
      lastMediaTime = position - mediaOffset;
      soundtrack.currentTime = lastMediaTime;
      soundtrack.loop = duration() > soundtrackDuration();
      // Call play inside the click event to preserve Safari user activation.
      await Promise.all([prepareAudio(), soundtrack.play()]);
      if (currentOperation !== operation) return;
      mediaClock = true;
      musicStatus.textContent = "";
    } catch {
      if (currentOperation !== operation) return;
      mediaClock = false;
      soundtrack.pause();
      soundtrack.muted = true;
      updateSoundState();
      musicStatus.textContent = "音楽を再生できないため、無音で上映しています。";
    }
    anchorPosition = position;
    anchorTime = performance.now();
    experience.classList.remove("is-starting");
    stopFrame();
    tick();
  };

  const pause = () => {
    if (!isPlaying) return;
    if (!experience.classList.contains("is-starting")) {
      position = Math.min(duration(), readClock());
    }
    operation += 1;
    isPlaying = false;
    soundtrack.pause();
    stopFrame();
    paint();
    experience.classList.remove("is-starting");
    experience.classList.add("is-paused");
    toggleLabel.textContent = "再生する";
  };

  const setMotionMode = (reduced) => {
    if (reduced) pause();
    isReduced = reduced;
    document.documentElement.dataset.motion = reduced ? "reduced" : "auto";
    measure();
    paint();
    if (reduced) toggleLabel.textContent = "自動再生";
  };

  const begin = async (withSound) => {
    if (!hasWorks) return;
    pause();
    hasStarted = true;
    startGate.hidden = true;
    experience.classList.remove("is-awaiting-start", "is-ended");
    setMotionMode(false);
    position = 0;
    mediaClock = false;
    soundtrack.muted = !withSound;
    updateSoundState();
    measure();
    paint();
    await play();
  };

  const restart = () => begin(!soundtrack.muted);

  const togglePlayback = () => {
    if (!hasStarted) return begin(true);
    if (isReduced || experience.classList.contains("is-ended")) return restart();
    if (isPlaying) pause();
    else return play();
  };

  const toggleSound = () => {
    if (!hasStarted) return begin(true);
    soundtrack.muted = !soundtrack.muted;
    updateSoundState();
    // Retry a failed audio load at the current roll position.
    if (!mediaClock && !soundtrack.muted && isPlaying) {
      pause();
      return play();
    }
  };

  const render = (data) => {
    if (!data || !Array.isArray(data.works)) throw new Error("表示データの形式が違います");
    const fragment = document.createDocumentFragment();
    const groupedWorks = data.works.map((work) => ({
      ...work,
      creditGroup: work.creditGroup === "membership" ? "membership" : "club",
    }));
    fragment.append(intro());
    let renderedGroupCount = 0;
    creditGroups.forEach((group) => {
      const works = groupedWorks.filter((work) => work.creditGroup === group.key);
      if (works.length === 0) return;
      renderedGroupCount += 1;
      fragment.append(groupScene(group));
      works.forEach((work) => fragment.append(workScene(work, group.key)));
    });
    // Reading time controls the roll independently from the music's playback rate.
    minimumRollDuration = groupedWorks.length * 8 + renderedGroupCount * 7;
    hasWorks = groupedWorks.length > 0;
    if (!hasWorks) fragment.append(emptyScene());
    fragment.append(outro());
    track.replaceChildren(fragment);
    experience.classList.remove("is-loading");
    [toggleButton, restartButton, soundButton, startWithSound, startWithoutSound]
      .forEach((button) => { button.disabled = !hasWorks; });
    if (!hasWorks) {
      startGate.hidden = true;
      experience.classList.remove("is-awaiting-start");
    }
    setMotionMode(isReduced || !hasWorks);
    measure();
    paint();
  };

  const showError = () => {
    loadingMessage.textContent = "作品を読み込めませんでした。時間をおいて再度お試しください。";
    loadingMessage.classList.add("error-message");
    startGate.hidden = true;
  };

  startWithSound.addEventListener("click", () => { void begin(true); });
  startWithoutSound.addEventListener("click", () => { void begin(false); });
  toggleButton.addEventListener("click", () => { void togglePlayback(); });
  restartButton.addEventListener("click", () => { void restart(); });
  soundButton.addEventListener("click", () => { void toggleSound(); });
  soundtrack.addEventListener("loadedmetadata", () => { measure(); paint(); });
  soundtrack.addEventListener("ended", () => { if (isPlaying && mediaClock) finish(); });
  soundtrack.addEventListener("error", () => {
    if (!isPlaying || !mediaClock) return;
    anchorPosition = position;
    anchorTime = performance.now();
    mediaClock = false;
    soundtrack.muted = true;
    updateSoundState();
    musicStatus.textContent = "音楽を再生できないため、無音で上映しています。";
  });
  document.addEventListener("keydown", (event) => {
    if (event.target instanceof HTMLElement
        && event.target.closest("button, a, input, textarea, select, [contenteditable]")) return;
    if (event.code === "Space" && !event.repeat && event.target === document.body) {
      event.preventDefault();
      void togglePlayback();
    }
    if (event.key.toLowerCase() === "r" && !event.repeat) void restart();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && isPlaying) {
      pause();
      resumeAfterVisibility = true;
    } else if (!document.hidden && resumeAfterVisibility) {
      resumeAfterVisibility = false;
      void play();
    }
  });
  reducedMotion.addEventListener?.("change", (event) => {
    setMotionMode(event.matches || autoplayDisabled);
  });
  window.addEventListener("resize", () => { measure(); paint(); });
  document.fonts?.ready.then(() => { measure(); paint(); });
  soundtrack.volume = BASE_VOLUME;
  updateSoundState();
  fetch("./data/works.json", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(render)
    .catch(showError);
})();
