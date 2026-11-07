const W = 360, H = 520;
const canvas = $("world");
const ctx = canvas.getContext("2d");
const dpr = window.devicePixelRatio || 1;
canvas.width = W * dpr;
canvas.height = H * dpr;
ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

const CLASS_COLORS = {fighter: "#d64545", rogue: "#7a4ad6", gatherer: "#3fae5a"};
const ARROWS = {left: "⬅️", right: "➡️", up: "⬆️", down: "⬇️"};

const me = {x: 180, y: 320, tx: null, ty: null, pending: null};
const cam = {x: 0, y: 0};
let scene = "village";            // village | forest | lake | mine
let forest = null;
let mine = null;
const lake = {phase: "idle", waitUntil: 0};
let busy = false;

const places = [
  {id: "auction",  name: "Аукцион",  emoji: "⚖️", x: 25,  y: 35,  w: 120, h: 85, color: "#8a5a2b", roof: "#b33a3a", door: {x: 85,  y: 140}, title: "Аукцион"},
  {id: "merchant", name: "Торговец", emoji: "🧑‍🌾", x: 215, y: 35,  w: 120, h: 85, color: "#2b6a8a", roof: "#2a9a6a", door: {x: 275, y: 140}, title: "Торговец"},
  {id: "forge",    name: "Кузня",    emoji: "🔨", x: 15,  y: 225, w: 95,  h: 85, color: "#555",    roof: "#333",    door: {x: 128, y: 268}, title: "Кузня"},
  {id: "mine",     name: "Шахта",    emoji: "⛏️", x: 250, y: 225, w: 95,  h: 85, color: "#6b5a4a", roof: "#3a2f26", door: {x: 232, y: 268}, title: "Шахта"},
  {id: "gates",    name: "Ворота",   emoji: "🚪", x: 120, y: 440, w: 120, h: 70, color: "#7a7a7a", roof: "#444",    door: {x: 180, y: 425}, title: "Ворота"}
];

function worldW() {
  if (scene === "forest") return forest.width;
  if (scene === "mine") return mine.width;
  return W;
}
function worldH() {
  if (scene === "forest") return forest.height;
  if (scene === "mine") return mine.height;
  return H;
}

/* ---------- движение и ввод ---------- */
function openPlace(id) {
  if (id === "mine") {
    enterMine();
    return;
  }
  openSheet(id, places.find(p => p.id === id).title);
}

function go(x, y, pending) {
  x = Math.max(12, Math.min(worldW() - 12, x));
  y = Math.max(12, Math.min(worldH() - 12, y));
  if (scene === "lake") y = Math.max(y, 330);
  me.tx = x; me.ty = y; me.pending = pending;
  if (Math.hypot(x - me.x, y - me.y) < 3) {
    me.tx = null;
    if (pending) { me.pending = null; openPlace(pending); }
  }
}

canvas.addEventListener("pointerdown", e => {
  const r = canvas.getBoundingClientRect();
  const x = (e.clientX - r.left) * W / r.width + cam.x;
  const y = (e.clientY - r.top) * H / r.height + cam.y;

  if (scene === "village") {
    const hit = places.find(p =>
      x >= p.x && x <= p.x + p.w && y >= p.y && y <= p.y + p.h);
    if (hit) { go(hit.door.x, hit.door.y, hit.id); return; }
  }
  go(x, y, null);
});

/* ---------- рисование ---------- */
function emoji(txt, x, y, size) {
  ctx.font = size + "px serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(txt, x, y);
}

function drawPlayer() {
  ctx.fillStyle = "rgba(0,0,0,.3)";
  ctx.beginPath(); ctx.ellipse(me.x, me.y + 10, 10, 4, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = CLASS_COLORS[hero.cls] || "#d64545";
  ctx.beginPath(); ctx.arc(me.x, me.y, 10, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke();
  ctx.fillStyle = "#fff";
  ctx.font = "bold 12px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  ctx.fillText(hero.name, me.x, me.y - 16);
}

function drawVillage() {
  ctx.fillStyle = "#3b7d3b";
  ctx.fillRect(0, 0, W, H);

  ctx.fillStyle = "#b08a5a";
  ctx.fillRect(155, 120, 50, 330);
  ctx.fillRect(110, 245, 140, 50);
  ctx.fillRect(65, 120, 40, 40);
  ctx.fillRect(255, 120, 40, 40);
  ctx.fillRect(65, 140, 230, 20);

  ctx.fillStyle = "#c9a66b";
  ctx.beginPath(); ctx.arc(180, 270, 48, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#777";
  ctx.beginPath(); ctx.arc(180, 270, 16, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#3a7bd5";
  ctx.beginPath(); ctx.arc(180, 270, 10, 0, Math.PI * 2); ctx.fill();

  [[20,175],[335,175],[28,385],[332,385],[50,478],[310,478],[100,195],[262,195]]
    .forEach(([x, y]) => emoji("🌳", x, y, 28));
  [[120,380],[245,370],[90,335],[275,340]]
    .forEach(([x, y]) => emoji("🌼", x, y, 14));

  places.forEach(p => {
    ctx.fillStyle = p.color;
    ctx.fillRect(p.x, p.y, p.w, p.h);
    ctx.fillStyle = p.roof;
    ctx.fillRect(p.x - 4, p.y - 8, p.w + 8, 22);
    ctx.fillStyle = "#fff";
    emoji(p.emoji, p.x + p.w / 2, p.y + p.h / 2 - 2, 30);
    ctx.font = "bold 13px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "alphabetic";
    ctx.fillText(p.name, p.x + p.w / 2, p.y + p.h - 6);
  });

  drawPlayer();
}

function drawForest() {
  ctx.fillStyle = "#2f6b2f";
  ctx.fillRect(0, 0, W, H);
  ctx.save();
  ctx.translate(-cam.x, -cam.y);

  ctx.fillStyle = "#357535";
  for (let gx = 0; gx < forest.width; gx += 80) {
    for (let gy = 0; gy < forest.height; gy += 80) {
      if ((gx / 80 + gy / 80) % 2 === 0) ctx.fillRect(gx, gy, 80, 80);
    }
  }
  ctx.strokeStyle = "#1c4a1c";
  ctx.lineWidth = 4;
  ctx.strokeRect(0, 0, forest.width, forest.height);

  if (forest.treasure) {
    emoji(forest.treasure.dug ? "🕳️" : "❓", forest.treasure.x, forest.treasure.y, 26);
  }

  forest.trees.slice().sort((a, b) => a.y - b.y).forEach(t => {
    if (t.felled) { emoji("🪵", t.x, t.y, 22); return; }
    emoji("🌲", t.x, t.y, 44);
    if (t.started) {
      ctx.fillStyle = "#000";
      ctx.fillRect(t.x - 20, t.y - 36, 40, 6);
      ctx.fillStyle = "#f5c542";
      ctx.fillRect(t.x - 20, t.y - 36, 40 * t.hits / forest.hits, 6);
    }
  });

  drawPlayer();
  ctx.restore();
}

function drawLake() {
  ctx.fillStyle = "#3b7d3b";
  ctx.fillRect(0, 0, W, H);

  ctx.fillStyle = "#c9a66b";
  ctx.beginPath(); ctx.ellipse(180, 175, 182, 150, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#2a6fb0";
  ctx.beginPath(); ctx.ellipse(180, 170, 170, 140, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#3a86cc";
  ctx.beginPath(); ctx.ellipse(160, 140, 90, 60, 0, 0, Math.PI * 2); ctx.fill();

  [[30,330],[320,340],[60,480],[300,490]].forEach(([x, y]) => emoji("🌿", x, y, 24));
  [[90,350],[270,360]].forEach(([x, y]) => emoji("🪨", x, y, 22));

  if (lake.phase === "waiting" || lake.phase === "bite") {
    emoji("🔴", 180, 190 + Math.sin(performance.now() / 250) * 3, 16);
  }

  drawPlayer();
}

function drawMine() {
  // тёмный фон пещеры
  ctx.fillStyle = "#1a1a22";
  ctx.fillRect(0, 0, W, H);
  ctx.save();
  ctx.translate(-cam.x, -cam.y);

  // стены
  ctx.fillStyle = "#2a2a35";
  ctx.fillRect(0, 0, mine.width, mine.height);

  // пол
  ctx.fillStyle = "#22222c";
  for (let gx = 0; gx < mine.width; gx += 60) {
    for (let gy = 0; gy < mine.height; gy += 60) {
      if ((gx / 60 + gy / 60) % 2 === 0) ctx.fillRect(gx, gy, 60, 60);
    }
  }

  // выход (верх центр)
  ctx.fillStyle = "#3a2f26";
  ctx.fillRect(mine.width / 2 - 50, 20, 100, 50);
  ctx.fillStyle = "#1a1a22";
  ctx.beginPath();
  ctx.ellipse(mine.width / 2, 70, 40, 18, 0, 0, Math.PI * 2);
  ctx.fill();
  emoji("🚪", mine.width / 2, 45, 28);
  ctx.fillStyle = "#aaa";
  ctx.font = "bold 12px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("Выход", mine.width / 2, 95);

  // лифт (закрыт)
  ctx.fillStyle = "#333";
  ctx.fillRect(mine.width / 2 + 70, 25, 55, 55);
  ctx.fillStyle = "#555";
  ctx.fillRect(mine.width / 2 + 78, 33, 39, 39);
  emoji("🛗", mine.width / 2 + 97, 52, 22);
  ctx.fillStyle = "#888";
  ctx.font = "10px sans-serif";
  ctx.fillText("Скоро", mine.width / 2 + 97, 90);

  // жилы
  mine.veins.forEach(v => {
    if (v.done && v.collected) return;
    const alpha = v.done ? 0.5 : 1;
    ctx.globalAlpha = alpha;
    emoji(v.emoji, v.x, v.y, 32);
    if (v.started && !v.done) {
      // мини-полоска
      ctx.fillStyle = "#000";
      ctx.fillRect(v.x - 18, v.y - 28, 36, 5);
      ctx.fillStyle = "#f5c542";
      ctx.fillRect(v.x - 18, v.y - 28, 36 * v.progress, 5);
    }
    ctx.globalAlpha = 1;
  });

  drawPlayer();
  ctx.restore();
}

let last = performance.now();
function frame(t) {
  const dt = Math.min(0.05, (t - last) / 1000);
  last = t;

  if (me.tx !== null) {
    const dx = me.tx - me.x, dy = me.ty - me.y;
    const d = Math.hypot(dx, dy);
    const step = 150 * dt;
    if (d <= step) {
      me.x = me.tx; me.y = me.ty; me.tx = null;
      if (me.pending) {
        const id = me.pending;
        me.pending = null;
        openPlace(id);
      }
    } else {
      me.x += dx / d * step;
      me.y += dy / d * step;
    }
  }

  cam.x = Math.max(0, Math.min(worldW() - W, me.x - W / 2));
  cam.y = Math.max(0, Math.min(worldH() - H, me.y - H / 2));

  if (scene === "village") drawVillage();
  else if (scene === "forest") drawForest();
  else if (scene === "mine") drawMine();
  else drawLake();

  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

/* ---------- панель действий ---------- */
const bChop = $("bChop");
const bDig = $("bDig");
const bCast = $("bCast");
const bMineDig = $("bMineDig");

function nearestTree() {
  let best = null, bd = 55;
  for (const t of forest.trees) {
    if (t.felled) continue;
    const d = Math.hypot(t.x - me.x, t.y - me.y);
    if (d < bd) { bd = d; best = t; }
  }
  return best;
}

function nearestVein() {
  if (!mine) return null;
  let best = null, bd = 55;
  for (const v of mine.veins) {
    if (v.done && v.collected) continue;
    const d = Math.hypot(v.x - me.x, v.y - me.y);
    if (d < bd) { bd = d; best = v; }
  }
  return best;
}

function nearTreasure() {
  const t = forest.treasure;
  return t && !t.dug && Math.hypot(t.x - me.x, t.y - me.y) < 55;
}

function updateActions() {
  $("actions").classList.toggle("hidden", scene === "village");
  if (scene === "village") return;

  bChop.classList.toggle("hidden", scene !== "forest");
  bDig.classList.toggle("hidden", scene !== "forest" || !nearTreasure());
  bCast.classList.toggle("hidden", scene !== "lake");
  bMineDig.classList.toggle("hidden", scene !== "mine");

  if (scene === "forest") {
    const t = nearestTree();
    let text = "Подойди к дереву (тапни по земле)";
    bChop.textContent = "🪓 Рубить";
    if (t && t.started) {
      const left = Math.max(0, Math.ceil((t.readyAt - Date.now()) / 1000));
      text = "Дерево: удар " + t.hits + "/" + forest.hits +
             (left > 0 ? " · следующий через " + left + " с" : " · можно рубить!");
      if (left > 0) bChop.textContent = "🪓 Рубить (" + left + ")";
    } else if (t) {
      text = "Дерево рядом. Рубка займёт " + forest.hits * forest.gap + " секунд";
      bChop.textContent = "🪓 Начать рубку";
    }
    if (nearTreasure()) text = "Здесь клад! Нужна лопата";
    $("sceneInfo").textContent = text;
  } else if (scene === "mine") {
    const v = nearestVein();
    if (!v) {
      $("sceneInfo").textContent = "Все жилы выкопаны. Можно выйти";
      bMineDig.textContent = "⛏️ Копать";
      bMineDig.disabled = true;
    } else if (v.done) {
      $("sceneInfo").textContent = v.name + " готова! Забери добычу";
      bMineDig.textContent = "📦 Забрать";
      bMineDig.disabled = false;
    } else if (v.started) {
      const sec = Math.ceil(v.left);
      $("sceneInfo").textContent = "Копается " + v.name + " · осталось \~" + sec + " с";
      bMineDig.textContent = "⛏️ Открыть";
      bMineDig.disabled = false;
    } else {
      $("sceneInfo").textContent = "Рядом: " + v.name + ". Нажми «Копать»";
      bMineDig.textContent = "⛏️ Копать";
      bMineDig.disabled = false;
    }
  } else {
    if (lake.phase === "idle") {
      $("sceneInfo").textContent = "Забрось удочку: поклёвка через 20–60 секунд";
    } else if (lake.phase === "waiting") {
      const left = Math.max(0, Math.ceil((lake.waitUntil - Date.now()) / 1000));
      $("sceneInfo").textContent = "Ждём поклёвку... " + left + " с";
    } else {
      $("sceneInfo").textContent = "";
    }
    bCast.disabled = lake.phase !== "idle";
  }
}
setInterval(updateActions, 250);

/* ---------- RTP: вход, возврат, выход ---------- */
function enterScene(p) {
  me.tx = null;
  me.pending = null;

  if (p.place === "forest") {
    scene = "forest";
    forest = {
      width: p.width, height: p.height, hits: p.hits_needed, gap: p.gap,
      trees: p.trees, treasure: p.treasure
    };
    forest.trees.forEach(t => { t.readyAt = Date.now() + t.wait * 1000; });
    me.x = p.start.x;
    me.y = p.start.y;
  } else if (p.place === "mine") {
    scene = "mine";
    mine = {
      width: p.width,
      height: p.height,
      veins: p.veins
    };
    me.x = p.start.x;
    me.y = p.start.y;
  } else {
    scene = "lake";
    me.x = 180;
    me.y = 390;
    lake.phase = p.phase;
    if (lake.phase === "waiting") {
      lake.waitUntil = Date.now() + p.wait_left * 1000;
      scheduleBite();
    }
  }
  updateActions();
}

async function enterMine() {
  try {
    const res = await call("/mine/enter", {init_data: tg.initData});
    enterScene(res);
    setStatus("Ты вошёл в шахту");
  } catch (e) {
    setStatus(e.message);
  }
}

async function rtpGo() {
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
}

async function restoreScene() {
  try {
    const res = await call("/rtp/current", {init_data: tg.initData});
    if (res.dead) {
      setStatus(res.message);
      refreshProfile();
    } else if (res.place === "clearing") {
      startFight(res);
    } else if (res.place) {
      enterScene(res);
    }
  } catch (e) {}
}

$("bLeave").onclick = async () => {
  clearTimeout(biteTimer);
  clearInterval(fishTimer);
  fishInput = false;
  $("fishgame").classList.add("hidden");
  $("btnrow").classList.remove("hidden");
  lake.phase = "idle";
  try { await call("/rtp/leave", {init_data: tg.initData}); } catch (e) {}
  scene = "village";
  me.x = 180;
  me.y = 400;
  me.tx = null;
  mine = null;
  updateActions();
};

/* ---------- лес ---------- */
bChop.onclick = async () => {
  if (busy) return;
  const t = nearestTree();
  if (!t) { setStatus("Подойди ближе к дереву"); return; }
  if (t.started) {
    const left = (t.readyAt - Date.now()) / 1000;
    if (left > 0.8) { setStatus("Рано. Подожди ещё " + Math.ceil(left) + " сек"); return; }
  }
  busy = true;
  try {
    const res = await call("/forest/chop",
      {init_data: tg.initData, tree_id: t.id});
    Object.assign(t, res.tree);
    t.readyAt = Date.now() + res.tree.wait * 1000;
    apply(res);
  } catch (e) {
    setStatus(e.message);
  }
  busy = false;
};

bDig.onclick = async () => {
  if (busy) return;
  busy = true;
  try {
    const res = await call("/forest/dig", {init_data: tg.initData});
    forest.treasure = res.treasure;
    apply(res);
  } catch (e) {
    setStatus(e.message);
  }
  busy = false;
};

/* ---------- шахта ---------- */
bMineDig.onclick = async () => {
  const v = nearestVein();
  if (!v) return;

  if (v.done) {
    // забрать
    try {
      const res = await call("/mine/collect", {init_data: tg.initData, vein_id: v.id});
      Object.assign(v, res.vein);
      v.collected = true;
      apply(res);
      closeDig();
    } catch (e) {
      setStatus(e.message);
    }
    return;
  }

  // открыть окно копания
  openDig(v);
};

/* ---------- озеро ---------- */
let biteTimer = null;
let biteTries = 0;
let fishTimer = null;
let fishSeq = [];
let fishAns = [];
let fishInput = false;

bCast.onclick = async () => {
  if (lake.phase !== "idle") return;
  try {
    const res = await call("/fish/start", {init_data: tg.initData});
    lake.phase = "waiting";
    lake.waitUntil = Date.now() + res.wait * 1000;
    scheduleBite();
  } catch (e) {
    setStatus(e.message);
  }
};

function scheduleBite() {
  clearTimeout(biteTimer);
  biteTimer = setTimeout(doBite, Math.max(0, lake.waitUntil - Date.now()) + 300);
}

async function doBite() {
  try {
    const res = await call("/fish/bite", {init_data: tg.initData});
    biteTries = 0;
    startMemory(res);
  } catch (e) {
    if (e.message === "Пока не клюёт" && biteTries < 5) {
      biteTries++;
      biteTimer = setTimeout(doBite, 1000);
    } else {
      biteTries = 0;
      lake.phase = "idle";
      setStatus(e.message);
    }
  }
}

function fishProgress() {
  let s = "";
  for (let i = 0; i < fishSeq.length; i++) s += i < fishAns.length ? "● " : "○ ";
  $("fishProg").textContent = s;
}

function startMemory(res) {
  lake.phase = "bite";
  fishSeq = res.sequence;
  fishAns = [];
  fishInput = false;
  $("btnrow").classList.add("hidden");
  $("fishgame").classList.remove("hidden");
  $("fishPad").classList.add("hidden");
  $("fishProg").textContent = "";
  $("fishSeq").textContent = fishSeq.map(d => ARROWS[d]).join(" ");

  let left = res.show_seconds;
  $("fishTitle").textContent = "Клюёт! Запомни: " + left + " с";
  clearInterval(fishTimer);
  fishTimer = setInterval(() => {
    left--;
    if (left > 0) {
      $("fishTitle").textContent = "Клюёт! Запомни: " + left + " с";
      return;
    }
    clearInterval(fishTimer);
    startInput(res.answer_seconds);
  }, 1000);
}

function startInput(seconds) {
  fishInput = true;
  $("fishSeq").textContent = "";
  $("fishPad").classList.remove("hidden");
  fishProgress();

  let left = seconds;
  $("fishTitle").textContent = "Повтори! Осталось " + left + " с";
  fishTimer = setInterval(() => {
    left--;
    $("fishTitle").textContent = "Повтори! Осталось " + left + " с";
    if (left <= 0) {
      clearInterval(fishTimer);
      finishFish();
    }
  }, 1000);
}

document.querySelectorAll("#fishPad button").forEach(b => {
  b.onclick = () => {
    if (!fishInput) return;
    fishAns.push(b.dataset.d);
    fishProgress();
    if (fishAns.length >= fishSeq.length) {
      clearInterval(fishTimer);
      finishFish();
    }
  };
});

async function finishFish() {
  fishInput = false;
  $("fishgame").classList.add("hidden");
  $("btnrow").classList.remove("hidden");
  try {
    apply(await call("/fish/finish",
      {init_data: tg.initData, answer: fishAns}));
  } catch (e) {
    setStatus(e.message);
  }
  lake.phase = "idle";
}

/* ---------- окно копания шахты ---------- */
let digVein = null;
let digTimer = null;
let boostTimer = null;

function openDig(v) {
  digVein = v;
  $("digRoot").classList.remove("hidden");
  $("digTitle").textContent = v.emoji + " " + v.name;
  $("digBoostBtn").classList.add("hidden");
  updateDigBar();

  // если ещё не начато — стартуем
  if (!v.started) {
    call("/mine/start", {init_data: tg.initData, vein_id: v.id})
      .then(res => {
        Object.assign(v, res.vein);
        $("digInfo").textContent = res.message + " (ускорение " + (res.boost_percent || 10) + "%)";
        scheduleBoost();
      })
      .catch(e => setStatus(e.message));
  } else {
    $("digInfo").textContent = "Копается...";
    scheduleBoost();
  }

  clearInterval(digTimer);
  digTimer = setInterval(async () => {
    try {
      const res = await call("/mine/state", {init_data: tg.initData});
      const updated = res.veins.find(x => x.id === v.id);
      if (updated) {
        Object.assign(v, updated);
        // обновить и в mine.veins
        const mv = mine.veins.find(x => x.id === v.id);
        if (mv) Object.assign(mv, updated);
        updateDigBar();
        if (v.done) {
          $("digInfo").textContent = "Готово! Можно забрать";
          $("digBoostBtn").classList.add("hidden");
          clearInterval(digTimer);
          clearTimeout(boostTimer);
        }
      }
    } catch (e) {}
  }, 1000);
}

function updateDigBar() {
  if (!digVein) return;
  const pct = Math.min(100, (1 - digVein.left / digVein.total) * 100);
  $("digFill").style.width = pct + "%";
  $("digTime").textContent = digVein.done
    ? "Готово!"
    : Math.ceil(digVein.left) + " с";
}

function scheduleBoost() {
  clearTimeout(boostTimer);
  if (!digVein || digVein.done) return;
  const delay = 7000 + Math.random() * 8000; // 7–15 сек
  boostTimer = setTimeout(() => {
    if (digVein && !digVein.done) {
      // случайная позиция кнопки
      const btn = $("digBoostBtn");
      btn.classList.remove("hidden");
      btn.style.left = (20 + Math.random() * 60) + "%";
      btn.style.top = (30 + Math.random() * 40) + "%";
    }
  }, delay);
}

$("digBoostBtn").onclick = async () => {
  if (!digVein || digVein.done) return;
  $("digBoostBtn").classList.add("hidden");
  try {
    const res = await call("/mine/boost", {init_data: tg.initData, vein_id: digVein.id});
    Object.assign(digVein, res.vein);
    const mv = mine.veins.find(x => x.id === digVein.id);
    if (mv) Object.assign(mv, res.vein);
    updateDigBar();
    $("digInfo").textContent = res.message;
    if (!digVein.done) scheduleBoost();
  } catch (e) {
    setStatus(e.message);
  }
};

$("digClose").onclick = closeDig;
$("digCollect").onclick = async () => {
  if (!digVein || !digVein.done) return;
  try {
    const res = await call("/mine/collect", {init_data: tg.initData, vein_id: digVein.id});
    Object.assign(digVein, res.vein);
    digVein.collected = true;
    const mv = mine.veins.find(x => x.id === digVein.id);
    if (mv) { Object.assign(mv, res.vein); mv.collected = true; }
    apply(res);
    closeDig();
  } catch (e) {
    setStatus(e.message);
  }
};

function closeDig() {
  clearInterval(digTimer);
  clearTimeout(boostTimer);
  $("digRoot").classList.add("hidden");
  digVein = null;
}
  
