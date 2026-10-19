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

  // if the passcode cookie has gone, any API call says 401: reload to get the passcode page
  const rawFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const r = await rawFetch(...args);
    if (r.status === 401 && String(args[0]).startsWith("/api/") && args[0] !== "/api/login") location.reload();
    return r;
  };
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
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
      fetch("/api/saves").catch(() => {});  // reloads to the passcode page if the cookie has gone
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
    const before = game;
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
    renderObjective(s);
    if (before) feedback(before, s);
    if (prevMode === "combat" && s.mode !== "combat" && s.combat && s.combat.outcome) resultCard(s.combat);
    if (s.mode === "dead" && prevMode !== "dead" && !(s.combat && s.combat.outcome)) resultCard({ outcome: "defeat" });
  }

  function bar(cur, max, cls = "") {
    const pct = max ? Math.max(0, Math.min(100, (cur / max) * 100)) : 0;
    return `<div class="bar ${cls}"><i style="width:${pct}%"></i></div>`;
  }
  // "Old Mariner Harl" -> "Harl", "Light-Warden Sunder-Salt" -> "Sunder-Salt", "Maren Holt" -> "Maren"
  const TITLES = new Set(["the", "old", "young", "brother", "sister", "father", "mother", "captain", "lady", "lord", "sir",
    "dame", "master", "mistress", "doctor", "dr", "elder", "auntie", "uncle", "mariner", "chaplain", "warden", "keeper",
    "sergeant", "abbot", "abbess", "prior", "cantor", "deacon", "overseer", "foreman", "matron", "saint", "madam"]);
  function shortName(name) {
    const words = name.split(/\s+/);
    const isTitle = (w) => TITLES.has(w.toLowerCase().split("-").pop().replace(/[^a-z]/g, ""));
    return words.find((w) => !isTitle(w)) || words[0];
  }
  function tags(list) { return list && list.length ? `<span class="status-tags">${list.map((t) => `<span class="tag ${t.name}">${t.name}${t.amount ? " " + t.amount : ""}</span>`).join("")}</span>` : ""; }

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
          <span class="bar-name">${esc(cap(c.name))}<small>AC ${c.ac}${mine ? "" : id === target ? " · target" : ""}${tags(c.status)}</small></span>
          ${bar(c.hp, c.max_hp, mine ? "player" : "")}<span class="bar-num">${c.hp}/${c.max_hp}</span></button>`;
      });
      const t = target && cb.combatants[target];
      const intel = [];
      if (t && t.abilities) intel.push(...t.abilities.map((a) => `<span class="sig" title="${esc(a.desc)}">${esc(a.name)}</span>`));
      if (t && t.weak && t.weak.length) intel.push(`<span class="weak">weak: ${esc(t.weak.join(", "))}</span>`);
      if (t && t.resist && t.resist.length) intel.push(`<span class="resist">resists: ${esc(t.resist.join(", "))}</span>`);
      ui.hud.innerHTML = `<div class="bars">${rows.join("")}</div><div class="hud-meta"><span>Round ${cb.round}</span>${intel.length ? `<span class="intel">${intel.join("")}</span>` : "<span>Tap an enemy to target it</span>"}</div>`;
      $$(".bar-row.enemy", ui.hud).forEach((b) => b.addEventListener("click", () => { target = b.dataset.id; renderHud(game); }));
      ui.hud.hidden = false;
    } else if (s.mode === "dialogue" && s.dialogue) {
      const d = s.dialogue;
      ui.hud.innerHTML = `<div class="npc-card">${portrait(d.name, d.attitude, d.known !== false)}
        <div><div class="npc-name">${esc(cap(d.name))}</div><div class="npc-role">${esc(d.role)}</div>
        <div class="meter"><span>${esc(d.attitude)}</span>${bar(d.disposition, 100)}<span>${d.disposition}</span></div></div>
        <div class="npc-side"><span class="mood">${esc(d.mood || "")}</span><button type="button" class="mini" id="btn-leave">Leave</button></div></div>`;
      $("#btn-leave", ui.hud).addEventListener("click", () => sendAction("end_conversation"));
      const meter = { friendly: "#7fae6b", warm: "#b9b062", wary: "#d8b765", unfriendly: "#e0803a", hostile: "#c4473b" }[d.attitude];
      $(".meter .bar > i", ui.hud).style.setProperty("--meter", meter || "#d8b765");
      ui.hud.hidden = false;
    } else if (s.mode === "exploration") {
      const loc = s.location;
      const people = loc.npcs.map((n) => n.name).join(", ");  // strangers come described, not named
      ui.hud.innerHTML = `<div class="loc-strip"><b>${esc(loc.name)}</b>${people ? `<span>Here: ${esc(people)}</span>` : ""}</div>`;
      ui.hud.hidden = false;
    } else {
      ui.hud.hidden = true; ui.hud.innerHTML = "";
    }
  }

  function portrait(name, attitude, known = true) {
    const initials = known ? name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase() : "?";
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
      (s.dialogue.sells || []).slice(0, 4).forEach((it) => chip(`Buy ${esc(it.name)} <b>${it.price} ${esc(money(s))}</b>`, () => sendAction("trade", { trade: "buy", item: it.id })));
    } else if (s.mode === "exploration") {
      const loc = s.location;
      loc.npcs.forEach((n) => chip(`Talk to ${esc(n.known === false ? n.name : shortName(n.name))}`, () => sendText(`I go and talk to ${n.name}.`)));
      loc.exits.forEach((e) => chip(`${esc(cap(e.direction))} · ${esc(e.name)}`, () => sendText(`I head ${e.direction}${e.to ? " to " + e.name : ""}.`)));
      loc.items.forEach((i) => chip(`Take ${esc(i.name)}`, () => sendAction("take", { item: i.id })));
      loc.features.slice(0, 2).forEach((f) => chip(`Inspect ${esc(f)}`, () => sendText(`I take a closer look at the ${f}.`), "muted"));
      if (loc.rest) chip(`Rest (5 ${esc(money(s))})`, () => sendAction("rest"), "muted");
    } else if (s.mode === "dead") {
      chip("Load a save", openMenu); chip("New game", newGame, "muted");
    }
  }
  const cap = (t) => t.charAt(0).toUpperCase() + t.slice(1);

  function renderActions(s) {
    const show = s.mode === "combat" && s.combat && !s.combat.outcome;
    ui.actionbar.hidden = !show;
    if (!show) { ui.actionbar.innerHTML = ""; return; }
    const usable = s.player.inventory.filter((i) => i.combat).reduce((n, i) => n + i.qty, 0);
    const btn = (id, label, sub, cls = "", disabled = false, extra = "") => `<button type="button" class="act ${cls}" data-act="${id}" ${extra} ${disabled ? "disabled" : ""}>${esc(label)}<small>${esc(sub)}</small></button>`;
    const abilities = s.player.abilities.map((a) => {
      const sub = a.id === "power_strike" ? `${a.uses} left` : a.id === "second_wind" ? `${a.uses} left · heal` : `${a.uses} left · ${a.desc.replace(/ \(.*\)$/, "")}`;
      const id = a.generated ? "ability" : a.id;
      return btn(id, a.name, sub, a.generated ? "gen" : "", !a.uses, a.generated ? `data-ability="${esc(a.id)}"` : "");
    });
    ui.actionbar.innerHTML =
      btn("attack", "Attack", `${s.player.damage} ${s.player.damage_type || ""}`.trim(), "primary") +
      btn("defend", "Defend", "+2 AC") +
      btn("item", "Item", `${usable} usable`, "", !usable) +
      abilities.join("") +
      btn("flee", "Flee", "dex check");
    ui.actionbar.classList.toggle("many", s.player.abilities.length > 2);
    $$(".act", ui.actionbar).forEach((b) => b.addEventListener("click", () => {
      const a = b.dataset.act;
      if (a === "item") return openItems();
      $$(".act", ui.actionbar).forEach((x) => (x.disabled = true));
      sendAction(a, b.dataset.ability ? { target, ability: b.dataset.ability } : { target });
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
      const names = r.names || [];
      d.innerHTML = `<h4>Victory</h4><p>+${r.xp} XP · +${r.gold} ${esc(money(game))}${r.items.length ? " · " + r.items.length + " item" + (r.items.length > 1 ? "s" : "") : ""}</p>${names.length ? `<ul class="loot">${names.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}<button class="btn ghost" type="button">Carry on</button>`;
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
    const equippedIds = Object.values(p.equipped_ids || {});
    const inv = p.inventory.map((i) => {
      const equipped = equippedIds.includes(i.id);
      const gear = ["weapon", "armour", "trinket"].includes(i.kind);
      const usable = i.kind === "consumable" || i.kind === "scroll" || (gear && !equipped);
      const verb = i.kind === "consumable" ? "Use" : i.kind === "scroll" ? "Study" : "Equip";
      const tier = i.tier ? `<span class="tier t${i.tier}">${"◆".repeat(i.tier)}</span>` : "";
      const line = [i.stats, i.desc].filter(Boolean).join(" · ");
      return `<li><span class="nm">${esc(i.name)}${i.qty > 1 ? ` ×${i.qty}` : ""} ${tier} ${equipped ? '<span class="eq">equipped</span>' : ""}<small>${esc(line)}</small></span>
        ${usable ? `<button class="mini" data-use="${i.id}" type="button">${verb}</button>` : ""}</li>`;
    }).join("");
    const abil = p.abilities.map((a) => `<div class="ability"><span>${esc(a.name)}<small>${esc(a.desc)}</small></span><span class="pips">${Array.from({ length: a.max_uses }, (_, i) => `<i class="${i < a.uses ? "on" : ""}"></i>`).join("")}</span></div>`).join("");
    $("#sheet").innerHTML = `<div class="sheet-top"><h3>${esc(p.name)}</h3><span class="lvl">Level ${p.level} ${esc(p.class)}</span></div>
      <div class="labelled"><span>HP</span>${bar(p.hp, p.max_hp, "player")}<span>${p.hp}/${p.max_hp}</span></div>
      <div class="labelled"><span>XP</span>${bar(p.xp, p.xp_next, "xp")}<span>${p.xp}/${p.xp_next}</span></div>
      ${p.status.length ? `<p>${tags(p.status)}</p>` : ""}
      ${p.resist && p.resist.length ? `<p class="resists">Resists ${esc(p.resist.join(", "))}</p>` : ""}
      <div class="kv"><div><b>${p.ac}</b><span>AC</span></div><div><b>+${p.attack}</b><span>Attack</span></div><div class="purse"><b>${p.gold}</b><span>${esc(money(s))}</span></div></div>
      <div class="kv stats">${st}</div>
      <h4>Abilities</h4>${abil}
      <h4>Inventory</h4><ul class="inv">${inv || '<li class="empty">Empty pockets.</li>'}</ul>`;
    $$("[data-use]", $("#sheet")).forEach((b) => b.addEventListener("click", () => {
      sendAction(game.mode === "combat" ? "item" : "use_item", { item: b.dataset.use, target });
      closeDrawer();
    }));
  }

  // ---------- map: drawn from what you've discovered, drag to pan, pinch or wheel to zoom ----------
  const CELL = 120;
  const RING = { friendly: "#7fae6b", warm: "#b9b062", wary: "#d8b765", unfriendly: "#e0803a", hostile: "#c4473b" };
  const mapState = { vb: null, here: null, sel: null, nodes: {}, aspect: 0.9 };
  function hue(name) { let h = 0; for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360; return h; }
  function face(p, x, y, r) {
    const h = hue(p.name);
    const txt = p.known === false ? "?" : p.name.split(/\s+/).filter((w) => !TITLES.has(w.toLowerCase())).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
    return `<g class="face"><circle cx="${x}" cy="${y}" r="${r}" fill="hsl(${h},28%,${p.known === false ? 18 : 28}%)" stroke="${RING[p.attitude] || "#d8b765"}" stroke-width="1.6"/>
      <text x="${x}" y="${y + r * 0.38}" text-anchor="middle" font-size="${r * 0.95}" font-weight="700" fill="#f1e6d6" font-family="Cormorant Garamond, Georgia, serif">${esc(txt)}</text></g>`;
  }
  const LOCK = (x, y) => `<g transform="translate(${x - 6} ${y - 7})"><rect x="1" y="6" width="10" height="8" rx="1.5" fill="#c9a36a"/><path d="M3 6V4a3 3 0 0 1 6 0v2" stroke="#c9a36a" stroke-width="1.6" fill="none"/></g>`;
  const CROWN = (x, y) => `<path transform="translate(${x - 7} ${y - 6})" d="M0 10L1.5 2l4 4L7 0l1.5 6 4-4L14 10z" fill="#e0675a"/>`;
  function renderMap(s, refit = false) {
    const nodes = Object.entries(s.map);
    if (!nodes.length) return;
    const pos = {};
    nodes.forEach(([id, n]) => { pos[id] = [n.x * CELL, n.y * CELL]; });
    mapState.nodes = pos;
    let lines = "", dots = "";
    nodes.forEach(([id, n]) => n.links.forEach((to) => {
      if (!s.map[to] || id > to) return;
      const [x1, y1] = pos[id], [x2, y2] = pos[to];
      const walked = n.visited && s.map[to].visited;
      lines += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="road ${walked ? "walked" : ""}"/>`;
    }));
    nodes.forEach(([id, n]) => {
      const [x, y] = pos[id];
      const here = id === s.location.id;
      const cls = ["node", here ? "here" : "", n.visited ? "seen" : "new", n.lair || n.boss ? "lair" : "", n.gate ? "gated" : "", id === mapState.sel ? "sel" : ""].join(" ");
      const label = n.name.length > 18 ? n.name.slice(0, 17) + "…" : n.name;
      const people = n.people || [];
      const shown = people.slice(0, 4);
      const faces = shown.map((p, i) => face(p, x + (i - (shown.length - 1) / 2) * 19, y - 33, 9)).join("") +
        (people.length > 4 ? `<text x="${x + 46}" y="${y - 29}" font-size="10" fill="#a8998a">+${people.length - 4}</text>` : "");
      dots += `<g class="${cls}" data-id="${id}">
        ${here ? `<circle class="here-ring" cx="${x}" cy="${y}" r="22"/>` : ""}
        <circle class="dot" cx="${x}" cy="${y}" r="${here ? 15 : 13}"/>
        ${n.gate ? LOCK(x, y) : n.lair || n.boss ? CROWN(x, y) : ""}
        ${n.unexplored ? `<g class="more"><circle cx="${x + 13}" cy="${y - 11}" r="6"/><text x="${x + 13}" y="${y - 8}" text-anchor="middle" font-size="9">?</text></g>` : ""}
        <text class="nm" x="${x}" y="${y + 30}" text-anchor="middle">${esc(label)}</text>
        ${n.gate ? `<text class="gate" x="${x}" y="${y + 42}" text-anchor="middle">level ${n.gate}</text>` : n.lair || n.boss ? `<text class="gate lair-t" x="${x}" y="${y + 42}" text-anchor="middle">lair</text>` : ""}
        ${faces}</g>`;
    });
    const box = $("#map");
    const r = box.getBoundingClientRect();
    if (r.width > 0) mapState.aspect = r.height / r.width;
    const moved = mapState.here !== s.location.id;
    if (!mapState.vb || moved || refit) {
      // fit everything if it fits at a readable size, otherwise centre on where you are
      const xs = nodes.map(([id]) => pos[id][0]), ys = nodes.map(([id]) => pos[id][1]);
      const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
      let w = Math.max(320, x1 - x0 + 190, (y1 - y0 + 150) / mapState.aspect);
      let [cx, cy] = [(x0 + x1) / 2, (y0 + y1) / 2 - 6];
      if (w > 640) { w = 520; [cx, cy] = pos[s.location.id] || [cx, cy]; }
      const h = w * mapState.aspect;
      mapState.vb = { x: cx - w / 2, y: cy - h / 2, w, h };
      mapState.here = s.location.id;
      if (moved) mapState.sel = null;
    }
    const vb = mapState.vb;
    box.innerHTML = `<svg viewBox="${vb.x} ${vb.y} ${vb.w} ${vb.h}" role="img" aria-label="Map of the places you've found">
      <defs><pattern id="grain" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M0 12h24M12 0v24" stroke="#241d17" stroke-width="1"/></pattern></defs>
      <rect x="-5000" y="-5000" width="10000" height="10000" fill="url(#grain)"/>${lines}${dots}</svg>`;
    mapInfo(s);
  }
  function mapInfo(s) {
    const id = mapState.sel || s.location.id;
    const n = s.map[id];
    if (!n) { $("#map-info").innerHTML = ""; return; }
    const here = id === s.location.id;
    const exit = s.location.exits.find((e) => e.to === id);
    const status = here ? "You are here" : n.gate ? `Locked until level ${n.gate}` : n.lair || n.boss ? "A lair. Something powerful waits here" : n.visited ? "Visited" : "Not visited yet";
    const people = (n.people || []).map((p) => `<li>${portrait(p.name, p.attitude, p.known !== false)}<span>${esc(cap(p.name))}<small>${esc(p.known === false ? "name not known" : p.role)}</small></span></li>`).join("");
    const go = !here && exit && s.mode !== "combat" ? `<button type="button" class="btn ghost" id="map-go">Travel ${esc(exit.direction)}</button>` : "";
    $("#map-info").innerHTML = `<div class="mi-head"><b>${esc(n.name)}</b><small>${esc(status)}</small>${go}</div>
      ${people ? `<ul class="mi-people">${people}</ul>` : n.visited ? `<p class="empty">Nobody you've seen here.</p>` : `<p class="empty">You haven't been there yet.</p>`}`;
    const b = $("#map-go");
    if (b) b.addEventListener("click", () => { sendText(`I head ${exit.direction} to ${exit.name}.`); closeDrawer(); });
  }
  (function mapGestures() {
    const box = $("#map");
    const pts = new Map();
    let start = null, pinch = null;
    const svgPoint = (cx, cy) => {
      const r = box.getBoundingClientRect(), vb = mapState.vb;
      return { x: vb.x + ((cx - r.left) / r.width) * vb.w, y: vb.y + ((cy - r.top) / r.height) * vb.h };
    };
    const apply = () => { const svg = $("svg", box); const vb = mapState.vb; if (svg) svg.setAttribute("viewBox", `${vb.x} ${vb.y} ${vb.w} ${vb.h}`); };
    function zoom(factor, cx, cy) {
      const vb = mapState.vb; if (!vb) return;
      const w = Math.max(160, Math.min(1400, vb.w * factor)), k = w / vb.w;
      const p = cx == null ? { x: vb.x + vb.w / 2, y: vb.y + vb.h / 2 } : svgPoint(cx, cy);
      mapState.vb = { x: p.x - (p.x - vb.x) * k, y: p.y - (p.y - vb.y) * k, w, h: vb.h * k };
      apply();
    }
    box.addEventListener("pointerdown", (e) => {
      box.setPointerCapture(e.pointerId);
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pts.size === 1) start = { x: e.clientX, y: e.clientY, vb: { ...mapState.vb }, moved: false };
      if (pts.size === 2) { const [a, b] = [...pts.values()]; pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), w: mapState.vb.w }; }
    });
    box.addEventListener("pointermove", (e) => {
      if (!pts.has(e.pointerId) || !mapState.vb) return;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      const r = box.getBoundingClientRect();
      if (pts.size === 2 && pinch) {
        const [a, b] = [...pts.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y) || 1;
        zoom((pinch.w * (pinch.d / d)) / mapState.vb.w, (a.x + b.x) / 2, (a.y + b.y) / 2);
        if (start) start.moved = true;
      } else if (start) {
        const dx = e.clientX - start.x, dy = e.clientY - start.y;
        if (Math.abs(dx) + Math.abs(dy) > 6) start.moved = true;
        if (start.moved) {
          mapState.vb = { ...mapState.vb, x: start.vb.x - (dx / r.width) * start.vb.w, y: start.vb.y - (dy / r.height) * start.vb.h };
          apply();
        }
      }
    });
    const up = (e) => {
      const tap = start && !start.moved && pts.size === 1;
      pts.delete(e.pointerId);
      if (pts.size < 2) pinch = null;
      if (tap && game) {
        // a tap picks the nearest place to show what you know about it
        const p = svgPoint(e.clientX, e.clientY);
        let best = null, bd = 30;
        Object.entries(mapState.nodes).forEach(([id, [x, y]]) => { const d = Math.hypot(x - p.x, y - p.y); if (d < bd) { bd = d; best = id; } });
        if (best) { mapState.sel = best; renderMap(game); }
      }
      if (!pts.size) start = null;
    };
    box.addEventListener("pointerup", up);
    box.addEventListener("pointercancel", up);
    box.addEventListener("wheel", (e) => { e.preventDefault(); zoom(e.deltaY > 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY); }, { passive: false });
    $$("[data-zoom]").forEach((b) => b.addEventListener("click", () => {
      if (b.dataset.zoom === "in") zoom(1 / 1.3);
      else if (b.dataset.zoom === "out") zoom(1.3);
      else if (game) { mapState.sel = null; renderMap(game, true); }
    }));
  })();

  function renderJournal(s) {
    const order = { ready: 0, active: 1, done: 2, failed: 3 };
    const quests = [...s.quests].sort((a, b) => order[a.status] - order[b.status] || (b.started || 0) - (a.started || 0)).map((q) => {
      const now = (q.objectives || []).findIndex((o) => !o.done);
      const steps = (q.objectives || []).map((o, i) => `<li class="${o.done ? "done" : i === now ? "now" : ""}"><i></i><span>${esc(o.text)}${o.count && !o.done ? ` <b>${o.have}/${o.need}</b>` : ""}</span></li>`).join("");
      return `<div class="quest ${q.status}"><span class="st">${q.status === "ready" ? "claim reward" : q.status}</span><b>${esc(q.title)}</b><p>${esc(q.desc)}</p>${steps ? `<ul class="steps">${steps}</ul>` : ""}</div>`;
    }).join("");
    const entries = [...s.journal].reverse().map((e) => `<li><small>${esc(e.kind)}</small>${esc(e.text)}</li>`).join("");
    $("#journal").innerHTML = `<h3>Journal</h3><h4>Quests</h4>${quests || '<p class="empty">No quests yet. Someone around here might have work.</p>'}
      <h4>Notes</h4><ul class="entries">${entries || '<li class="empty">Nothing written yet.</li>'}</ul>`;
  }

  function renderObjective(s) {
    const el = $("#objective");
    const o = s.objective;
    if (!o || s.mode === "dead" || s.mode === "combat") { el.hidden = true; return; }
    el.innerHTML = `<i class="obj-mark"></i><span class="obj-text">${esc(o.text)}${o.count ? ` <b>${o.have}/${o.need}</b>` : ""}</span><small>${esc(o.quest)}</small>`;
    el.hidden = false;
  }
  function tickObjective() {
    const el = $("#objective");
    el.classList.remove("ticked"); void el.offsetWidth; el.classList.add("ticked");
  }
  $("#objective").addEventListener("click", () => {
    if ($("#btn-drawer").offsetParent) openDrawer("journal");
    else $("#journal").scrollIntoView({ behavior: calm.matches ? "auto" : "smooth" });
  });

  // ---------- drawer / modals ----------
  function openDrawer(tab) {
    if (tab) selectTab(tab);
    ui.side.classList.add("open"); ui.scrim.hidden = false;
    unseen = 0; $("#bag-badge").hidden = true;
  }
  function closeDrawer() { ui.side.classList.remove("open"); ui.scrim.hidden = true; }
  function selectTab(tab) {
    $$(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
    $$(".panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === tab));
    if (tab === "map" && game) requestAnimationFrame(() => renderMap(game, true));
  }
  selectTab("sheet");
  $$(".tabs button").forEach((b) => b.addEventListener("click", () => selectTab(b.dataset.tab)));
  $("#btn-drawer").addEventListener("click", () => openDrawer());
  $("#btn-close-drawer").addEventListener("click", closeDrawer);
  ui.scrim.addEventListener("click", closeDrawer);

  function openItems() {
    const list = game.player.inventory.filter((i) => i.combat);
    $("#item-list").innerHTML = list.map((i) => `<button class="item-opt" type="button" data-item="${i.id}"><span>${esc(i.name)} ×${i.qty}<small>${esc(i.stats || i.desc)}</small></span></button>`).join("") || '<p class="empty">Nothing usable.</p>';
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

  const toasts = [];
  let toastBusy = false;
  function toast(text, kind = "") {
    if (toasts.some((t) => t[0] === text)) return;
    toasts.push([text, kind]);
    if (!toastBusy) nextToast();
  }
  function nextToast() {
    const t = toasts.shift();
    if (!t) { toastBusy = false; return; }
    toastBusy = true;
    ui.toast.innerHTML = t[1] ? `<i class="toast-mark ${t[1]}"></i>${esc(t[0])}` : esc(t[0]);
    ui.toast.className = `toast show ${t[1]}`;
    setTimeout(() => { ui.toast.classList.remove("show"); setTimeout(nextToast, 280); }, toasts.length ? 2000 : 2800);
  }

  // ---------- what changed: things flying into the bag, toasts for quests and names ----------
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)");
  const money = (s) => (s && s.setting && s.setting.currency) || "gold";
  const ICON = {
    gold: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="5"/>',
    xp: '<path d="M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.6 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z"/>',
    weapon: '<path d="M14.5 4H20v5.5L9 20.5 3.5 15z"/><path d="M5 13l6 6"/>',
    armour: '<path d="M12 3l7 3v5c0 5-3.5 8-7 10-3.5-2-7-5-7-10V6z"/>',
    trinket: '<circle cx="12" cy="14" r="5"/><path d="M9 4l3 5 3-5"/>',
    consumable: '<path d="M10 3h4M10.5 3v5L6 17a3 3 0 0 0 2.7 4h6.6A3 3 0 0 0 18 17l-4.5-9V3"/>',
    scroll: '<path d="M7 4h11v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2h11"/><path d="M7 4a2 2 0 0 0-2 2v10"/>',
    quest: '<path d="M6 3h9l3 3v15H6z"/><path d="M9 9h6M9 13h6M9 17h3"/>',
    item: '<path d="M5 8h14l-1 12H6z"/><path d="M9 8a3 3 0 0 1 6 0"/>',
  };
  function feedback(a, b) {
    const flights = [];
    const dg = b.player.gold - a.player.gold;
    if (dg) flights.push({ kind: "gold", gain: dg > 0, label: `${dg > 0 ? "+" : "−"}${Math.abs(dg)} ${money(b)}` });
    const dx = b.player.xp - a.player.xp;
    if (dx > 0) flights.push({ kind: "xp", gain: true, label: `+${dx} XP` });
    const had = Object.fromEntries(a.player.inventory.map((i) => [i.id, i]));
    const has = Object.fromEntries(b.player.inventory.map((i) => [i.id, i]));
    new Set([...Object.keys(had), ...Object.keys(has)]).forEach((id) => {
      const d = (has[id] ? has[id].qty : 0) - (had[id] ? had[id].qty : 0);
      if (!d) return;
      const it = has[id] || had[id];
      const kind = ICON[it.kind] ? it.kind : "item";
      flights.push({ kind, gain: d > 0, quest: it.kind === "quest", label: `${d > 0 ? "+" : "−"}${Math.abs(d) > 1 ? Math.abs(d) + " " : ""}${it.name}` });
    });
    flights.slice(0, 6).forEach((f, i) => setTimeout(() => fly(f), i * 240));

    const old = Object.fromEntries((a.quests || []).map((q) => [q.id, q]));
    (b.quests || []).forEach((q) => {
      const o = old[q.id];
      if (!o) return toast(`New quest: ${q.title}`, "quest");
      if (q.status === "done" && o.status !== "done") return toast(`Quest complete: ${q.title}`, "quest");
      (q.objectives || []).forEach((step, i) => {
        const was = (o.objectives || [])[i];
        if (step.done && was && !was.done) { toast(`Objective complete: ${step.text}`, "tick"); tickObjective(); }
      });
    });
    (b.learned || []).slice((a.learned || []).length).forEach((n) => toast(`You learned: ${n}`, "name"));
  }

  function bagTarget() {
    const b = $("#btn-drawer");
    if (b && b.offsetParent) return b;  // phones: the bag button
    return $("#sheet .inv") || $("#sheet");
  }
  function scenePoint() {
    const box = ui.stream.getBoundingClientRect();
    const last = $$(".msg.gm, .log-line, .result-card", ui.stream).pop();
    const r = last ? last.getBoundingClientRect() : box;
    const y = Math.max(box.top + 40, Math.min(box.bottom - 40, r.top + Math.min(r.height, 120) / 2));
    return { x: box.left + box.width / 2, y };
  }
  let unseen = 0;
  function pulse(t, gain) {
    if (gain && t.id === "btn-drawer") {
      unseen += 1;
      const badge = $("#bag-badge");
      badge.textContent = unseen > 9 ? "9+" : String(unseen);
      badge.hidden = false;
    }
    t.classList.remove("pulse", "pulse-loss");
    void t.offsetWidth;  // restart the animation
    t.classList.add(gain ? "pulse" : "pulse-loss");
  }
  function fly(f) {
    const t = bagTarget();
    if (!t) return;
    const tr = t.getBoundingClientRect();
    const bag = { x: tr.left + Math.min(tr.width, 44) / 2, y: tr.top + Math.min(tr.height, 44) / 2 };
    const scene = scenePoint();
    const el = document.createElement("div");
    el.className = `fly ${f.gain ? "gain" : "loss"} k-${f.kind}${f.quest ? " k-quest" : ""}`;
    el.innerHTML = `<b><svg viewBox="0 0 24 24">${ICON[f.kind] || ICON.item}</svg></b><span>${esc(f.label)}</span>`;
    el.setAttribute("aria-hidden", "true");
    document.body.appendChild(el);
    if (calm.matches || !el.animate) {
      // no flying about: the label just appears by the bag for a moment
      el.classList.add("still");
      el.style.transform = `translate(${Math.max(8, bag.x - 20)}px, ${bag.y + 26}px)`;
      setTimeout(() => el.remove(), 1700);
      pulse(t, f.gain);
      return;
    }
    const [p0, p1] = f.gain ? [scene, bag] : [bag, scene];
    const mid = { x: (p0.x + p1.x) / 2 + (f.gain ? 30 : -30), y: Math.max(70, Math.min(p0.y, p1.y) - 70) };
    const at = (p, sc) => `translate(${p.x}px, ${p.y}px) translate(-50%, -50%) scale(${sc})`;
    const frames = f.gain
      ? [{ transform: at(p0, 0.5), opacity: 0 }, { transform: at({ x: p0.x, y: p0.y - 26 }, 1.15), opacity: 1, offset: 0.2 },
         { transform: at({ x: p0.x, y: p0.y - 26 }, 1.15), opacity: 1, offset: 0.42 }, { transform: at(mid, 0.9), opacity: 1, offset: 0.72 },
         { transform: at(p1, 0.35), opacity: 0.2 }]
      : [{ transform: at(p0, 0.4), opacity: 0 }, { transform: at({ x: p0.x + 10, y: p0.y + 30 }, 1), opacity: 1, offset: 0.25 },
         { transform: at(mid, 1), opacity: 1, offset: 0.6 }, { transform: at({ x: p1.x, y: p1.y + 40 }, 0.9), opacity: 0 }];
    el.animate(frames, { duration: f.gain ? 1500 : 1400, easing: "cubic-bezier(.25,.7,.35,1)", fill: "forwards" })
      .onfinish = () => { el.remove(); if (f.gain) pulse(t, true); };
    if (!f.gain) pulse(t, false);
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
  // the button is disabled in the HTML so an early tap can't submit before this script is ready
  $("#btn-begin").disabled = false; $("#btn-begin").textContent = "Begin";
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
