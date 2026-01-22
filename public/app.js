/* global Telegram */

const state = {
  items: [],
  cart: {},
};

const grid = document.getElementById("grid");
const searchInput = document.getElementById("searchInput");
const sortSelect = document.getElementById("sortSelect");
const cartButton = document.getElementById("cartButton");
const cartDrawer = document.getElementById("cartDrawer");
const cartClose = document.getElementById("cartClose");
const cartItems = document.getElementById("cartItems");
const cartCount = document.getElementById("cartCount");
const cartTotal = document.getElementById("cartTotal");
const checkoutBtn = document.getElementById("checkoutBtn");

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
    const row = document.createElement("div");
    row.className = "cart-item";
    row.innerHTML = `
      <div class="cart-item-name">${item.title}</div>
      <div class="qty">
        <button data-id="${item.id}" data-delta="-1">-</button>
        <span>${qty}</span>
        <button data-id="${item.id}" data-delta="1">+</button>
      </div>
      <div>${fmt.format(item.price * qty)} ₽</div>
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
  let items = state.items.filter((it) => it.title.toLowerCase().includes(q));

  const sort = sortSelect.value;
  items = items.slice().sort((a, b) => {
    if (sort === "price_desc") return b.price - a.price;
    if (sort === "title") return a.title.localeCompare(b.title);
    return a.price - b.price;
  });

  grid.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <img src="${item.image}" alt="${item.title}" loading="lazy" />
      <div class="card-body">
        <div class="card-title">${item.title}</div>
        <div class="card-price">${fmt.format(item.price)} ₽</div>
        <button class="card-btn" data-id="${item.id}">В корзину</button>
      </div>
    `;
    grid.appendChild(card);
  }
}

async function loadProducts() {
  const res = await fetch(`products.json?ts=${Date.now()}`);
  const data = await res.json();
  state.items = data.items || [];
  renderGrid();
  renderCart();
}

function openCart() {
  cartDrawer.classList.add("open");
}

function closeCart() {
  cartDrawer.classList.remove("open");
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
    tg_user: (window.Telegram && Telegram.WebApp && Telegram.WebApp.initDataUnsafe)
      ? Telegram.WebApp.initDataUnsafe.user || null
      : null,
  };

  if (window.Telegram && Telegram.WebApp) {
    Telegram.WebApp.sendData(JSON.stringify(payload));
  } else {
    alert("Заказ: " + JSON.stringify(payload, null, 2));
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
searchInput.addEventListener("input", renderGrid);
sortSelect.addEventListener("change", renderGrid);

loadCart();
loadProducts();

if (window.Telegram && Telegram.WebApp) {
  Telegram.WebApp.ready();
  Telegram.WebApp.expand();
}
