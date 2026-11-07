const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

window.onerror = (msg, src, line) => {
  const d = document.createElement("div");
  d.style.cssText = "position:fixed;top:0;left:0;right:0;background:#d64545;" +
                    "color:#fff;padding:8px;font-size:12px;z-index:999";
  d.textContent = "Ошибка: " + msg + " (" + String(src).split("/").pop() + ":" + line + ")";
  document.body.appendChild(d);
};

const $ = id => document.getElementById(id);

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/* ---------- состояние ---------- */
const SLOTS = [
  ["helmet", "Шлем"], ["chest", "Нагрудник"], ["gloves", "Перчатки"],
  ["pants", "Штаны"], ["boots", "Ботинки"], ["amulet", "Амулет"],
  ["weapon", "Оружие"]
];
const INV_SIZE = 10;
const STAT_DEFS = [
  ["damage", "⚔️ Урон", "+0.5 за очко", v => "+" + v],
  ["crit", "🎯 Шанс крита (×1.5)", "+0.3% за очко", v => v + "%"],
  ["hp", "❤️ Доп. HP", "+3 за очко", v => "+" + v],
  ["armor", "🛡 Броня", "+0.5 за очко", v => "+" + v],
  ["regen", "💚 Регенерация", "+0.5 за очко", v => "+" + v],
  ["evasion", "💨 Уклонение", "+0.3% за очко", v => v + "%"]
];

const hero = {name: "Игрок", cls: "fighter"};
let shopItems = [];
let shopCat = "pvp";
let inventory = [];
let itemCatalog = {};
let deleteMode = false;
let lastLevel = 0;

/* ---------- сообщения ---------- */
let toastTimer;
function setStatus(msg) {
  clearTimeout(toastTimer);
  $("toast").textContent = msg || "";
  $("toast").classList.toggle("hidden", !msg);
  if (msg) toastTimer = setTimeout(() => $("toast").classList.add("hidden"), 3500);
}

function ask(text, yes) {
  if (tg.isVersionAtLeast && tg.isVersionAtLeast("6.2") && tg.showConfirm) {
    tg.showConfirm(text, ok => { if (ok) yes(); });
  } else if (confirm(text)) {
    yes();
  }
}

/* ---------- запросы ---------- */
async function call(url, body) {
  const opts = body
    ? {method: "POST",
       headers: {"Content-Type": "application/json"},
       body: JSON.stringify(body)}
    : {};
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = "Ошибка " + r.status;
    try {
      const j = await r.json();
      if (j.detail) msg = j.detail;
    } catch (e) {}
    throw new Error(msg);
  }
  return r.json();
}

function apply(res) {
  if (res.player) show(res.player);
  if (res.inventory) showInventory(res.inventory);
  setStatus(res.message || "");
}

async function act(url, invId) {
  try {
    apply(await call(url, {init_data: tg.initData, inv_id: invId}));
  } catch (e) {
    setStatus(e.message);
  }
}

async function refreshProfile() {
  try {
    const r = await call("/profile/get", {init_data: tg.initData});
    show(r.player);
  } catch (e) {}
}

/* ---------- профиль ---------- */
function statRow(left, right) {
  const row = el("div", "line");
  row.appendChild(el("span", "", left));
  row.appendChild(el("b", "", right));
  return row;
}

function renderTotals(p) {
  const t = p.totals;
  const box = $("totalsBox");
  box.innerHTML = "";
  box.appendChild(statRow("⚔️ Урон", t.damage));
  box.appendChild(statRow("🎯 Шанс крита", t.crit + "%"));
  box.appendChild(statRow("❤️ Макс. HP", t.max_hp));
  box.appendChild(statRow("🛡 Броня", t.armor));
  box.appendChild(statRow("💚 Регенерация", t.regen));
  box.appendChild(statRow("💨 Уклонение", t.evasion + "%"));
}

function renderStats(p) {
  $("pointsText").textContent = "Свободных очков: " + p.stat_points;
  const box = $("statsBox");
  box.innerHTML = "";

  STAT_DEFS.forEach(([key, title, hint, fmt]) => {
    const s = p.stats[key];
    const row = el("div", "row");

    const left = el("div");
    left.appendChild(el("div", "", title + ": " + fmt(s.bonus)));
    left.appendChild(el("small", "", "вложено " + s.points + " · " + hint));

    const btns = el("div");
    [1, 5].forEach(n => {
      const b = el("button", "", "+" + n);
      b.style.marginLeft = "6px";
      b.disabled = p.stat_points < n;
      b.onclick = () => spendPoints(key, n);
      btns.appendChild(b);
    });

    row.appendChild(left);
    row.appendChild(btns);
    box.appendChild(row);
  });
}

function show(p) {
  hero.name = p.first_name || p.username || "Игрок";
  hero.cls = p.class;

  $("name").textContent = hero.name;
  $("silver").textContent = "Серебро: " + p.balance;
  if (p.photo_url) $("avatar").src = p.photo_url;

  $("levelText").textContent = "Уровень " + p.level;
  $("hpText").textContent = p.hp + " / " + p.max_hp;
  $("hpFill").style.width = Math.min(100, p.hp / p.max_hp * 100) + "%";

  const maxed = p.level >= p.max_level;
  $("xpText").textContent = maxed ? "МАКС" : p.xp + " / " + p.xp_to_next;
  $("xpFill").style.width =
    maxed ? "100%" : Math.min(100, p.xp / p.xp_to_next * 100) + "%";

  document.querySelectorAll(".classes button").forEach(b =>
    b.classList.toggle("active", b.dataset.c === p.class));

  renderTotals(p);
  renderStats(p);

  if (lastLevel && p.level > lastLevel) {
    setStatus("🎉 Новый уровень: " + p.level + "! Очки ждут в профиле");
  }
  lastLevel = p.level;
}

async function spendPoints(stat, n) {
  try {
    const res = await call("/profile/spend",
      {init_data: tg.initData, stat: stat, amount: n});
    show(res.player);
  } catch (e) {
    setStatus(e.message);
  }
}

/* ---------- инвентарь ---------- */
function showInventory(list) {
  inventory = list;
  const worn = list.filter(r => r.equipped);
  const bag = list.filter(r => !r.equipped);

  const equip = $("equip");
  equip.innerHTML = "";
  SLOTS.forEach(([key, label]) => {
    const row = worn.find(r => r.items.slot === key);
    const d = el("div", "slot" + (row ? " full on" : ""), row ? row.items.name : label);
    if (row) d.onclick = () => act("/inventory/unequip", row.id);
    equip.appendChild(d);
  });

  const inv = $("inv");
  inv.innerHTML = "";
  $("invCount").textContent = "(" + bag.length + "/" + INV_SIZE + ")";
  for (let i = 0; i < INV_SIZE; i++) {
    const row = bag[i];
    if (!row) { inv.appendChild(el("div", "slot")); continue; }

    const label = row.items.name + (row.qty > 1 ? " x" + row.qty : "");
    const d = el("div", "slot full", label);
    d.onclick = () => {
      if (deleteMode) {
        ask("Удалить «" + label + "»? Это нельзя отменить.",
            () => act("/inventory/delete", row.id));
      } else if (row.items.slot) {
        act("/inventory/equip", row.id);
      } else {
        setStatus("Этот предмет нельзя надеть");
      }
    };
    inv.appendChild(d);
  }

  showSell();
}

/* ---------- магазин ---------- */
function statText(id) {
  const it = itemCatalog[id];
  if (!it) return "";
  const parts = [];
  if (it.damage) parts.push("урон " + it.damage);
  if (it.hp_bonus) parts.push("+" + it.hp_bonus + " HP");
  if (it.armor) parts.push("броня " + it.armor);
  if (it.heal) parts.push("лечит " + it.heal + " HP");
  return parts.join(" · ");
}

function makeRow(title, sub, btnText, onClick, cls) {
  const row = el("div", "row");
  const left = el("div");
  left.appendChild(el("div", cls || "", title));
  left.appendChild(el("small", "", sub));
  const b = el("button", "", btnText);
  b.onclick = onClick;
  row.appendChild(left);
  row.appendChild(b);
  return row;
}

function showShop() {
  const box = $("shopList");
  box.innerHTML = "";
  shopItems.filter(i => i.shop_category === shopCat).forEach(i => {
    const rarity = i.rarity === "uncommon" ? "Необычный" : "Обычный";
    const st = statText(i.id);
    box.appendChild(makeRow(
      i.name,
      rarity + " · " + i.price + " серебра" + (st ? " · " + st : ""),
      "Купить",
      () => act2("/shop/buy", {item_id: i.id}),
      i.rarity === "uncommon" ? "uncommon" : ""
    ));
  });
}

function showSell() {
  const box = $("sellList");
  box.innerHTML = "";
  const res = inventory.filter(r => r.items.type === "resource" && !r.equipped);
  if (!res.length) {
    box.textContent = "Нет ресурсов для продажи";
    return;
  }
  res.forEach(r => {
    const total = r.items.sell_price * r.qty;
    box.appendChild(makeRow(
      r.items.name + " x" + r.qty,
      r.items.sell_price + " × " + r.qty + " = " + total + " серебра",
      "Продать всё",
      () => act("/shop/sell", r.id)
    ));
  });
}

async function act2(url, extra) {
  try {
    apply(await call(url, Object.assign({init_data: tg.initData}, extra)));
  } catch (e) {
    setStatus(e.message);
  }
}

/* ---------- окна ---------- */
const overlay = $("overlay");
let sheetOpenedAt = 0;

function openSheet(sec, title) {
  document.querySelectorAll(".sec").forEach(s =>
    s.classList.toggle("hidden", s.id !== "sec-" + sec));
  $("sheetTitle").textContent = title;
  overlay.classList.remove("hidden");
  sheetOpenedAt = Date.now();
}

function closeSheet() { overlay.classList.add("hidden"); }

$("sheetClose").onclick = closeSheet;
// «хвост» тапа, который открыл окно, не должен его сразу закрывать
overlay.onclick = e => {
  if (e.target === overlay && Date.now() - sheetOpenedAt > 500) closeSheet();
};

$("profileBtn").onclick = () => openSheet("profile", "Профиль");
$("gBase").onclick = () => setStatus("Строительство баз скоро появится");
$("gRtp").onclick = () => { closeSheet(); rtpGo(); };

$("delBtn").onclick = () => {
  deleteMode = !deleteMode;
  $("delBtn").textContent = "🗑 Режим удаления: " + (deleteMode ? "ВКЛ" : "выкл");
  $("delBtn").classList.toggle("danger", deleteMode);
  $("invBox").classList.toggle("del", deleteMode);
};

document.querySelectorAll(".classes button").forEach(b => {
  b.onclick = async () => {
    try {
      const res = await call("/profile/class",
        {init_data: tg.initData, player_class: b.dataset.c});
      show(res.player);
    } catch (e) {
      setStatus(e.message);
    }
  };
});

document.querySelectorAll(".cats button").forEach(b => {
  b.onclick = () => {
    shopCat = b.dataset.cat;
    document.querySelectorAll(".cats button").forEach(x =>
      x.classList.toggle("active", x === b));
    showShop();
  };
});

document.querySelectorAll("[data-m]").forEach(b => {
  b.onclick = () => {
    document.querySelectorAll("[data-m]").forEach(x =>
      x.classList.toggle("active", x === b));
    $("m-buy").classList.toggle("hidden", b.dataset.m !== "buy");
    $("m-sell").classList.toggle("hidden", b.dataset.m !== "sell");
  };
});

/* ---------- запуск ---------- */
async function start() {
  setStatus("Загрузка...");
  try {
    apply(await call("/auth/telegram", {init_data: tg.initData}));
    const [shop, cat] = await Promise.all([
      call("/shop/items"), call("/items/catalog")
    ]);
    shopItems = shop.items;
    itemCatalog = cat.items;
    showShop();
    setStatus("");
    await restoreScene();
  } catch (e) {
    setStatus("Не удалось войти: " + e.message);
  }
}
