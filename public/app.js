/* global Telegram */

const state = {
  items: [],
  cart: {},
};

const grid = document.getElementById("grid");
const searchInput = document.getElementById("searchInput");
const modelSelect = document.getElementById("modelSelect");
const sortSelect = document.getElementById("sortSelect");
const cartButton = document.getElementById("cartButton");
const cartDrawer = document.getElementById("cartDrawer");
const cartClose = document.getElementById("cartClose");
const cartItems = document.getElementById("cartItems");
const cartCount = document.getElementById("cartCount");
const cartTotal = document.getElementById("cartTotal");
const checkoutBtn = document.getElementById("checkoutBtn");
const clearBtn = document.getElementById("clearBtn");
const scrollTopBtn = document.getElementById("scrollTopBtn");

const fmt = new Intl.NumberFormat("ru-RU");

function loadCart() {
  try {
    state.cart = JSON.parse(localStorage.getItem("cart") || "{}");
  } catch {
    state.cart = {};
  }
}

function saveCart() {
  localStorage.setItem("cart", JSON.stringify(state.cart));
}

function cleanValue(value) {
  if (!value) return "";
  const s = String(value).trim();
  if (!s || s.toLowerCase() === "unknown") return "";
  return s;
}

function getMemoryGB(item) {
  const meta = item.meta || {};
  if (meta.memory_gb) return Number(meta.memory_gb);
  const fromStorage = String(item.storage || "").match(/(\d{2,4})/);
  if (fromStorage) return Number(fromStorage[1]);
  const fromTitle = String(item.title || "").match(/(\d{2,4})\s*GB/i);
  return fromTitle ? Number(fromTitle[1]) : 0;
}

function buildMetaLine(item) {
  const meta = item.meta || {};
  let storage = cleanValue(meta.memory_gb ? `${meta.memory_gb}GB` : item.storage);
  if (!storage) {
    const mem = getMemoryGB(item);
    storage = mem ? `${mem}GB` : "";
  }
  const sim = cleanValue(meta.sim || item.sim);
  const color = cleanValue(meta.color_en || meta.color_ru || item.color || item.color_ru);
  return [storage, sim, color].filter(Boolean).join(" • ");
}

function buildSearchText(item) {
  const meta = item.meta || {};
  const parts = [
    item.title,
    item.model,
    meta.model,
    item.storage,
    meta.memory_gb ? `${meta.memory_gb}GB` : "",
    item.color,
    meta.color_en,
    meta.color_ru,
    item.sim,
    meta.sim,
    item.condition,
  ];
  return parts.filter(Boolean).join(" ").toLowerCase();
}

function cartSummary() {
  let count = 0;
  let total = 0;
  for (const item of state.items) {
    const qty = state.cart[item.id] || 0;
    if (!qty) continue;
    count += qty;
    total += item.price * qty;
  }
  cartCount.textContent = count;
  cartTotal.textContent = fmt.format(total);
  return { count, total };
}

function renderCart() {
  cartItems.innerHTML = "";
  for (const item of state.items) {
    const qty = state.cart[item.id] || 0;
    if (!qty) continue;
    const metaLine = buildMetaLine(item);
    const row = document.createElement("div");
    row.className = "cart-item";
    row.innerHTML = `
      <img src="${item.image}" alt="${item.title}" />
      <div>
        <div class="cart-item-title">${item.title}</div>
        <div class="cart-item-meta">${metaLine}</div>
        <div class="qty">
          <button data-id="${item.id}" data-delta="-1">-</button>
          <span>${qty}</span>
          <button data-id="${item.id}" data-delta="1">+</button>
        </div>
      </div>
      <div class="cart-item-price">${fmt.format(item.price * qty)} ₽</div>
    `;
    cartItems.appendChild(row);
  }
  cartSummary();
}

function updateCart(id, delta) {
  const next = (state.cart[id] || 0) + delta;
  if (next <= 0) {
    delete state.cart[id];
  } else {
    state.cart[id] = next;
  }
  saveCart();
  renderCart();
}

function renderGrid() {
  const q = (searchInput.value || "").trim().toLowerCase();
  const selectedModel = modelSelect.value || "";
  let items = state.items.slice();

  if (q) {
    items = items.filter((it) => buildSearchText(it).includes(q));
  }

  if (selectedModel) {
    items = items.filter((it) => (it.meta?.model || it.model || "") === selectedModel);
  }

  const sort = sortSelect.value;
  items = items.slice().sort((a, b) => {
    if (sort === "popular") return 0;
    if (sort === "price_desc") return b.price - a.price;
    if (sort === "updated_desc") return (b.updated_ts || 0) - (a.updated_ts || 0);
    if (sort === "memory_desc") return getMemoryGB(b) - getMemoryGB(a);
    return a.price - b.price;
  });

  grid.innerHTML = "";
  for (const item of items) {
    const metaLine = buildMetaLine(item);
    const priceText = fmt.format(item.price);
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-media">
        <img src="${item.image}" alt="${item.title}" loading="lazy" />
      </div>
      <div class="card-body">
        <div class="card-title">${item.title}</div>
        <div class="card-meta">${metaLine}</div>
        <div class="card-actions">
          <div class="price">
            <div class="price-amount">${priceText}</div>
            <div class="price-currency">₽</div>
          </div>
          <button class="card-btn" data-id="${item.id}">В корзину</button>
        </div>
      </div>
    `;
    grid.appendChild(card);
  }
}

async function loadProducts() {
  const res = await fetch(`products.json?ts=${Date.now()}`);
  const data = await res.json();
  state.items = data.items || [];
  const models = Array.from(
    new Set(state.items.map((it) => (it.meta?.model || it.model || "").trim()).filter(Boolean))
  ).sort((a, b) => a.localeCompare(b));
  modelSelect.innerHTML = `<option value="">Все модели</option>`;
  for (const m of models) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    modelSelect.appendChild(opt);
  }
  renderGrid();
  renderCart();
}

function openCart() {
  cartDrawer.classList.add("open");
}

function closeCart() {
  cartDrawer.classList.remove("open");
}

function clearCart() {
  state.cart = {};
  saveCart();
  renderCart();
}

function checkout() {
  const orderItems = [];
  for (const item of state.items) {
    const qty = state.cart[item.id] || 0;
    if (qty) {
      orderItems.push({
        id: item.id,
        title: item.title,
        price: item.price,
        qty,
      });
    }
  }
  const payload = {
    items: orderItems,
    total: cartSummary().total,
    ts: Date.now(),
    tg_user:
      window.Telegram && Telegram.WebApp && Telegram.WebApp.initDataUnsafe
        ? Telegram.WebApp.initDataUnsafe.user || null
        : null,
  };

  if (window.Telegram && Telegram.WebApp) {
    Telegram.WebApp.sendData(JSON.stringify(payload));
  } else {
    alert("Заказ: " + JSON.stringify(payload, null, 2));
  }
}

function handleScroll() {
  if (window.scrollY > 600) {
    scrollTopBtn.classList.add("show");
  } else {
    scrollTopBtn.classList.remove("show");
  }
}

grid.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-id]");
  if (!btn) return;
  updateCart(btn.dataset.id, 1);
});

cartItems.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-id]");
  if (!btn) return;
  updateCart(btn.dataset.id, parseInt(btn.dataset.delta, 10));
});

cartButton.addEventListener("click", openCart);
cartClose.addEventListener("click", closeCart);
checkoutBtn.addEventListener("click", checkout);
clearBtn.addEventListener("click", clearCart);
searchInput.addEventListener("input", renderGrid);
sortSelect.addEventListener("change", renderGrid);
modelSelect.addEventListener("change", renderGrid);
scrollTopBtn.addEventListener("click", () => {
  window.scrollTo({ top: 0, behavior: "smooth" });
});
window.addEventListener("scroll", handleScroll);

loadCart();
loadProducts();

if (window.Telegram && Telegram.WebApp) {
  Telegram.WebApp.ready();
  Telegram.WebApp.expand();
}
