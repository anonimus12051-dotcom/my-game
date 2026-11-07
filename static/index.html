const fight = {
  active: false, mobs: [], cards: {}, php: 0, pmax: 0, selected: null,
  readyAt: 0, healReadyAt: 0, done: false, gainXp: 0, gainSilver: 0,
  log: [], seen: new Set(), healBtns: []
};
let fightPoll = null;
let fightTick = null;
let fBusy = false;

function logLine(text) {
  fight.log.unshift(text);
  fight.log = fight.log.slice(0, 6);
  $("fLog").textContent = fight.log.join("\n");
}

function isAlive(id) {
  return fight.mobs.some(m => m.id === id && m.hp > 0);
}

/* ---------- карточки мобов (создаются один раз) ---------- */
function buildMobs(mobs) {
  const box = $("fMobs");
  box.innerHTML = "";
  fight.cards = {};

  mobs.forEach(m => {
    const card = el("div", "mobcard");
    const em = el("div", "em", m.emoji);
    const bar = el("div", "bar");
    const fill = el("div", "fill");
    fill.style.background = "#d64545";
    bar.appendChild(fill);
    const hp = el("div", "hp");

    card.appendChild(em);
    card.appendChild(el("div", "nm", m.name));
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
    const dead = m.hp <= 0;
    c.em.textContent = dead ? "💀" : c.emoji;
    c.fill.style.width = Math.max(0, m.hp / m.max_hp * 100) + "%";
    c.hp.textContent = dead ? "побеждён" : Math.ceil(m.hp) + " / " + m.max_hp;
    c.card.classList.toggle("dead", dead);
    c.card.classList.toggle("sel", fight.selected === m.id && !dead);
  });
}

function updatePlayer() {
  $("fPhp").textContent = Math.ceil(fight.php) + " / " + fight.pmax;
  $("fPhpFill").style.width = Math.min(100, fight.php / fight.pmax * 100) + "%";
}

/* ---------- лечение ---------- */
function renderHeal() {
  const box = $("fHeal");
  box.innerHTML = "";
  fight.healBtns = [];

  const groups = {};
  inventory.filter(r => r.items.type === "heal").forEach(r => {
    const g = groups[r.items.id] ||
      (groups[r.items.id] = {row: r, name: r.items.name, id: r.items.id, count: 0});
    g.count += r.qty;
  });

  const list = Object.values(groups);
  if (!list.length) {
    box.appendChild(el("div", "", "Нет лечебных предметов. Их можно купить у торговца"));
    return;
  }

  list.forEach(g => {
    const info = itemCatalog[g.id];
    const label = "🩹 " + g.name + " x" + g.count +
                  (info && info.heal ? " (+" + info.heal + ")" : "");
    const btn = el("button", "", label);
    btn.onclick = () => useHeal(g.row.id);
    box.appendChild(btn);
    fight.healBtns.push({btn: btn, label: label});
  });
}

async function useHeal(invId) {
  if (fBusy) return;
  fBusy = true;
  try {
    const res = await call("/fight/heal",
      {init_data: tg.initData, inv_id: invId});
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

/* ---------- состояние боя ---------- */
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

  const atk = $("fAttack");
  atk.classList.toggle("hidden", fight.done);
  atk.disabled = now < fight.readyAt || fight.selected === null;
  $("fFlee").textContent = fight.done ? "🏠 На спавн" : "🏃 Бежать";

  const wait = Math.ceil((fight.healReadyAt - now) / 1000);
  fight.healBtns.forEach(h => {
    h.btn.disabled = wait > 0 || fight.php >= fight.pmax || fight.done;
    h.btn.textContent = h.label + (wait > 0 ? " (" + wait + ")" : "");
  });
}

function closeFight() {
  fight.active = false;
  clearInterval(fightPoll);
  clearInterval(fightTick);
  $("fightRoot").classList.add("hidden");
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
  $("fLog").textContent = "";
  $("fightRoot").classList.remove("hidden");

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

/* ---------- кнопки ---------- */
$("fAttack").onclick = async () => {
  if (fBusy || fight.selected === null) return;
  fBusy = true;
  try {
    const res = await call("/fight/attack",
      {init_data: tg.initData, mob_id: fight.selected});
    if (res.dead) {
      onDeath(res);
    } else {
      applyView(res);
      logLine(res.hit.miss
        ? "💨 Ты промахнулся"
        : "⚔️ Ты нанёс " + res.hit.damage + (res.hit.crit ? " (КРИТ!)" : ""));

      if (res.killed) {
        fight.gainXp += res.killed.xp;
        fight.gainSilver += res.killed.silver;
        logLine("☠️ " + res.killed.name + " побеждён: +" + res.killed.xp +
                " опыта, +" + res.killed.silver + " серебра");
        if (res.player) show(res.player);
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

$("fFlee").onclick = async () => {
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
