// The panel on the page works like the real one: type to filter, arrows and
// Enter, hover and click, Esc to hide, the ? copies a prompt for an AI.
(() => {
  const demo = document.getElementById("demo");
  const list = document.getElementById("demo-list");
  const title = document.getElementById("demo-title");
  const count = document.getElementById("demo-count");
  const foot = document.getElementById("demo-foot");
  const help = document.getElementById("demo-help");
  const reopen = document.getElementById("demo-reopen");
  const hint = "type to search · enter to play · esc to hide";
  const prompt =
    "Read Hanami's guide at https://github.com/sjdsjadjajdjsa/hanami/blob/main/GUIDE.md " +
    "and tell me, briefly and in plain words, what Hanami does, how to install it on my computer, " +
    "which of my games it would find, and what I can customise. Don't change anything on my computer yet.";

  const games = [...list.querySelectorAll(".demo-row")].map((row) => ({
    name: row.querySelector(".demo-name").textContent,
    label: row.querySelector(".demo-label").textContent,
  }));
  let query = "", shown = games, selected = 0, notice = null;

  const rank = (name) => {
    const n = name.toLowerCase(), q = query.toLowerCase();
    if (n.startsWith(q)) return 0;
    if (n.split(/[^a-z0-9]+/).some((w) => w.startsWith(q))) return 1;
    return n.includes(q) ? 2 : -1;
  };

  function render() {
    shown = query
      ? games.map((g, i) => [rank(g.name), i, g]).filter(([r]) => r >= 0).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(([, , g]) => g)
      : games;
    selected = Math.min(selected, Math.max(shown.length - 1, 0));
    title.textContent = query || "hanami";
    title.classList.toggle("typing", !!query);
    count.textContent = query ? `${shown.length} of ${games.length}` : `${games.length} games`;
    list.replaceChildren(
      ...shown.map((g, i) => {
        const row = document.createElement("li");
        row.className = "demo-row" + (i === selected ? " selected" : "");
        row.setAttribute("role", "option");
        row.setAttribute("aria-selected", String(i === selected));
        row.innerHTML = `<span class="demo-name"></span><span class="demo-label"></span>`;
        row.firstChild.textContent = g.name;
        row.lastChild.textContent = g.label;
        row.addEventListener("mousemove", () => { if (selected !== i) { selected = i; render(); } });
        row.addEventListener("click", () => { selected = i; start(); });
        return row;
      })
    );
    if (!shown.length) {
      const empty = document.createElement("li");
      empty.className = "demo-empty";
      empty.textContent = `Nothing matches "${query}".`;
      list.append(empty);
    }
  }

  function say(text, ms = 2600) {
    foot.textContent = text;
    foot.classList.add("notice");
    clearTimeout(notice);
    notice = setTimeout(() => { foot.textContent = hint; foot.classList.remove("notice"); }, ms);
  }

  function hide() {
    demo.classList.add("away");
    reopen.hidden = false;
  }

  function show() {
    demo.classList.remove("away");
    reopen.hidden = true;
    query = ""; selected = 0; render();
    demo.focus({ preventScroll: true });
  }

  function start() {
    const game = shown[selected];
    if (!game) return;
    say(`Starting ${game.name}`, 900);
    setTimeout(hide, 700);
  }

  demo.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "ArrowDown") selected = Math.min(selected + 1, shown.length - 1);
    else if (e.key === "ArrowUp") selected = Math.max(selected - 1, 0);
    else if (e.key === "Enter") return start();
    else if (e.key === "Escape") return hide();
    else if (e.key === "Backspace") query = query.slice(0, -1);
    else if (e.key.length === 1) { query += e.key; selected = 0; }
    else return;
    e.preventDefault();
    render();
  });

  help.addEventListener("mouseenter", () => { if (!foot.classList.contains("notice")) foot.textContent = "Copy a prompt that explains Hanami to your AI"; });
  help.addEventListener("mouseleave", () => { if (!foot.classList.contains("notice")) foot.textContent = hint; });
  help.addEventListener("click", async (e) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(prompt);
      say("Copied. Paste it into your AI.");
    } catch {
      say("Couldn't copy here. The guide is on GitHub.");
    }
  });

  reopen.addEventListener("click", show);
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.altKey && e.key.toLowerCase() === "h") {
      e.preventDefault();
      demo.classList.contains("away") ? show() : hide();
    }
  });

  window.hanamiPetals?.(demo.querySelector(".demo-petals"), { count: 18, sizes: [7, 13], alphas: [0.35, 0.8], seed: 0x4f6cdd1d });
  render();
})();
