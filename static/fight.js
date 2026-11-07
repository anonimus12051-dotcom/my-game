/* Бой на поляне: подключается из world.js */
const fight = {
  active: false, mobs: [], cards: {}, php: 0, pmax: 0, selected: null,
  readyAt: 0, healReadyAt: 0, done: false, gainXp: 0, gainSilver: 0,
  log: [], seen: new Set(), healBtns: []
};
let fightPoll = null;
let fightTick = null;
let fBusy = false;

function el(tag, css, text) {
  const e = document.createElement(tag);
  if (css) e.style.cssText = css;
  if (text !== undefined) e.textContent = text;
  return e;
}

const fightRoot = document.createElement("div");
fightRoot.className = "hidden";
fightRoot.style.cssText =
  "position:fixed;inset:0;z-index:45;background:#2f6b2f;overflow-y:auto;" +
  "padding:14px;box-sizing:border-box;color:#fff;font-family:sans-serif";
fightRoot.innerHTML =
  '<div style="font-size:18px;font-weight:bold;margin-bottom:10px">⚔️ Поляна с мобами</div>' +
  '<div>Твоё HP: <b id="fPhp"></b></div>' +
  '<div class="bar"><div class="fill" id="fPhpFill" style="background:#d64545"></div></div>' +
  '<div id="fMobs" style="display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin:14px 0"></div>' +
  '<div id="fLog" style="min-height:90px;font-size:13px;text-align:center;line-height:1.5;white-space:pre-line"></div>' +
  '<div id="fHeal" style="display:flex;flex-wrap:wrap;gap:8px;margin:10px 0"></div>' +
  '<div style="display:flex;gap:8px">' +
  '<button id="fAttack" style="flex:2;padding:14px;border:none;border-radius:8px;background:#f5c542;color:#111;font-weight:bold;font-size:16px">⚔️ Атаковать</button>' +
  '<button id="fFlee" style="flex:1;padding:14px;border:none;border-radius:8px;background:#444;color:#eee;font-weight:bold;font-size:16px">🏃 Бежать</button>' +
  '</div>';
document.body.appendChild(fightRoot);

function logLine(text) {
  fight.log.unshift(text);
  fight.log = fight.log.slice(0, 6);
  document.getElementById("fLog").textContent = fight.log.join("\n");
}

function isAlive(id) {
  return fight.mobs.some(m => m.id === id && m.hp > 0);
}

/* ---------- карточки мобов (создаются один раз) ---------- */
function buildMobs(mobs) {
  const box = document.getElementById("fMobs");
  box.innerHTML = "";
  fight.cards = {};
  mobs.forEach(m => {
    const card = el("div",
      "width:100px;padding:8px;border-radius:12px;text-align:center;" +
      "background:#272735;border:3px solid #444");
    const em = el("div", "font-size:44px", m.emoji);
    const nm = el("div", "font-size:12px", m.name);
    const bar = el("div", "margin:6px 0 2px");
    bar.className = "bar";
    const fill = el("div", "background:#d64545;width:100%");
    fill.className = "fill";
    bar.appendChild(fill);
    const hp = el("div", "font-size:11px", "");
    card.appendChild(em);
    card.appendChild(nm);
    card.appendChild(bar);
    card.appendChild(hp);
    card.onclick = () => {
      if (isAlive(m.id)) { fight.selected = m.id; updateMobs(); }
    };
    fight.cards[m.id] = {card: card, em: em, fill: fill, hp: hp, emoji: m.emoji};
    box.appendChild(card);
  });
}

function updateMobs() {
  fight.mobs.forEach(m => {
    const c = fight.cards[m.id];
    if (!c) return;
    const dead = m.hp <= 0;
    c.em.textContent = dead ? "💀" : c.emoji;
    c.fill.style.width = Math.max(0, m.hp / m.max_hp * 100) + "%";
    c.hp.textContent = dead ? "побеждён" : Math.ceil(m.hp) + " / " + m.max_hp;
    c.card.style.opacity = dead ? "0.45" : "1";
    c.card.style.background = dead ? "#1f3f1f" : "#272735";
    c.card.style.borderColor =
      (fight.selected === m.id && !dead) ? "#f5c542" : "#444";
  });
}

function updatePlayer() {
  document.getElementById("fPhp").textContent =
    Math.ceil(fight.php) + " / " + fight.pmax;
  document.getElementById("fPhpFill").style.width =
    Math.min(100, fight.php / fight.pmax * 100) + "%";
}

/* ---------- лечение ---------- */
function renderHeal() {
  const box = document.getElementById("fHeal");
  box.innerHTML = "";
  fight.healBtns = [];

  const groups = {};
  inventory.filter(r => r.items.type === "heal").forEach(r => {
    const g = groups[r.items.id] ||
      (groups[r.items.id] = {row: r, name: r.items.name, count: 0, id: r.items.id});
    g.count += r.qty || 1;
  });

  const list = Object.values(groups);
  if (!list.length) {
    box.appendChild(el("div", "font-size:12px;opacity:.8",
      "Нет лечебных предметов. Их можно купить у торговца"));
    return;
  }

  list.forEach(g => {
    const info = itemCatalog[g.id];
    const label = "🩹 " + g.name + " x" + g.count +
                  (info && info.heal ? " (+" + info.heal + ")" : "");
    const btn = el("button",
      "flex:1;min-width:120px;padding:10px 6px;border:none;border-radius:8px;" +
      "background:#3a9d5d;color:#fff;font-weight:bold;font-size:13px", label);
    btn.onclick = () => useHeal(g.row.id);
    box.appendChild(btn);
    fight.healBtns.push({btn: btn, label: label});
  });
}

async function useHeal(invId) {
  if (fBusy) return;
  fBusy = true;
  try {
    const res = await call("/fight/heal", {init_data: tg.initData, inv_id: invId});
    if (res.dead) {
      onDeath(res);
    } else {
      applyView(res);
      logLine("🩹 " + res.healed.name + ": +" + res.healed.amount + " HP");
      showInventory(res.inventory);
      renderHeal();
    }
  } catch (e) {
    if (e.message === "Ты сейчас не здесь") closeFight();
    else logLine("⚠️ " + e.message);
  }
  fBusy = false;
}

/* ---------- обновление состояния ---------- */
function applyView(v) {
  const now = Date.now();

  (v.events || []).forEach(ev => {
    if (fight.seen.has(ev.id)) return;
    fight.seen.add(ev.id);
    if (!fight.active) return;
    logLine(ev.hit
      ? "💢 " + ev.mob + " ударил: -" + ev.dmg
      : "🌀 " + ev.mob + " промахнулся");
  });

  fight.php = v.php;
  fight.pmax = v.pmax;
  fight.done = v.done;
  fight.mobs = v.mobs;
  fight.readyAt = now + v.ready_in * 1000;
  fight.healReadyAt = now + v.heal_in * 1000;

  if (fight.selected === null || !isAlive(fight.selected)) {
    const a = fight.mobs.find(m => m.hp > 0);
    fight.selected = a ? a.id : null;
  }
  updatePlayer();
  updateMobs();
  tickFight();
}

function tickFight() {
  const now = Date.now();

  const atk = document.getElementById("fAttack");
  atk.classList.toggle("hidden", fight.done);
  atk.disabled = now < fight.readyAt || fight.selected === null;
  atk.style.opacity = atk.disabled ? "0.5" : "1";

  document.getElementById("fFlee").textContent =
    fight.done ? "🏠 На спавн" : "🏃 Бежать";

  const wait = Math.ceil((fight.healReadyAt - now) / 1000);
  fight.healBtns.forEach(h => {
    const off = wait > 0 || fight.php >= fight.pmax || fight.done;
    h.btn.disabled = off;
    h.btn.style.opacity = off ? "0.5" : "1";
    h.btn.textContent = h.label + (wait > 0 ? " (" + wait + ")" : "");
  });
}

function closeFight() {
  fight.active = false;
  clearInterval(fightPoll);
  clearInterval(fightTick);
  fightRoot.classList.add("hidden");
}

function onDeath(res) {
  closeFight();
  refreshProfile();
  if (tg.isVersionAtLeast && tg.isVersionAtLeast("6.2") && tg.showAlert) {
    tg.showAlert(res.message);
  } else {
    setStatus(res.message);
  }
}

function startFight(v) {
  fight.active = false;
  fight.selected = null;
  fight.gainXp = 0;
  fight.gainSilver = 0;
  fight.log = [];
  fight.seen = new Set();
  fight.php = v.php;
  document.getElementById("fLog").textContent = "";
  fightRoot.classList.remove("hidden");
  buildMobs(v.mobs);
  renderHeal();
  applyView(v);
  fight.active = true;
  logLine("Из кустов выскочили мобы! Выбери цель и атакуй");
  clearInterval(fightPoll);
  clearInterval(fightTick);
  fightPoll = setInterval(pollFight, 1000);
  fightTick = setInterval(tickFight, 250);
}

async function pollFight() {
  if (!fight.active || fBusy) return;
  try {
    const res = await call("/fight/state", {init_data: tg.initData});
    if (res.dead) { onDeath(res); return; }
    applyView(res);
  } catch (e) {
    if (e.message === "Ты сейчас не здесь") closeFight();
  }
}

document.getElementById("fAttack").onclick = async () => {
  if (fBusy || fight.selected === null) return;
  fBusy = true;
  try {
    const res = await call("/fight/attack",
      {init_data: tg.initData, mob_id: fight.selected});
    if (res.dead) {
      onDeath(res);
    } else {
      applyView(res);
      if (res.hit.miss) {
        logLine("💨 Ты промахнулся");
      } else {
        logLine("⚔️ Ты нанёс " + res.hit.damage + (res.hit.crit ? " (КРИТ!)" : ""));
      }
      if (res.killed) {
        fight.gainXp += res.killed.xp;
        fight.gainSilver += res.killed.silver;
        logLine("☠️ " + res.killed.name + " побеждён: +" + res.killed.xp +
                " опыта, +" + res.killed.silver + " серебра");
        refreshProfile();
      }
      if (res.done) {
        logLine("🏆 Победа! Всего: +" + fight.gainXp + " опыта, +" +
                fight.gainSilver + " серебра");
      }
    }
  } catch (e) {
    if (e.message === "Ты сейчас не здесь") closeFight();
    else logLine("⚠️ " + e.message);
  }
  fBusy = false;
};

document.getElementById("fFlee").onclick = async () => {
  if (fBusy) return;
  fBusy = true;
  try {
    const res = await call("/fight/flee", {init_data: tg.initData});
    if (res.dead) {
      onDeath(res);
    } else if (res.fled) {
      closeFight();
      setStatus(res.message);
      refreshProfile();
    } else {
      applyView(res);
      logLine("🏃 " + res.message);
    }
  } catch (e) {
    if (e.message === "Ты сейчас не здесь") closeFight();
    else logLine("⚠️ " + e.message);
  }
  fBusy = false;
};

/* ---------- подмена входа в RTP и восстановления ---------- */
rtpGo = async function () {
  try {
    const res = await call("/rtp/roll", {init_data: tg.initData});
    if (res.place === "clearing") {
      startFight(res);
      setStatus("Тебя заметили мобы!");
      return;
    }
    enterScene(res);
    setStatus(res.place === "forest" ? "Ты попал в лес" : "Ты вышел к озеру");
  } catch (e) {
    setStatus(e.message);
  }
};

restoreScene = async function () {
  try {
    const res = await call("/rtp/current2", {init_data: tg.initData});
    if (res.dead) {
      setStatus(res.message);
      refreshProfile();
      return;
    }
    if (res.place === "clearing") startFight(res);
    else if (res.place) enterScene(res);
  } catch (e) {}
};
