const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

window.onerror = (msg, src, line) => {
  const d = document.createElement("div");
  d.style.cssText = "position:fixed;top:0;left:0;right:0;background:#d64545;color:#fff;padding:8px;font-size:12px;z-index:999";
  d.textContent = "Ошибка: " + msg + " (" + String(src).split("/").pop() + ":" + line + ")";
  document.body.appendChild(d);
};

/* ---------- сообщения ---------- */
const toastEl = document.getElementById("toast");
let toastTimer;
function setStatus(msg) {
  clearTimeout(toastTimer);
  toastEl.textContent = msg || "";
  toastEl.classList.toggle("hidden", !msg);
  if (msg) toastTimer = setTimeout(() => toastEl.classList.add("hidden"), 3500);
}

/* ---------- данные игрока ---------- */
const SLOTS = [
  ["helmet","Шлем"], ["chest","Нагрудник"], ["gloves","Перчатки"],
  ["pants","Штаны"], ["boots","Ботинки"], ["amulet","Амулет"],
  ["weapon","Оружие"]
];
const INV_SIZE = 10;
let shopItems = [];
let shopCat = "pvp";
let inventory = [];
let deleteMode = false;

const me = {x:180, y:320, tx:null, ty:null, pending:null,
            name:"Игрок", cls:"fighter"};

function show(p) {
  me.name = p.first_name || p.username || "Игрок";
  me.cls = p.class;
  document.getElementById("name").textContent = me.name;
  document.getElementById("silver").textContent = "Серебро: " + p.balance;
  document.getElementById("levelText").textContent = "Уровень " + p.level;
  document.getElementById("hpText").textContent = p.hp + " / 100";
  document.getElementById("hpFill").style.width = Math.min(100, p.hp) + "%";
  document.getElementById("xpText").textContent = p.xp + " / " + p.xp_to_next;
  document.getElementById("xpFill").style.width =
      Math.min(100, p.xp / p.xp_to_next * 100) + "%";
  document.getElementById("points").textContent = p.stat_points;
  if (p.photo_url) document.getElementById("avatar").src = p.photo_url;
  document.querySelectorAll(".classes button").forEach(b =>
    b.classList.toggle("active", b.dataset.c === p.class));
}

function ask(text, yes) {
  if (tg.isVersionAtLeast && tg.isVersionAtLeast("6.2") && tg.showConfirm) {
    tg.showConfirm(text, ok => { if (ok) yes(); });
  } else if (confirm(text)) {
    yes();
  }
}

function itemLabel(row) {
  return (row.equipped ? "✓ " : "") + row.items.name +
         (row.qty > 1 ? " x" + row.qty : "");
}

function showInventory(list) {
  inventory = list;

  const equip = document.getElementById("equip");
  equip.innerHTML = "";
  SLOTS.forEach(([key, label]) => {
    const row = list.find(r => r.equipped && r.items && r.items.slot === key);
    const d = document.createElement("div");
    d.className = "slot" + (row ? " full on" : "");
    d.textContent = row ? row.items.name : label;
    if (row) d.onclick = () => act("/inventory/unequip", row.id);
    equip.appendChild(d);
  });

  const inv = document.getElementById("inv");
  inv.innerHTML = "";
  document.getElementById("invCount").textContent =
    "(" + list.length + "/" + INV_SIZE + ")";
  for (let i = 0; i < INV_SIZE; i++) {
    const row = list[i];
    const d = document.createElement("div");
    if (row) {
      d.className = "slot full" + (row.equipped ? " on" : "");
      d.textContent = itemLabel(row);
      d.onclick = () => {
        if (deleteMode) {
          if (row.equipped) {
            setStatus("Сначала сними предмет");
            return;
          }
          ask("Удалить «" + row.items.name +
              (row.qty > 1 ? " x" + row.qty : "") +
              "»? Это нельзя отменить.",
              () => act("/inventory/delete", row.id));
          return;
        }
        if (!row.items.slot) {
          setStatus("Этот предмет нельзя надеть");
          return;
        }
        act(row.equipped ? "/inventory/unequip" : "/inventory/equip", row.id);
      };
    } else {
      d.className = "slot";
    }
    inv.appendChild(d);
  }

  showSell();
}

function makeRow(title, sub, btnText, onClick, cls) {
  const row = document.createElement("div");
  row.className = "row";
  const left = document.createElement("div");
  const t = document.createElement("div");
  t.textContent = title;
  if (cls) t.className = cls;
  const s = document.createElement("small");
  s.textContent = sub;
  left.appendChild(t);
  left.appendChild(s);
  const b = document.createElement("button");
  b.textContent = btnText;
  b.onclick = onClick;
  row.appendChild(left);
  row.appendChild(b);
  return row;
}

function showShop() {
  const box = document.getElementById("shopList");
  box.innerHTML = "";
  shopItems.filter(i => i.shop_category === shopCat).forEach(i => {
    const rarity = i.rarity === "uncommon" ? "Необычный" : "Обычный";
    box.appendChild(makeRow(
      i.name,
      rarity + " · " + i.price + " серебра",
      "Купить",
      () => buy(i.id),
      i.rarity === "uncommon" ? "uncommon" : ""
    ));
  });
}

function showSell() {
  const box = document.getElementById("sellList");
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
      () => sell(r.id)
    ));
  });
}

/* ---------- запросы к серверу ---------- */
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

async function buy(itemId) {
  try {
    apply(await call("/shop/buy", {init_data: tg.initData, item_id: itemId}));
  } catch (e) {
    setStatus(e.message);
  }
}

async function sell(invId) {
  await act("/shop/sell", invId);
}

async function start() {
  setStatus("Загрузка...");
  try {
    const res = await call("/auth/telegram", {init_data: tg.initData});
    apply(res);
    setStatus("");
    const shop = await call("/shop/items");
    shopItems = shop.items;
    showShop();
    await restoreScene();
  } catch (e) {
    setStatus("Не удалось войти: " + e.message);
  }
}

/* ---------- окна ---------- */
const overlay = document.getElementById("overlay");

function openSheet(sec, title) {
  document.querySelectorAll(".sec").forEach(s =>
    s.classList.toggle("hidden", s.id !== "sec-" + sec));
  document.getElementById("sheetTitle").textContent = title;
  overlay.classList.remove("hidden");
}
function closeSheet() { overlay.classList.add("hidden"); }

document.getElementById("sheetClose").onclick = closeSheet;
overlay.onclick = e => { if (e.target === overlay) closeSheet(); };
document.getElementById("profileBtn").onclick = () => openSheet("profile", "Профиль");
document.getElementById("gBase").onclick = () => setStatus("Строительство баз скоро появится");
document.getElementById("gRtp").onclick = () => { closeSheet(); rtpGo(); };

document.getElementById("delBtn").onclick = () => {
  deleteMode = !deleteMode;
  const b = document.getElementById("delBtn");
  b.textContent = "🗑 Режим удаления: " + (deleteMode ? "ВКЛ" : "выкл");
  b.classList.toggle("danger", deleteMode);
  document.getElementById("invBox").classList.toggle("del", deleteMode);
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
    document.getElementById("m-buy").classList.toggle("hidden", b.dataset.m !== "buy");
    document.getElementById("m-sell").classList.toggle("hidden", b.dataset.m !== "sell");
  };
});
