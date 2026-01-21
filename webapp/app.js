const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

const el = (id) => document.getElementById(id);

const state = {
  products: [],
  filtered: [],
  cart: loadCart(),
};

function loadCart(){
  try { return JSON.parse(localStorage.getItem("cart")||"{}"); } catch { return {}; }
}
function saveCart(){
  localStorage.setItem("cart", JSON.stringify(state.cart));
  renderCartBadge();
}
function cartCount(){
  return Object.values(state.cart).reduce((s,it)=>s+Number(it.qty||0),0);
}
function cartTotal(){
  return Object.values(state.cart).reduce((s,it)=>s+Number(it.qty||0)*Number(it.price||0),0);
}
function money(x){
  return new Intl.NumberFormat("ru-RU").format(x) + " ₽";
}

async function loadProducts(){
  const r = await fetch("products.json?ts=" + Date.now());
  state.products = await r.json();
  state.filtered = state.products.slice();
  buildModelFilter();
  render();
  renderCart();
  renderCartBadge();
}

function buildModelFilter(){
  const models = [...new Set(state.products.map(p=>p.model).filter(Boolean))].sort();
  const sel = el("filterModel");
  for (const m of models){
    const o = document.createElement("option");
    o.value = m; o.textContent = m;
    sel.appendChild(o);
  }
}

function applyFilters(){
  const q = el("q").value.trim().toLowerCase();
  const model = el("filterModel").value;
  const cond = el("filterCond").value;

  state.filtered = state.products.filter(p=>{
    if (model && p.model !== model) return false;
    if (cond && (p.condition||"").toUpperCase() !== cond) return false;
    if (!q) return true;

    const hay = [p.title, p.model, p.storage, p.color, String(p.battery||""), p.condition]
      .join(" ").toLowerCase();
    return hay.includes(q);
  });
  render();
}

function addToCart(prod){
  const id = prod.id;
  if (!state.cart[id]) state.cart[id] = {...prod, qty: 0};
  state.cart[id].qty += 1;
  saveCart();
  renderCart();
}

function decFromCart(id){
  if (!state.cart[id]) return;
  state.cart[id].qty -= 1;
  if (state.cart[id].qty <= 0) delete state.cart[id];
  saveCart();
  renderCart();
}
function incFromCart(id){
  if (!state.cart[id]) return;
  state.cart[id].qty += 1;
  saveCart();
  renderCart();
}
function clearCart(){
  state.cart = {};
  saveCart();
  renderCart();
}

function render(){
  const grid = el("grid");
  grid.innerHTML = "";
  if (!state.filtered.length){
    grid.innerHTML = `<div class="meta" style="padding:10px;color:#8b8e9b">Ничего не найдено</div>`;
    return;
  }

  for (const p of state.filtered){
    const card = document.createElement("div");
    card.className = "card";
    const img = (p.photos && p.photos[0]) ? p.photos[0] : "https://placehold.co/600x750/png";
    const meta = `${p.storage || ""} • АКБ ${p.battery || "?"}% • ${p.color || ""} • ${String(p.condition||"").toUpperCase() || ""}`
      .replace(/\s•\s/g," • ").trim();

    card.innerHTML = `
      <div class="photo"><img src="${img}" alt="" referrerpolicy="no-referrer" loading="lazy"></div>
      <div class="p">
        <div class="h">${escapeHtml(p.title || p.model || "iPhone")}</div>
        <div class="meta">${escapeHtml(meta)}</div>
        <div class="priceRow">
          <div class="price">${money(Number(p.price||0))}</div>
          <button class="smallbtn">В корзину</button>
        </div>
      </div>
    `;
    card.querySelector("button").addEventListener("click", ()=>addToCart(p));
    grid.appendChild(card);
  }
}

function renderCartBadge(){
  el("cartCount").textContent = cartCount();
}

function renderCart(){
  const box = el("cartItems");
  box.innerHTML = "";

  const items = Object.values(state.cart);
  if (!items.length){
    box.innerHTML = `<div class="meta" style="padding:12px;color:#8b8e9b">Корзина пустая</div>`;
    el("total").textContent = money(0);
    return;
  }

  for (const it of items){
    const row = document.createElement("div");
    row.className = "cartItem";
    const img = (it.photos && it.photos[0]) ? it.photos[0] : "https://placehold.co/600x750/png";
    const meta = `${it.storage || ""} • АКБ ${it.battery || "?"}% • ${it.color || ""} • ${String(it.condition||"").toUpperCase() || ""}`
      .replace(/\s•\s/g," • ").trim();

    row.innerHTML = `
      <div class="thumb"><img src="${img}" alt="" referrerpolicy="no-referrer" loading="lazy"></div>
      <div>
        <div class="cTitle">${escapeHtml(it.title || "iPhone")}</div>
        <div class="cMeta">${escapeHtml(meta)}</div>
      </div>
      <div class="cRight">
        <div class="cTitle">${money(Number(it.price||0))}</div>
        <div class="qtyRow">
          <button class="qbtn" data-act="dec">-</button>
          <div>${it.qty}</div>
          <button class="qbtn" data-act="inc">+</button>
        </div>
      </div>
    `;
    row.querySelector('[data-act="dec"]').addEventListener("click", ()=>decFromCart(it.id));
    row.querySelector('[data-act="inc"]').addEventListener("click", ()=>incFromCart(it.id));
    box.appendChild(row);
  }

  el("total").textContent = money(cartTotal());
}

function openDrawer(){
  el("drawer").classList.add("show");
  tg?.HapticFeedback?.impactOccurred("light");
}
function closeDrawer(){ el("drawer").classList.remove("show"); }

function openModal(){ el("modal").classList.add("show"); }
function closeModal(){ el("modal").classList.remove("show"); }

function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, (c)=>({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;" }[c]));
}

function checkout(){
  if (!Object.keys(state.cart).length){
    tg?.showAlert?.("Корзина пустая");
    return;
  }
  openModal();
}

function sendOrder(){
  const name = el("name").value.trim();
  const phone = el("phone").value.trim();
  const comment = el("comment").value.trim();

  const items = Object.values(state.cart).map(it=>({
    id: it.id,
    title: it.title,
    price: it.price,
    qty: it.qty
  }));

  const order = {
    items,
    total: cartTotal(),
    contact: { name, phone, comment },
    tg_user: tg?.initDataUnsafe?.user || null
  };

  if (!tg){
    alert("Открой страницу внутри Telegram (Mini App).");
    return;
  }

  tg.sendData(JSON.stringify(order));
  clearCart();
  closeModal();
  closeDrawer();
  tg.showPopup({title:"✅ Готово", message:"Заказ отправлен администратору. Скоро с вами свяжутся."});
}

function bind(){
  el("openCart").addEventListener("click", openDrawer);
  el("closeCart").addEventListener("click", closeDrawer);
  el("drawer").addEventListener("click", (e)=>{ if (e.target.id === "drawer") closeDrawer(); });

  el("closeModal").addEventListener("click", closeModal);
  el("modal").addEventListener("click", (e)=>{ if (e.target.id === "modal") closeModal(); });

  el("checkout").addEventListener("click", checkout);
  el("send").addEventListener("click", sendOrder);
  el("clear").addEventListener("click", clearCart);

  el("q").addEventListener("input", applyFilters);
  el("filterModel").addEventListener("change", applyFilters);
  el("filterCond").addEventListener("change", applyFilters);

  const u = tg?.initDataUnsafe?.user;
  if (u) el("hello").textContent = `Привет, ${u.first_name || "друг"}!`;
}

bind();
loadProducts();
