const grid = document.getElementById("productGrid");
const searchInput = document.getElementById("searchInput");
const modelFilter = document.getElementById("modelFilter");
const sortFilter = document.getElementById("sortFilter");
const cartBtn = document.getElementById("cartBtn");
const cartDrawer = document.getElementById("cartDrawer");
const drawerBackdrop = document.getElementById("drawerBackdrop");
const drawerClose = document.getElementById("drawerClose");
const cartItemsEl = document.getElementById("cartItems");
const cartTotalEl = document.getElementById("cartTotal");
const cartCountEl = document.getElementById("cartCount");
const clearCartBtn = document.getElementById("clearCartBtn");
const checkoutBtn = document.getElementById("checkoutBtn");
const scrollTopBtn = document.getElementById("scrollTopBtn");
const tgHint = document.getElementById("tgHint");
const leadBackdrop = document.getElementById("leadBackdrop");
const leadModal = document.getElementById("leadModal");
const leadName = document.getElementById("leadName");
const leadPhone = document.getElementById("leadPhone");
const leadComment = document.getElementById("leadComment");
const leadTg = document.getElementById("leadTg");
const leadHint = document.getElementById("leadHint");
const leadCancel = document.getElementById("leadCancel");
const leadSend = document.getElementById("leadSend");

const RELAY_URL = "https://qbstore-relay.senoxone.workers.dev/lead";
const RELAY_AUTH = "QBSTORE_7f3a9c1d2e6b4a91f0c3d8aa";
const BUILD_ID = "20260129-0305";

const state = {
  baseItems: [],
  items: [],
  cart: loadCart(),
};

function getTgContext() {
  const tg = window.Telegram?.WebApp || null;
  const initData = tg?.initData || "";
  const qid = tg?.initDataUnsafe?.query_id || null;
  const user = tg?.initDataUnsafe?.user || null;
  return { tg, initData, qid, user };
}

const ctx = getTgContext();
const tg = ctx.tg;
try {
  tg?.ready();
  tg?.expand();
} catch {}

const MINI_APP_ERROR = "Открыто НЕ как Mini App. Открой через кнопку бота.";

function isMiniAppReady() {
  const local = getTgContext();
  return Boolean(local.tg && local.initData);
}

function applyMiniAppLock() {
  if (isMiniAppReady()) {
    if (tgHint) {
      tgHint.classList.remove("show");
      tgHint.style.color = "";
    }
    if (leadHint) {
      leadHint.style.color = "";
    }
    return;
  }
  if (tgHint) {
    tgHint.textContent = MINI_APP_ERROR;
    tgHint.style.color = "#ff5a5a";
    tgHint.classList.add("show");
  }
  if (leadHint) {
    leadHint.textContent = MINI_APP_ERROR;
    leadHint.style.color = "#ff5a5a";
    leadHint.classList.add("show");
  }
}

async function sendRelay(payload) {
  const res = await fetch(RELAY_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Auth": RELAY_AUTH,
    },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    const message = data?.error || `HTTP ${res.status}`;
    throw new Error(message);
  }
  return data;
}

applyMiniAppLock();
let miniCheckCount = 0;
const miniCheckTimer = setInterval(() => {
  applyMiniAppLock();
  miniCheckCount += 1;
  if (isMiniAppReady() || miniCheckCount >= 15) {
    clearInterval(miniCheckTimer);
  }
}, 300);

async function waitForInitData(timeoutMs = 2500) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const local = getTgContext();
    if (local.tg && local.initData && local.qid && local.user) return local;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  return getTgContext();
}

function formatPrice(value) {
  const num = Number(value || 0);
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

function formatTitle(title) {
  return String(title || "")
    .replace(/^Смартфон\s+Apple\s+iPhone\s+/i, "iPhone ")
    .replace(/^Смартфон\s+Apple\s+/i, "")
    .trim();
}

function getStorage(item) {
  const meta = item.meta || {};
  const storage = meta.storage || meta.memory_gb || item.storage || item.memory_gb;
  if (!storage) return "";
  const raw = String(storage);
  if (/gb$/i.test(raw)) return raw.toUpperCase();
  const num = parseInt(raw, 10);
  if (!Number.isNaN(num)) return `${num}GB`;
  return "";
}

function getSim(item) {
  const meta = item.meta || {};
  const sim = meta.sim || item.sim || "";
  if (!sim || sim === "unknown") return "";
  return sim;
}

function getColor(item) {
  const meta = item.meta || {};
  return meta.color || meta.color_ru || item.color || item.color_ru || "";
}

function buildMetaLine(item) {
  const parts = [getStorage(item), getSim(item), getColor(item)].filter(Boolean);
  return parts.join(" • ");
}

function buildTitleParts(item) {
  const meta = item.meta || {};
  const model = meta.model || item.model || "";
  const storage = getStorage(item);
  const color = getColor(item);
  const main = [model, storage].filter(Boolean).join(" ").trim();
  return {
    main: main || formatTitle(item.title),
    sub: color || "",
  };
}

function normalize(text) {
  return String(text || "").toLowerCase();
}

function loadCart() {
  try {
    const raw = localStorage.getItem("qb_cart");
    return raw ? JSON.parse(raw) : { items: [] };
  } catch {
    return { items: [] };
  }
}

function saveCart() {
  localStorage.setItem("qb_cart", JSON.stringify(state.cart));
}

function updateCartBadge() {
  const count = state.cart.items.reduce((sum, it) => sum + it.qty, 0);
  cartCountEl.textContent = count;
}

function updateCartTotal() {
  const total = state.cart.items.reduce((sum, it) => sum + it.price * it.qty, 0);
  cartTotalEl.textContent = `${formatPrice(total)} ₽`;
}

function renderCart() {
  cartItemsEl.innerHTML = "";
  state.cart.items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "cart-item";

    const img = document.createElement("img");
    img.className = "cart-thumb";
    img.src = item.image || "assets/placeholder.png";
    img.alt = item.title;
    img.onerror = () => {
      img.src = "assets/placeholder.png";
    };

    const info = document.createElement("div");
    info.className = "cart-info";

    const name = document.createElement("div");
    name.className = "cart-name";
    name.textContent = item.title;

    const meta = document.createElement("div");
    meta.className = "cart-meta";
    meta.textContent = item.meta || "";

    info.appendChild(name);
    info.appendChild(meta);

    const right = document.createElement("div");
    right.className = "cart-right";

    const price = document.createElement("div");
    price.className = "cart-price";
    price.textContent = `${formatPrice(item.price)} ₽`;

    const qtyControls = document.createElement("div");
    qtyControls.className = "qty-controls";

    const minus = document.createElement("button");
    minus.className = "qty-btn";
    minus.textContent = "-";
    minus.onclick = () => updateQty(item.id, item.qty - 1);

    const qty = document.createElement("div");
    qty.textContent = item.qty;

    const plus = document.createElement("button");
    plus.className = "qty-btn";
    plus.textContent = "+";
    plus.onclick = () => updateQty(item.id, item.qty + 1);

    qtyControls.append(minus, qty, plus);
    right.append(price, qtyControls);

    row.append(img, info, right);
    cartItemsEl.appendChild(row);
  });

  updateCartBadge();
  updateCartTotal();
  checkoutBtn.disabled = state.cart.items.length === 0;
}

function updateQty(id, qty) {
  const idx = state.cart.items.findIndex((it) => it.id === id);
  if (idx === -1) return;
  if (qty <= 0) {
    state.cart.items.splice(idx, 1);
  } else {
    state.cart.items[idx].qty = qty;
  }
  saveCart();
  renderCart();
}

function addToCart(item, btn) {
  const cleanTitle = formatTitle(item.title);
  const existing = state.cart.items.find((it) => it.id === item.id);
  if (existing) {
    existing.qty += 1;
  } else {
    state.cart.items.push({
      id: item.id,
      title: cleanTitle,
      price: item.price,
      qty: 1,
      image: item.image,
      meta: buildMetaLine(item),
    });
  }
  saveCart();
  renderCart();

  if (btn) {
    if (btn._timer) {
      clearTimeout(btn._timer);
    }
    btn.textContent = "Добавлено";
    btn.classList.add("added");
    btn.disabled = true;
    btn._timer = setTimeout(() => {
      btn.textContent = "В корзину";
      btn.classList.remove("added");
      btn.disabled = false;
      btn._timer = null;
    }, 900);
  }

  if (window.Telegram?.WebApp?.HapticFeedback) {
    window.Telegram.WebApp.HapticFeedback.impactOccurred("light");
  }
}

function openDrawer() {
  cartDrawer.classList.add("open");
  drawerBackdrop.classList.add("open");
}

function closeDrawer() {
  cartDrawer.classList.remove("open");
  drawerBackdrop.classList.remove("open");
}

function openLeadModal() {
  leadHint.classList.remove("show");
  leadModal.classList.add("open");
  leadBackdrop.classList.add("open");
  updateLeadState();
  setTimeout(() => leadName.focus(), 0);
}

function closeLeadModal() {
  leadModal.classList.remove("open");
  leadBackdrop.classList.remove("open");
}

function normalizePhone(value) {
  return String(value || "").replace(/\D/g, "");
}

function updateLeadState() {
  if (!isMiniAppReady()) {
    leadSend.disabled = true;
    return;
  }
  const nameOk = leadName.value.trim().length >= 2;
  const phoneOk = normalizePhone(leadPhone.value).length >= 10;
  leadSend.disabled = !(nameOk && phoneOk && state.cart.items.length);
}

function makeOrderId() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const ts = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
  const rand = Math.random().toString(36).slice(2, 6).toUpperCase();
  return `QB-${ts}-${rand}`;
}

function renderItems(items) {
  grid.innerHTML = "";
  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "product-card";

    const media = document.createElement("div");
    media.className = "card-media";

    const img = document.createElement("img");
    img.src = item.image || "assets/placeholder.png";
    img.alt = item.title;
    img.onerror = () => {
      img.src = "assets/placeholder.png";
    };
    media.appendChild(img);

    const body = document.createElement("div");
    body.className = "card-body";

    const title = document.createElement("div");
    title.className = "card-title";
    const titleParts = buildTitleParts(item);

    const titleMain = document.createElement("div");
    titleMain.className = "title-main";
    titleMain.textContent = titleParts.main;

    const titleSub = document.createElement("div");
    titleSub.className = "title-sub";
    titleSub.textContent = titleParts.sub;

    title.append(titleMain, titleSub);

    const meta = document.createElement("div");
    meta.className = "card-meta";
    meta.textContent = buildMetaLine(item);

    const footer = document.createElement("div");
    footer.className = "card-footer";

    const price = document.createElement("div");
    price.className = "card-price";
    price.innerHTML = `${formatPrice(item.price)}<span class="currency">₽</span>`;

    const btn = document.createElement("button");
    btn.className = "add-btn";
    btn.textContent = "В корзину";
    btn.onclick = () => addToCart(item, btn);

    footer.append(price, btn);
    body.append(title, meta, footer);
    card.append(media, body);
    grid.appendChild(card);
  });
}

function applyFilters() {
  const q = normalize(searchInput.value);
  const model = modelFilter.value;
  let result = state.baseItems.filter((item) => {
    if (model && item.meta?.model !== model) return false;
    if (!q) return true;
    const hay = [
      item.title,
      item.meta?.model,
      item.meta?.storage,
      item.meta?.sim,
      item.meta?.color,
    ]
      .filter(Boolean)
      .map(normalize)
      .join(" ");
    return hay.includes(q);
  });

  const sort = sortFilter.value;
  if (sort === "cheap") {
    result = result.slice().sort((a, b) => a.price - b.price);
  } else if (sort === "expensive") {
    result = result.slice().sort((a, b) => b.price - a.price);
  } else if (sort === "new") {
    result = result.slice().sort((a, b) => (b.updated_ts || 0) - (a.updated_ts || 0));
  } else if (sort === "memory") {
    result = result.slice().sort((a, b) => {
      const am = parseInt(String(a.meta?.storage || "").replace(/\D/g, ""), 10) || 0;
      const bm = parseInt(String(b.meta?.storage || "").replace(/\D/g, ""), 10) || 0;
      return am - bm;
    });
  }

  state.items = result;
  renderItems(state.items);
}

async function loadCatalog() {
  const res = await fetch("products.json", { cache: "no-store" });
  const data = await res.json();
  state.baseItems = data.items || [];

  const models = Array.from(
    new Set(state.baseItems.map((it) => it.meta?.model).filter(Boolean))
  ).sort();

  modelFilter.innerHTML = '<option value="">Все модели</option>';
  models.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    modelFilter.appendChild(opt);
  });

  applyFilters();
}

searchInput.addEventListener("input", applyFilters);
modelFilter.addEventListener("change", applyFilters);
sortFilter.addEventListener("change", applyFilters);

cartBtn.addEventListener("click", () => {
  renderCart();
  openDrawer();
});

drawerBackdrop.addEventListener("click", closeDrawer);
drawerClose.addEventListener("click", closeDrawer);

clearCartBtn.addEventListener("click", () => {
  state.cart.items = [];
  saveCart();
  renderCart();
});

checkoutBtn.addEventListener("click", () => {
  if (state.cart.items.length === 0) {
    return;
  }
  openLeadModal();
});

window.addEventListener("scroll", () => {
  if (window.scrollY > 600) {
    scrollTopBtn.classList.add("show");
  } else {
    scrollTopBtn.classList.remove("show");
  }
});

leadBackdrop.addEventListener("click", closeLeadModal);
leadCancel.addEventListener("click", closeLeadModal);
leadName.addEventListener("input", updateLeadState);
leadPhone.addEventListener("input", updateLeadState);
leadComment.addEventListener("input", updateLeadState);
leadTg.addEventListener("change", updateLeadState);

leadSend.addEventListener("click", async () => {
  console.log("CLICK submit");
  const name = leadName.value.trim();
  const phoneRaw = leadPhone.value.trim();
  const phoneDigits = normalizePhone(phoneRaw);
  if (name.length < 2 || phoneDigits.length < 10 || state.cart.items.length === 0) {
    updateLeadState();
    return;
  }

  leadSend.disabled = true;
  leadSend.textContent = "Отправка...";

  const total = state.cart.items.reduce((sum, it) => sum + it.price * it.qty, 0);
  const localCtx = await waitForInitData();
  const tgUser = localCtx.user || {};
  const payload = {
    type: "lead_order",
    order_id: makeOrderId(),
    ts: Date.now(),
    name,
    phone: phoneRaw,
    comment: leadComment.value.trim() || "",
    items: state.cart.items.map((it) => ({
      id: it.id,
      title: it.title,
      price: it.price,
      qty: it.qty,
    })),
    total,
    source: {
      webapp: true,
      page_url: location.href,
      build: BUILD_ID,
    },
    tg_user_id: tgUser.id ?? null,
    tg_username: tgUser.username ?? null,
    tg_first_name: tgUser.first_name ?? null,
    tg_last_name: tgUser.last_name ?? null,
  };

  try {
    await sendRelay(payload);
    if (localCtx.tg?.HapticFeedback) {
      localCtx.tg.HapticFeedback.notificationOccurred("success");
    }
    leadHint.textContent = "✅ Заявка отправлена";
    leadHint.classList.add("show");
    state.cart.items = [];
    saveCart();
    renderCart();
    if (localCtx.tg?.showPopup) {
      localCtx.tg.showPopup({ message: "✅ Заявка отправлена" });
    } else if (localCtx.tg?.showAlert) {
      localCtx.tg.showAlert("✅ Заявка отправлена");
    }
    setTimeout(() => {
      closeLeadModal();
      closeDrawer();
      leadHint.classList.remove("show");
      localCtx.tg?.close?.();
      leadSend.textContent = "Отправить заявку";
    }, 200);
  } catch {
    leadHint.textContent = "Ошибка отправки, попробуйте еще раз";
    leadHint.classList.add("show");
    leadSend.disabled = false;
    leadSend.textContent = "Отправить заявку";
  }
});

scrollTopBtn.addEventListener("click", () => {
  window.scrollTo({ top: 0, behavior: "smooth" });
});

renderCart();
loadCatalog();
