(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const ui = {
    stream: $("#stream"), hud: $("#hud"), chips: $("#chips"), actionbar: $("#actionbar"),
    say: $("#say"), mic: $("#btn-mic"), sound: $("#btn-sound"), pill: $("#mode-pill"), engine: $("#engine"),
    side: $("#side"), scrim: $("#scrim"), toast: $("#toast"),
  };
  let ws = null, sid = null, game = null, target = null;
  let gmBubble = null, committed = "", partial = "", thinkingEl = null, youVoice = null;
  const seenLog = {};
  let engineMode = "connecting";
  let toolPending = false, toolTimer = null;
  const usedReplies = new Set();

  // ---------- keep the dock above the on-screen keyboard ----------
  const vv = window.visualViewport;
  function fitViewport() {
    const h = vv ? vv.height : window.innerHeight;
    document.documentElement.style.setProperty("--app-h", h + "px");
    $("#app").style.top = (vv ? vv.offsetTop : 0) + "px";
  }
  if (vv) { vv.addEventListener("resize", fitViewport); vv.addEventListener("scroll", fitViewport); }
  window.addEventListener("resize", fitViewport);
  fitViewport();

  // ---------- audio out (24 kHz PCM from the Live API) ----------
  let actx = null, gain = null, playHead = 0, sources = [];
  let soundOn = localStorage.getItem("sound") !== "off";
  ui.sound.setAttribute("aria-pressed", String(soundOn));
  function ensureAudio() {
    if (!actx) {
      actx = new (window.AudioContext || window.webkitAudioContext)();
      gain = actx.createGain();
      gain.connect(actx.destination);
      gain.gain.value = soundOn ? 1 : 0;
    }
    if (actx.state === "suspended") actx.resume();
  }
  function playPcm(buf) {
    if (!actx || !soundOn) return;
    const pcm = new Int16Array(buf);
    const audio = actx.createBuffer(1, pcm.length, 24000);
    const ch = audio.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 32768;
    const src = actx.createBufferSource();
    src.buffer = audio;
    src.connect(gain);
    playHead = Math.max(playHead, actx.currentTime + 0.03);
    src.start(playHead);
    playHead += audio.duration;
    sources.push(src);
    src.onended = () => { sources = sources.filter((s) => s !== src); };
  }
  function stopAudio() { sources.forEach((s) => { try { s.stop(); } catch (e) {} }); sources = []; playHead = 0; }
  ui.sound.addEventListener("click", () => {
    soundOn = !soundOn;
    localStorage.setItem("sound", soundOn ? "on" : "off");
    ui.sound.setAttribute("aria-pressed", String(soundOn));
    ensureAudio();
    gain.gain.value = soundOn ? 1 : 0;
    if (!soundOn) stopAudio();
  });

  // ---------- mic in (16 kHz PCM to the Live API) ----------
  let micStream = null, micCtx = null, micNode = null;
  const WORKLET = `class Cap extends AudioWorkletProcessor{process(i){const c=i[0]&&i[0][0];if(c)this.port.postMessage(c.slice(0));return true}}registerProcessor('cap',Cap)`;
  async function startMic() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.AudioWorkletNode) {
      toast("Voice input isn't supported in this browser. Type instead.");
      return;
    }
    if (engineMode !== "live") { toast("Voice needs the live Game Master, which isn't connected right now."); return; }
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    } catch (e) { toast("Microphone permission was refused."); return; }
    micCtx = new (window.AudioContext || window.webkitAudioContext)();
    const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
    await micCtx.audioWorklet.addModule(url);
    const srcNode = micCtx.createMediaStreamSource(micStream);
    micNode = new AudioWorkletNode(micCtx, "cap");
    const ratio = micCtx.sampleRate / 16000;
    let pending = [];
    let pendingLen = 0;
    micNode.port.onmessage = (e) => {
      const input = e.data;
      const outLen = Math.floor(input.length / ratio);
      const out = new Int16Array(outLen);
      for (let i = 0; i < outLen; i++) {
        const s = Math.max(-1, Math.min(1, input[Math.floor(i * ratio)]));
        out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      pending.push(out); pendingLen += outLen;
      if (pendingLen >= 1600 && ws && ws.readyState === 1) {  // ~100 ms chunks
        const merged = new Int16Array(pendingLen);
        let o = 0; pending.forEach((p) => { merged.set(p, o); o += p.length; });
        ws.send(merged.buffer);
        pending = []; pendingLen = 0;
      }
    };
    srcNode.connect(micNode);
    ui.mic.setAttribute("aria-pressed", "true");
    stopAudio();
  }
  function stopMic() {
    if (micStream) micStream.getTracks().forEach((t) => t.stop());
    if (micCtx) micCtx.close();
    micStream = micCtx = micNode = null;
    ui.mic.setAttribute("aria-pressed", "false");
  }
  ui.mic.addEventListener("click", () => { ensureAudio(); micStream ? stopMic() : startMic(); });

  // ---------- stream rendering ----------
  function scrollDown() { requestAnimationFrame(() => { ui.stream.scrollTop = ui.stream.scrollHeight; }); }
  function add(el) { if (thinkingEl && thinkingEl.parentNode) ui.stream.insertBefore(el, thinkingEl); else ui.stream.appendChild(el); scrollDown(); return el; }
  function sys(text, level = "") { const d = document.createElement("div"); d.className = `msg sys ${level}`; d.textContent = text; add(d); }
  function you(text, voice = false) {
    const d = document.createElement("div"); d.className = "msg you" + (voice ? " voice" : "");
    d.innerHTML = `<span>${esc(text)}</span>`; return add(d);
  }
  function thinking(label) {
    if (!thinkingEl) { thinkingEl = document.createElement("div"); thinkingEl.className = "thinking"; ui.stream.appendChild(thinkingEl); }
    thinkingEl.innerHTML = `<i></i><i></i><i></i><span>${esc(label)}</span>`; scrollDown();
  }
  function stopThinking() { clearTimeout(toolTimer); if (thinkingEl) thinkingEl.remove(); thinkingEl = null; }
  function gmText() {
    if (!gmBubble) {
      gmBubble = document.createElement("div");
      gmBubble.className = "msg gm streaming";
      gmBubble.innerHTML = `<span class="who">Game Master</span><p></p>`;
      add(gmBubble);
      committed = ""; partial = "";
    }
    $("p", gmBubble).textContent = (committed + partial).replace(/\s+/g, " ").trim();
    scrollDown();
  }
  function endGm() { if (gmBubble) gmBubble.classList.remove("streaming"); gmBubble = null; committed = ""; partial = ""; }

  const TOOL_WORDS = { move: "The way unfolds…", say_to_npc: "They consider your words…", talk_to: "Getting their attention…",
    combat_action: "Rolling dice…", attack: "Rolling dice…", skill_check: "Rolling dice…", look_around: "Looking around…", inspect: "Looking closer…" };

  // ---------- websocket ----------
  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/${sid}`);
    ws.binaryType = "arraybuffer";
    ws.onmessage = (ev) => {
      if (ev.data instanceof ArrayBuffer) { playPcm(ev.data); return; }
      const m = JSON.parse(ev.data);
      switch (m.type) {
        case "token": toolPending = false; stopThinking(); partial += m.text; gmText(); break;
        case "final": toolPending = false; stopThinking(); committed += (committed ? " " : "") + m.text; partial = ""; gmText(); break;
        case "turn_complete":
          // the Live API can close a turn right after a tool call, before the model speaks again
          if (toolPending && !gmBubble) { clearTimeout(toolTimer); toolTimer = setTimeout(stopThinking, 15000); break; }
          stopThinking(); endGm(); break;
        case "interrupted": stopAudio(); endGm(); break;
        case "tool": toolPending = true; endGm(); thinking(TOOL_WORDS[m.names[0]] || "The world shifts…"); break;
        case "state": render(m.state); break;
        case "you_said":
          if (!youVoice) youVoice = you(m.text, true); else $("span", youVoice).textContent += m.text;
          if (m.final) youVoice = null; break;
        case "engine": if (!m.lines.some((l) => /Round \d+\./.test(l))) m.lines.forEach((l) => logLine({ text: l, kind: "info" })); break;
        case "status":
          engineMode = m.engine;
          ui.engine.dataset.engine = m.engine;
          $("b", ui.engine).textContent = m.engine === "live" ? `live · ${m.model}` : `text · ${m.model}`;
          ui.mic.disabled = m.engine !== "live";
          break;
        case "notice": stopThinking(); sys(m.text, m.level); break;
      }
    };
    ws.onclose = () => {
      ui.engine.dataset.engine = ""; $("b", ui.engine).textContent = "offline";
      stopMic();
      setTimeout(() => { if (sid && (!ws || ws.readyState === 3)) connect(); }, 2500);
    };
  }
  function sendText(text) {
    text = text.trim();
    if (!text || !ws || ws.readyState !== 1) return;
    ensureAudio(); stopAudio(); endGm();
    you(text);
    ws.send(JSON.stringify({ type: "text", text }));
    thinking("…");
  }
  function sendAction(action, extra = {}) {
    if (!ws || ws.readyState !== 1) return;
    ensureAudio(); stopAudio(); endGm();
    ws.send(JSON.stringify({ type: "action", action, ...extra }));
  }

  // ---------- rendering state ----------
  function render(s) {
    const prevMode = game && game.mode;
    game = s;
    ui.pill.dataset.mode = s.mode;
    if (s.setting) { $("#brand-text").textContent = s.setting.name; document.title = `${s.setting.name} · AI Dungeon`; }
    ui.pill.textContent = { exploration: "Exploring", dialogue: "Talking", combat: "Fighting", dead: "Fallen" }[s.mode];
    renderCombatLog(s);
    renderHud(s);
    renderChips(s);
    renderActions(s);
    renderSheet(s);
    renderMap(s);
    renderJournal(s);
    if (prevMode === "combat" && s.mode !== "combat" && s.combat && s.combat.outcome) resultCard(s.combat);
    if (s.mode === "dead" && prevMode !== "dead" && !(s.combat && s.combat.outcome)) resultCard({ outcome: "defeat" });
  }

  function bar(cur, max, cls = "") {
    const pct = max ? Math.max(0, Math.min(100, (cur / max) * 100)) : 0;
    return `<div class="bar ${cls}"><i style="width:${pct}%"></i></div>`;
  }
  function tags(list) { return list && list.length ? `<span class="status-tags">${list.map((t) => `<span class="tag ${t.name}">${t.name}</span>`).join("")}</span>` : ""; }

  function renderHud(s) {
    if (s.mode === "combat" && s.combat) {
      const cb = s.combat;
      const alive = cb.order.filter((id) => id !== "player" && cb.combatants[id].hp > 0);
      if (!target || !alive.includes(target)) target = alive[0] || null;
      const turnId = cb.order[cb.turn];
      const rows = cb.order.map((id) => {
        const c = cb.combatants[id];
        const mine = id === "player";
        const cls = ["bar-row", mine ? "player" : "enemy", id === target ? "target" : "", c.hp <= 0 ? "down" : "", id === turnId ? "turn" : ""].join(" ");
        return `<button type="button" class="${cls}" data-id="${id}" ${mine ? "disabled" : ""} aria-label="${esc(c.name)} ${c.hp} of ${c.max_hp} HP${mine ? "" : ", tap to target"}">
          <span class="bar-name">${esc(c.name)}<small>AC ${c.ac}${mine ? "" : id === target ? " · target" : ""}${tags(c.status)}</small></span>
          ${bar(c.hp, c.max_hp, mine ? "player" : "")}<span class="bar-num">${c.hp}/${c.max_hp}</span></button>`;
      });
      ui.hud.innerHTML = `<div class="bars">${rows.join("")}</div><div class="hud-meta"><span>Round ${cb.round}</span><span>Tap an enemy to target it</span></div>`;
      $$(".bar-row.enemy", ui.hud).forEach((b) => b.addEventListener("click", () => { target = b.dataset.id; renderHud(game); }));
      ui.hud.hidden = false;
    } else if (s.mode === "dialogue" && s.dialogue) {
      const d = s.dialogue;
      ui.hud.innerHTML = `<div class="npc-card">${portrait(d.name, d.attitude)}
        <div><div class="npc-name">${esc(d.name)}</div><div class="npc-role">${esc(d.role)}</div>
        <div class="meter"><span>${esc(d.attitude)}</span>${bar(d.disposition, 100)}<span>${d.disposition}</span></div></div>
        <div class="npc-side"><span class="mood">${esc(d.mood || "")}</span><button type="button" class="mini" id="btn-leave">Leave</button></div></div>`;
      $("#btn-leave", ui.hud).addEventListener("click", () => sendAction("end_conversation"));
      const meter = { friendly: "#7fae6b", warm: "#b9b062", wary: "#d8b765", unfriendly: "#e0803a", hostile: "#c4473b" }[d.attitude];
      $(".meter .bar > i", ui.hud).style.setProperty("--meter", meter || "#d8b765");
      ui.hud.hidden = false;
    } else if (s.mode === "exploration") {
      const loc = s.location;
      const people = loc.npcs.map((n) => n.name).join(", ");
      ui.hud.innerHTML = `<div class="loc-strip"><b>${esc(loc.name)}</b>${people ? `<span>Here: ${esc(people)}</span>` : ""}</div>`;
      ui.hud.hidden = false;
    } else {
      ui.hud.hidden = true; ui.hud.innerHTML = "";
    }
  }

  function portrait(name, attitude) {
    const initials = name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
    let h = 0; for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
    const ring = { friendly: "#7fae6b", warm: "#b9b062", wary: "#d8b765", unfriendly: "#e0803a", hostile: "#c4473b" }[attitude] || "#d8b765";
    return `<svg class="portrait" viewBox="0 0 52 52" aria-hidden="true">
      <defs><linearGradient id="pg${h}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="hsl(${h},28%,30%)"/><stop offset="1" stop-color="hsl(${(h + 40) % 360},30%,14%)"/></linearGradient></defs>
      <circle cx="26" cy="26" r="24" fill="url(#pg${h})" stroke="${ring}" stroke-width="2.5"/>
      <text x="26" y="32" text-anchor="middle" font-family="Cormorant Garamond, Georgia, serif" font-weight="700" font-size="19" fill="#f1e6d6">${esc(initials)}</text></svg>`;
  }

  function chip(label, onClick, cls = "") {
    const b = document.createElement("button");
    b.type = "button"; b.className = `chip ${cls}`; b.innerHTML = label;
    b.addEventListener("click", onClick);
    ui.chips.appendChild(b);
  }
  function renderChips(s) {
    ui.chips.innerHTML = "";
    ui.chips.scrollLeft = 0;
    if (s.mode === "dialogue" && s.dialogue) {
      (s.dialogue.suggested || []).filter((r) => !usedReplies.has(r)).forEach((r) => chip(esc(r), () => { usedReplies.add(r); sendText(r); renderChips(game); }, "reply"));
      if (!(s.dialogue.suggested || []).length) chip("Ask about the village", () => sendText("What's been happening around here?"), "reply");
      (s.dialogue.sells || []).slice(0, 4).forEach((it) => chip(`Buy ${esc(it.name)} <b>${it.price}g</b>`, () => sendAction("trade", { trade: "buy", item: it.id })));
    } else if (s.mode === "exploration") {
      const loc = s.location;
      loc.npcs.forEach((n) => chip(`Talk to ${esc(n.name.split(" ")[0])}`, () => sendText(`I go and talk to ${n.name}.`)));
      loc.exits.forEach((e) => chip(`${esc(cap(e.direction))} · ${esc(e.name)}`, () => sendText(`I head ${e.direction}${e.to ? " to " + e.name : ""}.`)));
      loc.items.forEach((i) => chip(`Take ${esc(i.name)}`, () => sendAction("take", { item: i.id })));
      loc.features.slice(0, 2).forEach((f) => chip(`Inspect ${esc(f)}`, () => sendText(`I take a closer look at the ${f}.`), "muted"));
      if (loc.rest) chip("Rest (5g)", () => sendAction("rest"), "muted");
    } else if (s.mode === "dead") {
      chip("Load a save", openMenu); chip("New game", newGame, "muted");
    }
  }
  const cap = (t) => t.charAt(0).toUpperCase() + t.slice(1);

  function renderActions(s) {
    const show = s.mode === "combat" && s.combat && !s.combat.outcome;
    ui.actionbar.hidden = !show;
    if (!show) { ui.actionbar.innerHTML = ""; return; }
    const ab = Object.fromEntries(s.player.abilities.map((a) => [a.id, a]));
    const potions = s.player.inventory.filter((i) => i.kind === "consumable").reduce((n, i) => n + i.qty, 0);
    const btn = (id, label, sub, cls = "", disabled = false) => `<button type="button" class="act ${cls}" data-act="${id}" ${disabled ? "disabled" : ""}>${label}<small>${sub}</small></button>`;
    ui.actionbar.innerHTML =
      btn("attack", "Attack", "weapon " + s.player.damage, "primary") +
      btn("power_strike", "Power Strike", `${ab.power_strike.uses} left`, "", !ab.power_strike.uses) +
      btn("defend", "Defend", "+2 AC") +
      btn("item", "Item", `${potions} usable`, "", !potions) +
      btn("second_wind", "Second Wind", `${ab.second_wind.uses} left`, "", !ab.second_wind.uses) +
      btn("flee", "Flee", "dex check");
    $$(".act", ui.actionbar).forEach((b) => b.addEventListener("click", () => {
      const a = b.dataset.act;
      if (a === "item") return openItems();
      $$(".act", ui.actionbar).forEach((x) => (x.disabled = true));
      sendAction(a, { target });
      thinking("Rolling dice…");
    }));
  }

  function renderCombatLog(s) {
    const cb = s.combat;
    if (!cb) return;
    const seen = seenLog[cb.id] || 0;
    cb.log.slice(seen).forEach(logLine);
    seenLog[cb.id] = cb.log.length;
  }
  function logLine(e) {
    const d = document.createElement("div");
    d.className = `log-line ${e.kind || ""} ${e.actor === "player" ? "mine" : ""}`;
    d.textContent = e.text;
    add(d);
  }
  function resultCard(cb) {
    const d = document.createElement("div");
    if (cb.outcome === "victory") {
      const r = cb.rewards || { xp: 0, gold: 0, items: [] };
      d.className = "result-card";
      d.innerHTML = `<h4>Victory</h4><p>+${r.xp} XP · +${r.gold} gold${r.items.length ? " · " + r.items.length + " item" + (r.items.length > 1 ? "s" : "") : ""}</p><button class="btn ghost" type="button">Carry on</button>`;
    } else if (cb.outcome === "fled") {
      d.className = "result-card"; d.innerHTML = `<h4>You got away</h4><p>Catch your breath. Your wounds are still with you.</p><button class="btn ghost" type="button">Carry on</button>`;
    } else {
      d.className = "result-card defeat"; d.innerHTML = `<h4>You have fallen</h4><p>Load a save to try again, or start over.</p><button class="btn" type="button">Load a save</button>`;
    }
    $("button", d).addEventListener("click", () => { if (cb.outcome === "defeat") openMenu(); else { sendAction("dismiss"); d.querySelector("button").remove(); } });
    add(d);
  }

  function renderSheet(s) {
    const p = s.player;
    const st = Object.entries(p.stats).map(([k, v]) => `<div><b>${v >= 0 ? "+" : ""}${v}</b><span>${k}</span></div>`).join("");
    const inv = p.inventory.map((i) => {
      const equipped = Object.values(p.equipped).includes(i.name);
      const usable = i.kind === "consumable" || ((i.kind === "weapon" || i.kind === "armour") && !equipped);
      const verb = i.kind === "consumable" ? "Use" : "Equip";
      return `<li><span class="nm">${esc(i.name)}${i.qty > 1 ? ` ×${i.qty}` : ""} ${equipped ? '<span class="eq">equipped</span>' : ""}<small>${esc(i.desc)}</small></span>
        ${usable ? `<button class="mini" data-use="${i.id}" type="button">${verb}</button>` : ""}</li>`;
    }).join("");
    const abil = p.abilities.map((a) => `<div class="ability"><span>${esc(a.name)}</span><span class="pips">${Array.from({ length: a.max_uses }, (_, i) => `<i class="${i < a.uses ? "on" : ""}"></i>`).join("")}</span></div>`).join("");
    $("#sheet").innerHTML = `<div class="sheet-top"><h3>${esc(p.name)}</h3><span class="lvl">Level ${p.level} ${esc(p.class)}</span></div>
      <div class="labelled"><span>HP</span>${bar(p.hp, p.max_hp, "player")}<span>${p.hp}/${p.max_hp}</span></div>
      <div class="labelled"><span>XP</span>${bar(p.xp, p.xp_next, "xp")}<span>${p.xp}/${p.xp_next}</span></div>
      ${p.status.length ? `<p>${tags(p.status)}</p>` : ""}
      <div class="kv"><div><b>${p.ac}</b><span>AC</span></div><div><b>+${p.attack}</b><span>Attack</span></div><div><b>${p.gold}</b><span>Gold</span></div></div>
      <div class="kv stats">${st}</div>
      <h4>Abilities</h4>${abil}
      <h4>Inventory</h4><ul class="inv">${inv || '<li class="empty">Empty pockets.</li>'}</ul>`;
    $$("[data-use]", $("#sheet")).forEach((b) => b.addEventListener("click", () => {
      sendAction(game.mode === "combat" ? "item" : "use_item", { item: b.dataset.use, target });
      closeDrawer();
    }));
  }

  function renderMap(s) {
    const nodes = Object.entries(s.map);
    if (!nodes.length) return;
    const xs = nodes.map(([, n]) => n.x), ys = nodes.map(([, n]) => n.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const cell = 92, pad = 56;
    const W = (maxX - minX) * cell + pad * 2, H = (maxY - minY) * cell + pad * 2;
    const pos = (n) => [(n.x - minX) * cell + pad, (n.y - minY) * cell + pad];
    let lines = "", dots = "";
    nodes.forEach(([id, n]) => n.links.forEach((to) => {
      if (!s.map[to] || id > to) return;
      const [x1, y1] = pos(n), [x2, y2] = pos(s.map[to]);
      lines += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#4a3b2e" stroke-width="2" stroke-dasharray="${n.visited && s.map[to].visited ? "0" : "4 4"}"/>`;
    }));
    nodes.forEach(([id, n]) => {
      const [x, y] = pos(n);
      const here = id === s.location.id;
      dots += `<g class="node" data-id="${id}" data-name="${esc(n.name)}">
        <circle cx="${x}" cy="${y}" r="${here ? 11 : 8}" fill="${here ? "#e0803a" : n.visited ? "#7a6450" : "#2a211b"}" stroke="${here ? "#f4c66b" : "#5a4838"}" stroke-width="2"/>
        <text x="${x}" y="${y + 26}" text-anchor="middle" font-size="11" fill="${here ? "#ece3d6" : n.visited ? "#a8998a" : "#6f6356"}" font-family="system-ui">${esc(n.name.length > 18 ? n.name.slice(0, 17) + "…" : n.name)}</text></g>`;
    });
    $("#map").innerHTML = `<svg viewBox="${-(Math.max(W, 320) - W) / 2} 0 ${Math.max(W, 320)} ${Math.max(H, 180)}" role="img" aria-label="Map">${lines}${dots}</svg>`;
    $("#loc-line").textContent = `You are at ${s.location.name}. Tap a neighbouring place to travel.`;
    $$(".node", $("#map")).forEach((g) => g.addEventListener("click", () => {
      if (g.dataset.id === s.location.id || game.mode === "combat") return;
      const ex = s.location.exits.find((e) => e.to === g.dataset.id);
      if (ex) { sendText(`I head ${ex.direction} to ${ex.name}.`); closeDrawer(); }
      else toast("That isn't next to you.");
    }));
  }

  function renderJournal(s) {
    const order = { ready: 0, active: 1, done: 2, failed: 3 };
    const quests = [...s.quests].sort((a, b) => order[a.status] - order[b.status]).map((q) =>
      `<div class="quest ${q.status}"><span class="st">${q.status === "ready" ? "claim reward" : q.status}</span><b>${esc(q.title)}</b><p>${esc(q.desc)}</p></div>`).join("");
    const entries = [...s.journal].reverse().map((e) => `<li><small>${esc(e.kind)}</small>${esc(e.text)}</li>`).join("");
    $("#journal").innerHTML = `<h3>Journal</h3><h4>Quests</h4>${quests || '<p class="empty">No quests yet. Someone around here might have work.</p>'}
      <h4>Notes</h4><ul class="entries">${entries || '<li class="empty">Nothing written yet.</li>'}</ul>`;
  }

  // ---------- drawer / modals ----------
  function openDrawer(tab) {
    if (tab) selectTab(tab);
    ui.side.classList.add("open"); ui.scrim.hidden = false;
  }
  function closeDrawer() { ui.side.classList.remove("open"); ui.scrim.hidden = true; }
  function selectTab(tab) {
    $$(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
    $$(".panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === tab));
  }
  selectTab("sheet");
  $$(".tabs button").forEach((b) => b.addEventListener("click", () => selectTab(b.dataset.tab)));
  $("#btn-drawer").addEventListener("click", () => openDrawer());
  $("#btn-close-drawer").addEventListener("click", closeDrawer);
  ui.scrim.addEventListener("click", closeDrawer);

  function openItems() {
    const list = game.player.inventory.filter((i) => i.kind === "consumable");
    $("#item-list").innerHTML = list.map((i) => `<button class="item-opt" type="button" data-item="${i.id}"><span>${esc(i.name)} ×${i.qty}<small>${esc(i.desc)}</small></span></button>`).join("") || '<p class="empty">Nothing usable.</p>';
    $$(".item-opt").forEach((b) => b.addEventListener("click", () => {
      $("#item-sheet").hidden = true; sendAction("item", { item: b.dataset.item, target }); thinking("Rolling dice…");
    }));
    $("#item-sheet").hidden = false;
  }
  $$("[data-close]").forEach((b) => b.addEventListener("click", () => { b.closest(".sheet-modal").hidden = true; }));
  $$(".sheet-modal").forEach((m) => m.addEventListener("click", (e) => { if (e.target === m) m.hidden = true; }));

  async function listSaves(el, onLoad) {
    const saves = await fetch("/api/saves").then((r) => r.json()).catch(() => []);
    el.innerHTML = saves.map((s) => `<button class="save-item" type="button" data-slot="${esc(s.slot)}"><span>${esc(s.slot)}<small>${esc(s.name)} · level ${s.level} · ${esc(s.location)}</small></span><span>Load</span></button>`).join("");
    $$(".save-item", el).forEach((b) => b.addEventListener("click", () => onLoad(b.dataset.slot)));
  }
  function openMenu() {
    $("#save-name").value = game ? game.player.name.toLowerCase().replace(/[^a-z0-9]+/g, "-") : "";
    listSaves($("#save-list"), loadSlot);
    $("#menu-sheet").hidden = false;
  }
  $("#btn-menu").addEventListener("click", openMenu);
  $("#save-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const r = await fetch("/api/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sid, slot: $("#save-name").value || "autosave" }) });
    const j = await r.json();
    toast(r.ok ? `Saved as "${j.slot}".` : j.detail || "Couldn't save.");
    listSaves($("#save-list"), loadSlot);
  });
  $("#btn-new").addEventListener("click", newGame);

  function toast(text) {
    ui.toast.textContent = text; ui.toast.classList.add("show");
    clearTimeout(toast.t); toast.t = setTimeout(() => ui.toast.classList.remove("show"), 2800);
  }

  // ---------- starting ----------
  function reset() {
    if (ws) { ws.onclose = null; ws.close(); }
    ui.stream.innerHTML = ""; endGm(); stopThinking(); stopAudio(); stopMic();
    Object.keys(seenLog).forEach((k) => delete seenLog[k]);
    game = null; target = null;
  }
  async function begin(res) {
    const j = await res.json();
    if (!res.ok) { toast(j.detail || "Something went wrong."); return; }
    if (j.notice) setTimeout(() => toast(j.notice), 400);
    reset();
    sid = j.session_id;
    localStorage.setItem("sid", sid);
    $("#title").hidden = true; $("#menu-sheet").hidden = true;
    render(j.state);
    thinking("The Game Master is gathering their thoughts…");
    connect();
  }
  async function loadSlot(slot) {
    ensureAudio();
    begin(await fetch("/api/load", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ slot }) }));
  }
  function newGame() { reset(); sid = null; localStorage.removeItem("sid"); $("#menu-sheet").hidden = true; $("#title").hidden = false; listSaves($("#title-saves"), loadSlot); }
  const premiseBox = $("#premise");
  const premiseChips = [...document.querySelectorAll("#premise-chips .chip")];
  function markPremise() {
    const v = premiseBox.value.trim();
    premiseChips.forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.premise === v)));
  }
  premiseChips.forEach((c) => c.addEventListener("click", () => { premiseBox.value = c.dataset.premise; markPremise(); }));
  premiseBox.addEventListener("input", markPremise);
  markPremise();
  $("#start-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    ensureAudio();
    const btn = $("#btn-begin");
    const premise = premiseBox.value.trim();
    btn.disabled = true;
    btn.textContent = premise ? "Building your world…" : "Begin";
    try {
      const res = await fetch("/api/new", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: $("#hero-name").value, premise }) });
      await begin(res);
    } catch (err) {
      toast("Couldn't reach the server.");
    } finally {
      btn.disabled = false; btn.textContent = "Begin";
    }
  });
  $("#inputbar").addEventListener("submit", (e) => { e.preventDefault(); sendText(ui.say.value); ui.say.value = ""; });
  ui.say.addEventListener("focus", () => setTimeout(() => { fitViewport(); scrollDown(); }, 250));

  // resume a game after a reload if the server still has it
  (async () => {
    listSaves($("#title-saves"), loadSlot);
    const saved = localStorage.getItem("sid");
    if (!saved) return;
    const r = await fetch(`/api/state/${saved}`);
    if (!r.ok) return;
    sid = saved; $("#title").hidden = true; render(await r.json()); connect();
  })();
})();
