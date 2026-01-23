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

const state = {
  baseItems: [],
  items: [],
  cart: loadCart(),
};

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

function addToCart(item) {
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
}

function openDrawer() {
  cartDrawer.classList.add("open");
  drawerBackdrop.classList.add("open");
}

function closeDrawer() {
  cartDrawer.classList.remove("open");
  drawerBackdrop.classList.remove("open");
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
    title.textContent = formatTitle(item.title);

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
    btn.onclick = () => addToCart(item);

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
  const total = state.cart.items.reduce((sum, it) => sum + it.price * it.qty, 0);
  const payload = {
    items: state.cart.items.map((it) => ({
      id: it.id,
      title: it.title,
      price: it.price,
      qty: it.qty,
    })),
    total,
    ts: Math.floor(Date.now() / 1000),
    tg_user: window.Telegram?.WebApp?.initDataUnsafe?.user || null,
  };

  if (window.Telegram?.WebApp?.sendData) {
    tgHint.classList.remove("show");
    window.Telegram.WebApp.sendData(JSON.stringify(payload));
  } else {
    tgHint.classList.add("show");
  }
});

window.addEventListener("scroll", () => {
  if (window.scrollY > 600) {
    scrollTopBtn.classList.add("show");
  } else {
    scrollTopBtn.classList.remove("show");
  }
});

scrollTopBtn.addEventListener("click", () => {
  window.scrollTo({ top: 0, behavior: "smooth" });
});

renderCart();
loadCatalog();
