// Shared catalogue and cart for the mock shop. The cart lives in localStorage (per browser profile).
var PRODUCTS = [
  { id: "cane", name: "Folding white cane", price: 649 },
  { id: "watch", name: "Talking wrist watch", price: 899 },
  { id: "calc", name: "Talking calculator", price: 499 },
  { id: "book", name: "Braille story book", price: 249 },
];

var Cart = {
  KEY: "mockshop.cart",
  load: function () {
    try { return JSON.parse(localStorage.getItem(Cart.KEY)) || {}; } catch (e) { return {}; }
  },
  save: function (cart) {
    try { localStorage.setItem(Cart.KEY, JSON.stringify(cart)); } catch (e) { /* storage blocked */ }
  },
  add: function (id) { var c = Cart.load(); c[id] = (c[id] || 0) + 1; Cart.save(c); },
  remove: function (id) { var c = Cart.load(); delete c[id]; Cart.save(c); },
  clear: function () { Cart.save({}); },
  lines: function () {
    var c = Cart.load();
    return PRODUCTS.filter(function (p) { return c[p.id]; })
      .map(function (p) { return { product: p, qty: c[p.id], total: p.price * c[p.id] }; });
  },
  count: function () { return Cart.lines().reduce(function (n, l) { return n + l.qty; }, 0); },
  total: function () { return Cart.lines().reduce(function (n, l) { return n + l.total; }, 0); },
};

function rupees(n) { return "Rs " + n.toLocaleString("en-IN"); }

function showCartCount() {
  var el = document.getElementById("cart-count");
  if (el) el.textContent = "Cart (" + Cart.count() + ")";
}
