// Sakura petals, drawn the same way as in the app: seeded, 30 fps, paused
// while the tab is hidden. People who ask for less motion get fewer, slower
// petals.
(() => {
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const petal = new Image();
  petal.src = "assets/petal.svg";

  function drift(canvas, { count, sizes, alphas, seed }) {
    const ctx = canvas.getContext("2d");
    let state = seed;
    const random = () => {
      state ^= state << 13; state ^= state >>> 17; state ^= state << 5;
      return (state >>> 0) / 4294967296;
    };
    const petals = Array.from({ length: count }, () => ({
      x: random(), speed: 10 + random() * 14, sway: 6 + random() * 14,
      freq: 0.3 + random() * 0.5, spin: (random() - 0.5) * 60,
      size: sizes[0] + random() * (sizes[1] - sizes[0]),
      alpha: alphas[0] + random() * (alphas[1] - alphas[0]), phase: random() * 6.28,
    }));

    let width = 0, height = 0, scale = 1;
    const resize = () => {
      const box = canvas.getBoundingClientRect();
      scale = window.devicePixelRatio || 1;
      width = box.width; height = box.height;
      canvas.width = Math.round(width * scale); canvas.height = Math.round(height * scale);
    };

    let clock = 0, last = performance.now(), timer = null;
    const draw = () => {
      const now = performance.now();
      clock += ((now - last) / 1000) * (motion.matches ? 0.4 : 1);
      last = now;
      const shown = motion.matches ? petals.slice(0, Math.ceil(count / 2)) : petals;
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      ctx.clearRect(0, 0, width, height);
      for (const p of shown) {
        const x = width * p.x + p.sway * Math.sin(clock * p.freq + p.phase);
        const y = ((clock * p.speed + p.phase * 97) % (height + 40)) - 20;
        ctx.save();
        ctx.globalAlpha = p.alpha;
        ctx.translate(x, y);
        ctx.rotate(((clock * p.spin + p.phase * 57) * Math.PI) / 180);
        ctx.drawImage(petal, -p.size / 2, -p.size * 0.6, p.size, p.size * 1.2);
        ctx.restore();
      }
    };
    const run = () => {
      if (timer || document.hidden) return;
      last = performance.now();
      timer = setInterval(draw, 33);
    };
    const stop = () => { clearInterval(timer); timer = null; };

    resize();
    new ResizeObserver(resize).observe(canvas);
    document.addEventListener("visibilitychange", () => (document.hidden ? stop() : run()));
    if (petal.complete) run(); else petal.addEventListener("load", run);
  }

  window.hanamiPetals = drift;
  drift(document.getElementById("petals"), { count: 16, sizes: [9, 16], alphas: [0.25, 0.6], seed: 0x2545f491 });

  // Pink goes to the download for the visitor's own system.
  const platform = (navigator.userAgentData?.platform || navigator.userAgent).toLowerCase();
  const os = platform.includes("win") ? "windows" : platform.includes("linux") || platform.includes("x11") ? "linux" : null;
  if (os) document.querySelector(`.button[data-os="${os}"]`)?.classList.add("mine");
})();
