// The panel on the page works like the real one: type to filter (first
// letters and small typos too), arrows and Enter, hover and click, Tab or
// right-click for Pin, Rename and Hide, Esc to hide, ? copies a prompt.
(() => {
  const demo = document.getElementById("demo");
  const list = document.getElementById("demo-list");
  const title = document.getElementById("demo-title");
  const count = document.getElementById("demo-count");
  const foot = document.getElementById("demo-foot");
  const help = document.getElementById("demo-help");
  const add = document.getElementById("demo-add");
  const reopen = document.getElementById("demo-reopen");
  const hint = "type to search · enter to play · tab for more";
  const keys = new Set(["Escape", "Tab", "ContextMenu", "ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp", "Enter", "Backspace"]);
  const prompt =
    "Read Hanami's guide at https://github.com/sjdsjadjajdjsa/hanami/blob/main/GUIDE.md " +
    "and tell me, briefly and in plain words, what Hanami does, how to install it on my computer, " +
    "which of my games it would find, and what I can customise. Don't change anything on my computer yet.";

  const games = [...list.querySelectorAll(".demo-row")].map((row) => ({
    name: row.querySelector(".demo-name").textContent,
    label: row.querySelector(".demo-label").textContent,
    icon: row.querySelector(".demo-icon").getAttribute("src"),
    pinned: row.dataset.pinned === "true",
  }));
  let query = "", shown = games, selected = 0, notice = null;
  let acting = -1, action = 0, renaming = -1;

  const words = (name) => name.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  const rank = (name) => {
    const n = name.toLowerCase(), q = query.toLowerCase(), w = words(name);
    if (n.startsWith(q)) return 0;
    if (w.some((word) => word.startsWith(q))) return 1;
    if (q.length > 1 && w.map((word) => word[0]).join("").startsWith(q)) return 2;
    return n.includes(q) ? 3 : -1;
  };
  // Letters in order ("holow"), only when nothing matches the usual way.
  const loose = (name) => {
    const q = query.toLowerCase();
    let i = 0;
    for (const c of name.toLowerCase()) if (c === q[i]) i++;
    return i === q.length;
  };
  const ordered = () => [...games.filter((g) => g.pinned), ...games.filter((g) => !g.pinned)];

  function filter() {
    const all = ordered();
    if (!query) return all;
    const hits = all.map((g, i) => [rank(g.name), i, g]).filter(([r]) => r >= 0)
      .sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(([, , g]) => g);
    return hits.length || query.length < 3 ? hits : all.filter((g) => loose(g.name));
  }

  function footer() {
    if (foot.classList.contains("notice")) return;
    foot.textContent = renaming >= 0 ? "enter to save · esc to cancel"
      : acting >= 0 ? "← → to choose · enter to do it · esc to go back" : hint;
  }

  function render() {
    shown = filter();
    selected = Math.min(selected, Math.max(shown.length - 1, 0));
    title.textContent = query || "hanami";
    title.classList.toggle("typing", !!query);
    count.textContent = query ? `${shown.length} of ${games.length}` : `${games.length} games`;
    footer();
    list.replaceChildren(...shown.map(row));
    if (!shown.length) {
      const empty = document.createElement("li");
      empty.className = "demo-empty";
      empty.textContent = games.length ? `Nothing matches "${query}".` : "No games yet. Add one with +.";
      list.append(empty);
    }
  }

  function row(g, i) {
    const li = document.createElement("li");
    li.className = "demo-row" + (i === selected && acting !== i ? " selected" : "") + (i === renaming ? " renaming" : "");
    li.setAttribute("role", "option");
    li.setAttribute("aria-selected", String(i === selected));
    if (i === acting) {
      li.classList.add("acting");
      [g.pinned ? "Unpin" : "Pin to top", "Rename", "Hide"].forEach((text, n) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "demo-chip" + (n === action ? " lit" : "");
        chip.textContent = text;
        chip.addEventListener("click", (e) => { e.stopPropagation(); act(n); });
        li.append(chip);
      });
      return li;
    }
    const icon = document.createElement("img");
    icon.className = "demo-icon";
    icon.src = g.icon;
    icon.alt = "";
    li.append(icon);
    if (i === renaming) {
      const input = document.createElement("input");
      input.className = "demo-rename";
      input.value = g.name;
      input.setAttribute("aria-label", "New name");
      input.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key !== "Enter" && e.key !== "Escape") return;
        e.preventDefault();
        if (e.key === "Enter" && input.value.trim()) g.name = input.value.trim();
        renaming = -1;
        render();
        demo.focus({ preventScroll: true });
      });
      li.append(input);
      queueMicrotask(() => { input.focus({ preventScroll: true }); input.select(); });
    } else {
      const name = document.createElement("span");
      name.className = "demo-name";
      name.textContent = g.name;
      const label = document.createElement("span");
      label.className = "demo-label";
      label.textContent = g.pinned ? `pinned · ${g.label}` : g.label;
      li.append(name, label);
    }
    li.addEventListener("mousemove", () => { if (acting < 0 && renaming < 0 && selected !== i) { selected = i; render(); } });
    li.addEventListener("click", () => { if (acting < 0 && renaming < 0) { selected = i; start(); } });
    li.addEventListener("contextmenu", (e) => { e.preventDefault(); more(i); });
    return li;
  }

  function more(i) {
    if (renaming >= 0 || !shown[i]) return;
    selected = acting = i;
    action = 0;
    render();
  }

  function act(n) {
    const g = shown[acting];
    acting = -1;
    if (!g) return render();
    if (n === 0) g.pinned = !g.pinned;
    if (n === 2) {
      games.splice(games.indexOf(g), 1);
      say(`Hid ${g.name}. In the app it's listed under hide in the settings.`, 3200);
    }
    render();
    if (n !== 2) selected = shown.indexOf(g);
    if (n === 1) renaming = selected;
    render();
  }

  function say(text, ms = 2600) {
    foot.textContent = text;
    foot.classList.add("notice");
    clearTimeout(notice);
    notice = setTimeout(() => { foot.classList.remove("notice"); footer(); }, ms);
  }

  function hide() {
    acting = renaming = -1;
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
    if (renaming >= 0 || demo.classList.contains("away") || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key.length > 1 && !keys.has(e.key)) return;
    if (e.key === "Escape") {
      e.preventDefault();
      if (acting >= 0) { acting = -1; return render(); }
      return hide();
    }
    if (e.key === "Tab" || e.key === "ContextMenu") {
      e.preventDefault();
      if (acting >= 0) { action = (action + (e.shiftKey ? 2 : 1)) % 3; return render(); }
      return more(selected);
    }
    if (acting >= 0) {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        action = Math.max(0, Math.min(2, action + (e.key === "ArrowRight" ? 1 : -1)));
        return render();
      }
      if (e.key === "Enter") { e.preventDefault(); return act(action); }
      acting = -1;
    }
    if (e.key === "ArrowDown") selected = Math.min(selected + 1, shown.length - 1);
    else if (e.key === "ArrowUp") selected = Math.max(selected - 1, 0);
    else if (e.key === "Enter") return start();
    else if (e.key === "Backspace") query = query.slice(0, -1);
    else if (e.key.length === 1) { query += e.key; selected = 0; }
    else return;
    e.preventDefault();
    render();
  });

  const hover = (button, text) => {
    button.addEventListener("mouseenter", () => { if (!foot.classList.contains("notice")) foot.textContent = text; });
    button.addEventListener("mouseleave", footer);
  };
  hover(help, "Copy a prompt that explains Hanami to your AI");
  hover(add, "Add a game by picking its program");
  add.addEventListener("click", (e) => {
    e.stopPropagation();
    say("In the app, + opens the file picker to add any game.", 3200);
  });
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
