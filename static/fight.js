/* Бой на поляне: подключается из world.js */
const fight = {
  active: false, mobs: [], php: 0, pmax: 0, selected: null,
  readyAt: 0, done: false, gainXp: 0, gainSilver: 0, log: []
};
let fightPoll = null;
let fightTick = null;
let fBusy = false;

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
  '<div id="fLog" style="min-height:80px;font-size:13px;text-align:center;line-height:1.5;white-space:pre-line"></div>' +
  '<div style="display:flex;gap:8px;margin-top:10px">' +
  '<button id="fAttack" style="flex:2;padding:14px;border:none;border-radius:8px;background:#f5c542;color:#111;font-weight:bold;font-size:16px">⚔️ Атаковать</button>' +
  '<button id="fFlee" style="flex:1;padding:14px;border:none;border-radius:8px;background:#444;color:#eee;font-weight:bold;font-size:16px">🏃 Бежать</button>' +
  '</div>';
document.body.appendChild(fightRoot);

function logLine(text) {
  fight.log.unshift(text);
  fight.log = fight.log.slice(0, 5);
  document.getElementById("fLog").textContent = fight.log.join("\n");
}

function isAlive(id) {
  return fight.mobs.some(m => m.id === id && m.hp > 0);
}

function renderFight() {
  document.getElementById("fPhp").textContent =
    Math.ceil(fight.php) + " / " + fight.pmax;
  document.getElementById("fPhpFill").style.width =
    Math.min(100, fight.php / fight.pmax * 100) + "%";

  const box = document.getElementById("fMobs");
  box.innerHTML = "";
  fight.mobs.forEach(m => {
    const dead = m.hp <= 0;
    const sel = fight.selected === m.id && !dead;
    const card = document.createElement("div");
    card.style.cssText =
      "width:100px;padding:8px;border-radius:12px;text-align:center;" +
      "background:" + (dead ? "#1f3f1f" : "#272735") + ";" +
      "border:3px solid " + (sel ? "#f5c542" : "#444") + ";" +
      "opacity:" + (dead ? "0.45" : "1");

    const em = document.createElement("div");
    em.style.fontSize = "44px";
    em.textContent = dead ? "💀" : m.emoji;

    const nm = document.createElement("div");
    nm.style.fontSize = "12px";
    nm.textContent = m.name;

    const bar = document.createElement("div");
    bar.className = "bar";
    bar.style.margin = "6px 0 2px";
    const fill = document.createElement("div");
    fill.className = "fill";
    fill.style.background = "#d64545";
    fill.style.width = Math.max(0, m.hp / m.max_hp * 100) + "%";
    bar.appendChild(fill);

    const hp = document.createElement("div");
    hp.style.fontSize = "11px";
    hp.textContent = dead ? "побеждён" : Math.ceil(m.hp) + " / " + m.max_hp;

    card.appendChild(em);
    card.appendChild(nm);
    card.appendChild(bar);
    card.appendChild(hp);
    card.onclick = () => {
      if (!dead) { fight.selected = m.id; renderFight(); }
    };
    box.appendChild(card);
  });

  const atk = document.getElementById("fAttack");
  const flee = document.getElementById("fFlee");
  atk.classList.toggle("hidden", fight.done);
  flee.textContent = fight.done ? "🏠 На спавн" : "🏃 Бежать";
  const waiting = Date.now() < fight.readyAt;
  atk.disabled = waiting || fight.selected === null;
  atk.style.opacity = atk.disabled ? "0.5" : "1";
}

function applyView(v) {
  const now = Date.now();
  if (fight.active && v.php < fight.php - 0.5) {
    logLine("💢 Тебе нанесли " + Math.round(fight.php - v.php) + " урона");
  }
  fight.php = v.php;
  fight.pmax = v.pmax;
  fight.done = v.done;
  fight.mobs = v.mobs.map(m => Object.assign(m, {nextAt: now + m.next_in * 1000}));
  fight.readyAt = now + v.ready_in * 1000;
  if (fight.selected === null || !isAlive(fight.selected)) {
    const a = fight.mobs.find(m => m.hp > 0);
    fight.selected = a ? a.id : null;
  }
  renderFight();
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
  fight.php = v.php;
  document.getElementById("fLog").textContent = "";
  fightRoot.classList.remove("hidden");
  applyView(v);
  fight.active = true;
  logLine("Из кустов выскочили мобы! Выбери цель и атакуй");
  clearInterval(fightPoll);
  clearInterval(fightTick);
  fightPoll = setInterval(pollFight, 1000);
  fightTick = setInterval(renderFight, 250);
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
      logLine("⚔️ Ты нанёс " + res.hit.damage + (res.hit.crit ? " (КРИТ!)" : ""));
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
