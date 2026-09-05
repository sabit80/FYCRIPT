
//Market · JS
/* =====================================================
   CRYPTOWALLET
   MARKET PAGE (Django API version)
 
   Rates now come from GET /api/rates/ — the public
   endpoint backed by wallet/views.py's EXCHANGE_RATES —
   instead of the local js/rates.js copy. Guests are
   allowed here too, same as before.
===================================================== */
 
 
const currentUserName =
    sessionStorage.getItem("userName");
 
 
 
/* =====================================================
   DOM
===================================================== */
 
const marketGrid =
    document.getElementById("marketGrid");
 
const avatar =
    document.getElementById("avatar");
 
const logout =
    document.getElementById("logout");
 
 
 
/* =====================================================
   DISPLAY META PER CURRENCY
 
   changePercent is a fixed, simulated 24h change — this
   is a demo wallet, not a live market feed (see the note
   on this page).
===================================================== */
 
const CURRENCY_META = {
 
    USD: { icon: "$", changePercent: 0 },
    BDT: { icon: "৳", changePercent: 0.4 },
    EUR: { icon: "€", changePercent: -0.6 },
    BTC: { icon: "₿", changePercent: 2.3 },
    ETH: { icon: "Ξ", changePercent: -1.1 },
    USDT: { icon: "₮", changePercent: 0.1 }
 
};
 
 
 
/* =====================================================
   AVATAR
===================================================== */
 
if (avatar) {
 
    avatar.textContent =
        currentUserName ? currentUserName.charAt(0).toUpperCase() : "G";
 
}
 
 
 
/* =====================================================
   RENDER MARKET GRID
===================================================== */
 
async function renderMarket() {
 
    if (!marketGrid) return;
 
    let rows;
 
    try {
 
        rows = await CryptoWalletAPI.request("/rates/", { auth: false });
 
    }
 
    catch (error) {
 
        marketGrid.innerHTML =
            "<div class=\"empty\"><strong>" + error.message + "</strong></div>";
        return;
 
    }
 
    /* The API returns a LIST of rate rows, e.g.
       [{ from_curr: "USD", to_curr: "BDT", rate: "120.00000000" }, ...]
       — not a flat { BDT: 120, ... } map. Build that map here
       before rendering (same conversion rates.js does). */
 
    const rates = { USD: 1 };
 
    rows.forEach(function(row) {
 
        if (row.from_curr === "USD") {
            rates[row.to_curr] = Number(row.rate);
        }
 
    });
 
    marketGrid.innerHTML = "";
 
    Object.keys(rates).forEach(function(currency) {
 
        const rate = rates[currency];
        const meta = CURRENCY_META[currency] || { icon: "◈", changePercent: 0 };
        const isUp = meta.changePercent >= 0;
 
        const card = document.createElement("div");
        card.className = "market-card";
 
        card.innerHTML =
            "<div class=\"symbol-row\">" +
                "<div class=\"symbol\">" +
                    "<span class=\"icon\">" + meta.icon + "</span>" +
                    "<span>" + currency + "</span>" +
                "</div>" +
                "<span class=\"change " + (isUp ? "up" : "down") + "\">" +
                    (isUp ? "▲ " : "▼ ") +
                    Math.abs(meta.changePercent).toFixed(1) + "%" +
                "</span>" +
            "</div>" +
            "<div class=\"rate\">" +
                (currency === "USD" ? "1.00" : rate.toFixed(currency === "BTC" || currency === "ETH" ? 8 : 2)) +
            "</div>" +
            "<div class=\"rate-label\">" +
                (currency === "USD" ? "Base currency" : "per 1 USD") +
            "</div>";
 
        marketGrid.appendChild(card);
 
    });
 
}
 
 
renderMarket();
 
 
 
/* =====================================================
   LOGOUT
===================================================== */
 
if (logout) {
 
    logout.addEventListener("click", function() {
 
        CryptoWalletAPI.clearTokens();
        sessionStorage.clear();
 
        window.location.href = "../login.html";
 
    });
 
}
 
