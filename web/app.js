(() => {
  const $ = (id) => document.getElementById(id);
  const els = {
    grid: $("grid"), messages: $("messages"), composer: $("composer"), input: $("input"), send: $("send"),
    suggest: $("suggest"), toolbar: $("toolbar"), chips: $("genreChips"), sort: $("sortSelect"),
    subtitle: $("subtitle"), title: $("resultsTitle"), profile: $("profile"), toast: $("toast"),
    tabForYou: $("tabForYou"), tabAll: $("tabAll"), chat: $("chatPanel"),
  };
  const EXAMPLES = ["Chill study session", "High-energy gym", "Rainy night, feeling nostalgic", "Upbeat latin party"];
  const state = { recs: [], catalog: null, tab: "foryou", genre: null, sort: "match", busy: false };

  // ---------- helpers ----------
  const h = (tag, props = {}, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") el.className = v; else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v); else el.setAttribute(k, v);
    }
    kids.flat().forEach((c) => c != null && el.append(c));
    return el;
  };
  const LABELS = { edm: "EDM", "r&b": "R&B", lofi: "Lo-fi", "hip-hop": "Hip-hop" };
  const cap = (s) => LABELS[s] || s.charAt(0).toUpperCase() + s.slice(1);
  const toast = (msg) => {
    els.toast.textContent = msg; els.toast.hidden = false;
    clearTimeout(toast.t); toast.t = setTimeout(() => (els.toast.hidden = true), 4000);
  };

  // ---------- song cards ----------
  function card(song, rank) {
    const meter = (label, pct, cls = "") => h("div", { class: "meter" },
      h("span", { text: label }), h("div", { class: `bar ${cls}` }, h("i", { style: `width:${pct}%` })), h("b", { text: `${pct}%` }));
    const why = (song.why || []).map((w) => h("li", { text: w }));
    const el = h("button", { class: "card", type: "button", "aria-expanded": "false",
      onclick: () => el.setAttribute("aria-expanded", el.getAttribute("aria-expanded") === "true" ? "false" : "true") },
      h("div", { class: "card-top" },
        rank ? h("div", { class: "rank", text: rank }) : null,
        h("div", {}, h("div", { class: "title", text: song.title }), h("div", { class: "artist", text: song.artist }))),
      song.reason ? h("div", { class: "reason" }, h("b", { text: "Why this song" }), h("span", { text: song.reason })) : null,
      h("div", { class: "pills" }, h("span", { class: "pill", text: cap(song.genre) }), h("span", { class: "pill", text: cap(song.mood) }),
        song.instrumental ? h("span", { class: "pill", text: "Instrumental" }) : null),
      song.match != null ? meter("Match", song.match) : null,
      meter("Energy", Math.round(song.energy * 100), "energy"),
      h("div", { class: "details" },
        h("div", { class: "meta" }, h("span", { text: `${song.tempo} BPM` }), h("span", { text: `${song.decade}s` }),
          h("span", { text: song.explicit ? "Explicit" : "Clean" })),
        song.tags.length ? h("div", { text: `Vibes: ${song.tags.join(", ")}` }) : null,
        why.length ? h("div", {}, h("b", { text: "Score breakdown" }), h("ul", {}, why)) : null));
    return el;
  }

  function visibleSongs() {
    let list = state.tab === "foryou" ? state.recs : (state.catalog || []);
    if (state.genre) list = list.filter((s) => s.genre === state.genre);
    const by = {
      match: (a, b) => (b.match ?? 0) - (a.match ?? 0), "energy-desc": (a, b) => b.energy - a.energy,
      "energy-asc": (a, b) => a.energy - b.energy, title: (a, b) => a.title.localeCompare(b.title),
    }[state.sort];
    if (state.tab === "all" && state.sort === "match") return [...list]; // "Default" = catalog order
    return [...list].sort(by);
  }

  function render() {
    const forYou = state.tab === "foryou";
    els.title.textContent = forYou ? "Recommended for you" : "Browse all songs";
    els.tabForYou.classList.toggle("active", forYou); els.tabForYou.setAttribute("aria-selected", forYou);
    els.tabAll.classList.toggle("active", !forYou); els.tabAll.setAttribute("aria-selected", !forYou);
    const source = forYou ? state.recs : (state.catalog || []);
    els.toolbar.hidden = source.length === 0;
    els.sort.querySelector('[value="match"]').textContent = forYou ? "Best match" : "Default";

    const genres = [...new Set(source.map((s) => s.genre))].sort();
    if (state.genre && !genres.includes(state.genre)) state.genre = null;
    els.chips.replaceChildren(...["All", ...genres].map((g) => {
      const active = (g === "All" && !state.genre) || g === state.genre;
      return h("button", { class: `chip${active ? " active" : ""}`, type: "button", "aria-pressed": active,
        text: g === "All" ? g : cap(g), onclick: () => { state.genre = g === "All" ? null : g; render(); } });
    }));

    const list = visibleSongs();
    if (!list.length) {
      els.grid.replaceChildren(h("div", { class: "empty", text: forYou
        ? "No recommendations yet. Describe your mood in the chat and songs will show up here." : "No songs match this filter." }));
      return;
    }
    els.grid.replaceChildren(...list.map((s, i) => card(s, forYou && !state.genre && state.sort === "match" ? i + 1 : null)));
  }

  function showProfile(profile) {
    const parts = Object.entries(profile || {}).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`);
    els.profile.hidden = !parts.length;
    els.profile.replaceChildren(h("span", { text: "Understood as" }), ...parts.map((p) => h("span", { class: "pill", text: p })));
  }

  // ---------- chat ----------
  function bubble(kind, content) {
    const el = h("div", { class: `msg ${kind}` }, content);
    els.messages.append(el); els.messages.scrollTop = els.messages.scrollHeight; return el;
  }
  // Render the model's text safely (no innerHTML): strip [song:12] citations, turn bullets into a list.
  function renderReply(text) {
    const lines = text.replace(/\s*\[(?:song|genre|mood):[^\]]+\]/g, "").split("\n").map((l) => l.trim()).filter(Boolean);
    const frag = document.createDocumentFragment(); let ul = null;
    for (const line of lines) {
      const m = line.match(/^(?:[*\-•]|\d+[.)])\s+(.*)$/);
      const clean = (m ? m[1] : line).replace(/\*\*/g, "");
      if (m) { ul = ul || frag.appendChild(h("ul")); ul.append(h("li", { text: clean })); }
      else { ul = null; frag.append(h("div", { text: clean })); }
    }
    return frag;
  }

  async function ask(message) {
    message = message.trim();
    if (!message || state.busy) return;
    state.busy = true; els.send.disabled = true; els.input.value = "";
    bubble("user", message);
    const typing = bubble("bot", h("span", { class: "typing" }, h("i"), h("i"), h("i")));
    els.grid.replaceChildren(...Array.from({ length: 6 }, () => h("div", { class: "skeleton" })));
    try {
      const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Request failed");
      typing.remove();
      const note = { "llm-grounded": "AI-written, grounded in song data", "llm-partial": "AI-written, with some rule-based notes" }[data.explain_source] || "Rule-based explanation";
      bubble("bot", data.songs.length ? [
        h("div", { text: `Here ${data.songs.length === 1 ? "is 1 pick" : `are ${data.songs.length} picks`} for you:` }),
        h("ul", {}, data.songs.map((s) => h("li", {}, h("strong", { text: s.title }), ` - ${s.reason}`))),
        h("span", { class: "src", text: note })] : renderReply(data.reply));
      state.recs = data.songs; state.tab = "foryou"; state.genre = null; state.sort = "match"; els.sort.value = "match";
      els.subtitle.textContent = data.songs.length ? `${data.songs.length} songs for "${message}"` : "Try a different description.";
      showProfile(data.profile); render();
      if (innerWidth <= 860 && data.songs.length) setChat(false);
    } catch (err) {
      typing.remove();
      bubble("bot", "Sorry, I couldn't get recommendations just now. Please try again.");
      toast(err.message); render();
    } finally { state.busy = false; els.send.disabled = false; els.input.focus(); }
  }

  function setChat(open) {
    els.chat.classList.toggle("open", open); $("chatToggle").setAttribute("aria-expanded", open);
    if (open) els.input.focus();
  }

  // ---------- wiring ----------
  els.composer.addEventListener("submit", (e) => { e.preventDefault(); ask(els.input.value); });
  els.sort.addEventListener("change", () => { state.sort = els.sort.value; render(); });
  els.tabForYou.addEventListener("click", () => { state.tab = "foryou"; state.genre = null; render(); });
  els.tabAll.addEventListener("click", async () => {
    state.tab = "all"; state.genre = null;
    if (!state.catalog) {
      try { state.catalog = (await (await fetch("/api/songs")).json()).songs; } catch { toast("Couldn't load the catalog."); }
    }
    render();
  });
  $("chatToggle").addEventListener("click", () => setChat(true));
  $("chatClose").addEventListener("click", () => setChat(false));
  EXAMPLES.forEach((t) => els.suggest.append(h("button", { class: "chip", type: "button", text: t, onclick: () => ask(t) })));

  bubble("bot", "Hi! Tell me how you're feeling or what you're doing, and I'll suggest songs. Try one of the ideas below.");
  render();
})();
