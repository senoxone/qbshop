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
const tgStatus = document.getElementById("tgStatus");
const leadBackdrop = document.getElementById("leadBackdrop");
const leadModal = document.getElementById("leadModal");
const leadName = document.getElementById("leadName");
const leadPhone = document.getElementById("leadPhone");
const leadComment = document.getElementById("leadComment");
const leadTg = document.getElementById("leadTg");
const leadHint = document.getElementById("leadHint");
const leadCancel = document.getElementById("leadCancel");
const leadSend = document.getElementById("leadSend");

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
const tgReady = Boolean(tg);
if (tgStatus) {
  tgStatus.textContent = tgReady ? "TG: OK" : "TG: NO";
  tgStatus.title = `qid=${ctx.qid ? String(ctx.qid).slice(0, 10) : "none"} host=${location.hostname}`;
}
try {
  tg?.ready();
  tg?.expand();
} catch {}

const urlParams = new URLSearchParams(location.search);
const debugEnabled = urlParams.get("debug") === "1" || localStorage.getItem("DEBUG") === "1";
const debugBot = urlParams.get("bot") || "";
const debugNonce = urlParams.get("nonce") || "";
const debugPanel = document.getElementById("debugPanel");
const debugInfo = document.getElementById("debugInfo");
const debugStatus = document.getElementById("debugStatus");
const debugCopy = document.getElementById("debugCopy");
const debugTest = document.getElementById("debugTest");
const MINI_APP_ERROR = "Открыто НЕ как Mini App. Открой через кнопку бота.";

function isMiniAppReady() {
  const local = getTgContext();
  return Boolean(local.tg && local.initData);
}

function getBotUsername() {
  let value = debugBot || "";
  if (value.startsWith("@")) value = value.slice(1);
  return value;
}

function buildDeepLink(nonce) {
  const botName = getBotUsername();
  if (!botName) return "";
  const token = nonce || "1";
  return `https://t.me/${botName}?startapp=${encodeURIComponent(token)}`;
}

function openViaDeepLink() {
  const link = buildDeepLink(debugNonce);
  if (!link) return;
  const local = getTgContext();
  if (local.tg?.openTelegramLink) {
    local.tg.openTelegramLink(link);
  } else {
    window.location.href = link;
  }
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
    if (debugTest) debugTest.disabled = false;
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
  if (checkoutBtn) checkoutBtn.disabled = true;
  if (leadSend) leadSend.disabled = true;
  if (debugTest) debugTest.disabled = false;
}

function setDebugStatus(text) {
  if (debugStatus) debugStatus.textContent = text;
}

function debugAlert(message) {
  if (!debugEnabled) return;
  const local = getTgContext();
  if (local.tg?.showAlert) {
    local.tg.showAlert(message);
  } else if (local.tg?.showPopup) {
    local.tg.showPopup({ message });
  }
}

function renderDebugInfo() {
  if (!debugInfo) return;
  const local = getTgContext();
  const info = [
    `TG_API: ${local.tg ? "OK" : "NO"}`,
    `initData: ${local.initData?.length || 0}`,
    `qid: ${local.qid ? String(local.qid).slice(0, 10) : "none"}`,
    `user: ${local.user?.id || "none"}`,
    `bot: ${debugBot || "none"}`,
    `nonce: ${debugNonce || "none"}`,
    `platform: ${local.tg?.platform || "n/a"}`,
    `version: ${local.tg?.version || "n/a"}`,
  ].join(" | ");
  debugInfo.textContent = info;
}

if (debugEnabled && debugPanel) {
  debugPanel.classList.add("show");
  renderDebugInfo();
  setDebugStatus(tgReady ? "READY" : "NO TG");
}

if (debugPanel) {
  const debugActions = debugPanel.querySelector(".debug-actions");
  if (debugActions) {
    const openBtn = document.createElement("button");
    openBtn.className = "debug-btn";
    openBtn.textContent = "OPEN VIA BOT";
    openBtn.addEventListener("click", openViaDeepLink);
    debugActions.appendChild(openBtn);
  }
}

applyMiniAppLock();
let miniCheckCount = 0;
const miniCheckTimer = setInterval(() => {
  applyMiniAppLock();
  if (debugEnabled) renderDebugInfo();
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
  checkoutBtn.disabled = !isMiniAppReady() || state.cart.items.length === 0;
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
  if (!isMiniAppReady()) {
    leadHint.textContent = MINI_APP_ERROR;
    leadHint.style.color = "#ff5a5a";
    leadHint.classList.add("show");
    leadSend.disabled = true;
    return;
  }
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
    bot: debugBot || null,
    nonce: debugNonce || null,
    order_id: makeOrderId(),
    ts: Date.now(),
    contact: {
      name,
      phone: phoneRaw,
      comment: leadComment.value.trim() || "",
    },
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
    },
    tg_user: {
      id: tgUser.id ?? null,
      username: tgUser.username ?? null,
      first_name: tgUser.first_name ?? null,
      last_name: tgUser.last_name ?? null,
    },
  };

  console.log(
    "tg exists",
    !!localCtx.tg,
    "initData",
    localCtx.initData?.length,
    "initDataUnsafe",
    localCtx.tg?.initDataUnsafe
  );
  if (debugEnabled) {
    setDebugStatus("SENDING...");
  }

  const payloadStr = JSON.stringify(payload);
  console.log("PAYLOAD", payloadStr);
  if (!localCtx.tg) {
    leadHint.textContent = MINI_APP_ERROR;
    leadHint.classList.add("show");
    leadSend.disabled = false;
    leadSend.textContent = "Отправить заявку";
    if (debugEnabled) {
      setDebugStatus("NO TG");
    }
    return;
  }
  if (!localCtx.initData) {
    leadHint.textContent = MINI_APP_ERROR;
    leadHint.classList.add("show");
    leadSend.disabled = false;
    leadSend.textContent = "Отправить заявку";
    if (debugEnabled) {
      setDebugStatus("NO INIT_DATA");
    }
    return;
  }
  if (payloadStr.length > 3800) {
    leadHint.textContent = "Слишком большой заказ, уберите часть позиций";
    leadHint.classList.add("show");
    leadSend.disabled = false;
    leadSend.textContent = "Отправить заявку";
    if (debugEnabled) {
      setDebugStatus("PAYLOAD TOO LARGE");
    }
    return;
  }
  try {
    debugAlert(`DEBUG: sendData called nonce=${debugNonce || "none"} len=${payloadStr.length}`);
    localCtx.tg.sendData(payloadStr);
    debugAlert("DEBUG: sendData done");
    if (localCtx.tg?.HapticFeedback) {
      localCtx.tg.HapticFeedback.notificationOccurred("success");
    }
    leadHint.textContent = "Заявка отправлена, менеджер свяжется";
    leadHint.classList.add("show");
    state.cart.items = [];
    saveCart();
    renderCart();
    if (debugEnabled) {
      setDebugStatus("SENT");
    }
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
    }, 200);
  } catch {
    leadHint.textContent = "Не удалось отправить заявку, попробуйте еще раз";
    leadHint.classList.add("show");
    leadSend.disabled = false;
    leadSend.textContent = "Отправить заявку";
    if (debugEnabled) {
      setDebugStatus("SEND FAILED");
    }
  }
});

scrollTopBtn.addEventListener("click", () => {
  window.scrollTo({ top: 0, behavior: "smooth" });
});

if (debugEnabled) {
  debugCopy?.addEventListener("click", async () => {
    renderDebugInfo();
    const text = debugInfo?.textContent || "";
    try {
      await navigator.clipboard.writeText(text);
      setDebugStatus("COPIED");
    } catch {
      setDebugStatus("COPY FAILED");
    }
  });

  debugTest?.addEventListener("click", async () => {
    const payload = JSON.stringify({ type: "ping", bot: debugBot || null, nonce: debugNonce || null, ts: Date.now() });
    const local = await waitForInitData();
    if (!local.tg) {
      setDebugStatus("NO TG");
      return;
    }
    if (!local.initData) {
      setDebugStatus("NO INIT_DATA");
      return;
    }
    setDebugStatus("TEST SENDING...");
    try {
      debugAlert(`DEBUG: sendData called nonce=${debugNonce || "none"} len=${payload.length}`);
      local.tg.sendData(payload);
      setDebugStatus("TEST SENT");
      setTimeout(() => {
        local.tg?.close?.();
      }, 200);
    } catch {
      setDebugStatus("TEST FAILED");
    }
  });
}

renderCart();
loadCatalog();
