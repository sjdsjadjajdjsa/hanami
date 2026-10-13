// A few sakura petals drifting behind the page, like in the app: 30 fps,
// paused while the tab is hidden, and off for people who ask for less motion.
(() => {
  const canvas = document.getElementById("petals");
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const ctx = canvas.getContext("2d");
  const petal = new Image();
  petal.src = "assets/petal.svg";

  let seed = 0x2545f491;
  const random = () => {
    seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
    return (seed >>> 0) / 4294967296;
  };
  const petals = Array.from({ length: 16 }, () => ({
    x: random(), speed: 10 + random() * 14, sway: 8 + random() * 18,
    freq: 0.3 + random() * 0.5, spin: (random() - 0.5) * 60,
    size: 9 + random() * 7, alpha: 0.25 + random() * 0.35, phase: random() * 6.28,
  }));

  let width = 0, height = 0, scale = 1;
  const resize = () => {
    scale = window.devicePixelRatio || 1;
    width = window.innerWidth; height = window.innerHeight;
    canvas.width = width * scale; canvas.height = height * scale;
  };

  const draw = (t) => {
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    ctx.clearRect(0, 0, width, height);
    for (const p of petals) {
      const x = width * p.x + p.sway * Math.sin(t * p.freq + p.phase);
      const y = ((t * p.speed + p.phase * 97) % (height + 40)) - 20;
      ctx.save();
      ctx.globalAlpha = p.alpha;
      ctx.translate(x, y);
      ctx.rotate(((t * p.spin + p.phase * 57) * Math.PI) / 180);
      ctx.drawImage(petal, -p.size / 2, -p.size * 0.6, p.size, p.size * 1.2);
      ctx.restore();
    }
  };

  let timer = null;
  const start = performance.now();
  const run = () => {
    if (timer || motion.matches || document.hidden) return;
    timer = setInterval(() => draw((performance.now() - start) / 1000), 33);
  };
  const stop = () => { clearInterval(timer); timer = null; };
  const update = () => { stop(); if (motion.matches) ctx.clearRect(0, 0, canvas.width, canvas.height); else run(); };

  resize();
  window.addEventListener("resize", resize);
  document.addEventListener("visibilitychange", update);
  motion.addEventListener("change", update);
  petal.addEventListener("load", run);

  // Pink goes to the download for the visitor's own system.
  const platform = (navigator.userAgentData?.platform || navigator.userAgent).toLowerCase();
  const os = platform.includes("win") ? "windows" : platform.includes("linux") || platform.includes("x11") ? "linux" : null;
  if (os) document.querySelector(`.button[data-os="${os}"]`)?.classList.add("mine");
})();
