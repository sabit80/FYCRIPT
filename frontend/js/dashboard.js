/* =====================================================
   CRYPTOWALLET
   DASHBOARD (Django API version)
===================================================== */


/* =====================================================
   REQUIRE A SESSION

   Same rule as before the API rewrite: a session only
   exists after logging in OR explicitly clicking
   "Continue as Guest". Anything else means the visitor
   never went through login.html.
===================================================== */

CryptoWalletAPI.requireSession("login.html");



/* =====================================================
   DOM ELEMENTS
===================================================== */

const welcome = document.getElementById("welcome");
const accountType = document.getElementById("accountType");
const guestMessage = document.getElementById("guestMessage");
const signInButton = document.getElementById("signInButton");
const logoutButton = document.getElementById("logout");
const avatar = document.querySelector(".avatar");

const totalBalanceEl = document.getElementById("totalBalance");
const totalBalanceNoteEl = document.getElementById("totalBalanceNote");
const totalWalletsEl = document.getElementById("totalWallets");
const totalWalletsNoteEl = document.getElementById("totalWalletsNote");
const totalCurrenciesEl = document.getElementById("totalCurrencies");
const totalCurrenciesNoteEl = document.getElementById("totalCurrenciesNote");
const totalTransactionsEl = document.getElementById("totalTransactions");
const totalTransactionsNoteEl = document.getElementById("totalTransactionsNote");

const balanceToggle = document.getElementById("balanceToggle");
const portfolioBody = document.getElementById("portfolioBody");
const portfolioChartWrap = document.getElementById("portfolioChartWrap");
const recentBody = document.getElementById("recentBody");



/* =====================================================
   FORMAT HELPERS
===================================================== */

function formatMoney(value) {
    return "$" + Number(value || 0).toFixed(2);
}


function formatWalletBalance(balance, currency) {

    const amount = Number(balance || 0);

    const symbols = {
        USD: "$", EUR: "€", BDT: "৳", BTC: "₿", ETH: "Ξ", USDT: "$"
    };

    if (currency === "BTC" || currency === "ETH") {
        return amount.toFixed(8) + " " + currency;
    }

    return (symbols[currency] || "") + amount.toFixed(2);

}


function getCurrencySymbol(currency) {

    const symbols = {
        USD: "$", EUR: "€", BDT: "৳", BTC: "₿", ETH: "Ξ", USDT: "$"
    };

    return symbols[currency] || currency;

}


function formatDate(date) {

    if (!date) return "-";
    const parsed = new Date(date);
    return Number.isNaN(parsed.getTime()) ? "-" : parsed.toLocaleString();

}


function escapeHTML(value) {

    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;

}


/* Removes the loading-skeleton look and briefly flashes
   the element once its real value is set — used for every
   stat card value so numbers don't just pop in silently. */
function setStatValue(element, text) {

    element.classList.remove("skeleton", "skeleton-text");
    element.textContent = text;
    element.classList.add("count-up-flash");
    setTimeout(function() { element.classList.remove("count-up-flash"); }, 500);

}



/* =====================================================
   USER INFO / AVATAR
===================================================== */

function updateUserInformation() {

    const userType = sessionStorage.getItem("userType");
    const userName = sessionStorage.getItem("userName");

    if (userType !== "user") {

        welcome.textContent = "Welcome, Guest";
        accountType.textContent = "Guest account";
        avatar.textContent = "G";
        return;

    }

    const name = userName || "User";

    welcome.textContent = "Welcome, " + name;
    accountType.textContent = "Account overview";
    avatar.textContent = name.charAt(0).toUpperCase();

}



/* =====================================================
   BALANCE HIDE / SHOW

   Persisted per browser (not per account) via localStorage,
   same pattern as js/theme.js. The real formatted string is
   kept on the element's dataset so toggling back doesn't
   need another API round trip.
===================================================== */

const BALANCE_HIDDEN_KEY = "cryptoWalletBalanceHidden";

function isBalanceHidden() {
    return localStorage.getItem(BALANCE_HIDDEN_KEY) === "true";
}


function renderBalanceDisplay() {

    const real = totalBalanceEl.dataset.value;
    if (real === undefined) return;

    if (isBalanceHidden()) {

        totalBalanceEl.textContent = "৳ ••••••";
        totalBalanceEl.classList.add("balance-masked");
        balanceToggle.setAttribute("aria-pressed", "true");

    } else {

        totalBalanceEl.textContent = real;
        totalBalanceEl.classList.remove("balance-masked");
        balanceToggle.setAttribute("aria-pressed", "false");

    }

}


balanceToggle.addEventListener("click", function() {

    localStorage.setItem(BALANCE_HIDDEN_KEY, isBalanceHidden() ? "false" : "true");
    renderBalanceDisplay();

});



/* =====================================================
   STAT CARDS
===================================================== */

function renderGuestStats() {

    setStatValue(totalBalanceEl, "$0.00");
    totalBalanceEl.dataset.value = "$0.00";
    totalBalanceNoteEl.textContent = "No funds available";
    renderBalanceDisplay();

    setStatValue(totalWalletsEl, "0");
    totalWalletsNoteEl.textContent = "No wallets created";

    setStatValue(totalCurrenciesEl, "0");
    totalCurrenciesNoteEl.textContent = "No currencies held";

    setStatValue(totalTransactionsEl, "0");
    totalTransactionsNoteEl.textContent = "No transactions";

}


async function updateStats() {

    if (sessionStorage.getItem("userType") !== "user") {
        renderGuestStats();
        return;
    }

    let summary;

    try {
        summary = await CryptoWalletAPI.request("/dashboard/summary/");
    }
    catch (error) {
        renderGuestStats();
        return;
    }

    const totalBalance = Number(summary.total_balance_usd);
    const formattedBalance = formatMoney(totalBalance);

    totalBalanceEl.dataset.value = formattedBalance;
    setStatValue(totalBalanceEl, formattedBalance);
    renderBalanceDisplay();
    totalBalanceNoteEl.textContent =
        totalBalance > 0 ? "Total balance in USD" : "No funds available";

    setStatValue(totalWalletsEl, String(summary.total_wallets));
    totalWalletsNoteEl.textContent =
        summary.total_wallets === 1 ? "1 wallet created" : summary.total_wallets + " wallets created";

    setStatValue(totalCurrenciesEl, String(summary.currencies));
    totalCurrenciesNoteEl.textContent =
        summary.currencies === 1 ? "1 currency held" : summary.currencies + " currencies held";

    setStatValue(totalTransactionsEl, String(summary.total_transactions));
    totalTransactionsNoteEl.textContent =
        summary.total_transactions === 1 ? "1 transaction" : summary.total_transactions + " transactions";

}



/* =====================================================
   BALANCE SPARKLINE

   There's no balance-history endpoint on the backend, so
   this doesn't invent fake data — it derives an approximate
   trend from the same /transactions/ list the "Recent
   Transactions" card already fetches: a running total built
   from each transaction's signed amount, ending at the
   current real balance. It's a reasonable trend line, not
   an exact historical ledger.
===================================================== */

let sparklineChart = null;

function renderBalanceSparkline(transactions, currentTotal) {

    const canvas = document.getElementById("balanceSparkline");
    if (!canvas || typeof Chart === "undefined") return;

    const ordered = [...transactions].sort(function(a, b) {
        return new Date(a.created_at) - new Date(b.created_at);
    }).slice(-12);

    if (ordered.length < 2) {
        canvas.closest(".sparkline-wrap").style.display = "none";
        return;
    }

    // Walk backwards from the current total, undoing each
    // transaction's effect, so the series ends exactly at
    // today's real balance.
    let running = Number(currentTotal);
    const points = [running];

    for (let i = ordered.length - 1; i >= 0; i--) {

        const amount = Number(ordered[i].amount || 0);
        running += ordered[i].type === "SEND" ? amount : -amount;
        points.unshift(running);

    }

    if (sparklineChart) sparklineChart.destroy();

    sparklineChart = new Chart(canvas, {
        type: "line",
        data: {
            labels: points.map(function(_, i) { return i; }),
            datasets: [{
                data: points,
                borderColor: "#6c63ff",
                backgroundColor: "rgba(108, 99, 255, 0.12)",
                borderWidth: 2,
                pointRadius: 0,
                fill: true,
                tension: 0.35,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: { x: { display: false }, y: { display: false } },
            animation: { duration: 600 },
        },
    });

}



/* =====================================================
   PORTFOLIO  (list + donut chart)
===================================================== */

let portfolioChart = null;

function renderPortfolioEmpty(message) {

    portfolioChartWrap.hidden = true;

    portfolioBody.innerHTML =
        "<div class=\"empty\">" +
            "<div aria-hidden=\"true\">◈</div>" +
            "<strong>No portfolio data</strong>" +
            "<p>" + message + "</p>" +
        "</div>";

}


function renderPortfolioDonut(wallets) {

    if (typeof Chart === "undefined") {
        portfolioChartWrap.hidden = true;
        return;
    }

    const byCurrency = {};

    wallets.forEach(function(wallet) {

        const usdValue =
            EXCHANGE_RATES[wallet.currency] !== undefined
                ? Number(wallet.balance) / EXCHANGE_RATES[wallet.currency]
                : 0;

        byCurrency[wallet.currency] = (byCurrency[wallet.currency] || 0) + usdValue;

    });

    const labels = Object.keys(byCurrency);
    const values = labels.map(function(c) { return byCurrency[c]; });

    if (labels.length === 0 || values.every(function(v) { return v === 0; })) {
        portfolioChartWrap.hidden = true;
        return;
    }

    portfolioChartWrap.hidden = false;

    const palette = ["#6c63ff", "#a89bff", "#4d2be4", "#16a34a", "#f59e0b", "#dc2626", "#0ea5e9"];

    if (portfolioChart) portfolioChart.destroy();

    portfolioChart = new Chart(document.getElementById("portfolioDonut"), {
        type: "doughnut",
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: labels.map(function(_, i) { return palette[i % palette.length]; }),
                borderWidth: 0,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "68%",
            plugins: {
                legend: {
                    position: "bottom",
                    labels: { boxWidth: 10, font: { size: 11 } },
                },
            },
            animation: { duration: 700 },
        },
    });

}


async function updatePortfolio() {

    if (sessionStorage.getItem("userType") !== "user") {
        renderPortfolioEmpty("Sign in and create wallets to manage your portfolio.");
        return [];
    }

    let wallets;

    try {
        wallets = await CryptoWalletAPI.request("/wallets/");
    }
    catch (error) {
        renderPortfolioEmpty("Sign in and create wallets to manage your portfolio.");
        return [];
    }

    if (wallets.length === 0) {
        renderPortfolioEmpty("Create a wallet to start building your portfolio.");
        return [];
    }

    renderPortfolioDonut(wallets);

    portfolioBody.innerHTML =
        "<div class=\"portfolio-list\">" +
            wallets.map(function(wallet) {

                const usdValue =
                    EXCHANGE_RATES[wallet.currency] !== undefined
                        ? Number(wallet.balance) / EXCHANGE_RATES[wallet.currency]
                        : null;

                return (
                    "<div class=\"portfolio-item\">" +
                        "<div class=\"portfolio-info\">" +
                            "<div class=\"portfolio-icon\" aria-hidden=\"true\">" +
                                getCurrencySymbol(wallet.currency) +
                            "</div>" +
                            "<div>" +
                                "<strong>" + escapeHTML(wallet.name) + "</strong>" +
                                "<small>" + escapeHTML(wallet.currency) + "</small>" +
                            "</div>" +
                        "</div>" +
                        "<div class=\"portfolio-balance\">" +
                            "<strong>" + formatWalletBalance(wallet.balance, wallet.currency) + "</strong>" +
                            "<small>" +
                                (usdValue !== null ? "≈ " + formatMoney(usdValue) : "USD value unavailable") +
                            "</small>" +
                        "</div>" +
                    "</div>"
                );

            }).join("") +
        "</div>";

    return wallets;

}



/* =====================================================
   RECENT TRANSACTIONS
===================================================== */

function getTransactionLabel(transaction) {

    const labels = {
        SEND: "Sent", RECEIVE: "Received",
        EXCHANGE: "Exchange", DEPOSIT: "Deposit"
    };
    return labels[transaction.type] || "Transaction";

}


function getTransactionDescription(transaction) {

    switch (transaction.type) {

        case "SEND":
            return "To " + escapeHTML(transaction.counterparty_wallet_name || "Unknown wallet");

        case "RECEIVE":
            return "From " + escapeHTML(transaction.counterparty_wallet_name || "Unknown wallet");

        case "EXCHANGE":
            return (
                escapeHTML(transaction.wallet_name || "Wallet") + " → " +
                escapeHTML(transaction.counterparty_wallet_name || "Wallet")
            );

        case "DEPOSIT":
            return "To " + escapeHTML(transaction.wallet_name || "Wallet");

        default:
            return "Financial activity";

    }

}


function getTransactionAmount(transaction) {

    const sign = transaction.type === "SEND" ? "-" : "+";
    const className = transaction.type === "SEND" ? "sent" : "received";

    return {
        text: sign + " " + formatWalletBalance(transaction.amount, transaction.currency),
        className: className
    };

}


function renderRecentEmpty(title, message) {

    recentBody.innerHTML =
        "<div class=\"empty\">" +
            "<div aria-hidden=\"true\">⇄</div>" +
            "<strong>" + title + "</strong>" +
            "<p>" + message + "</p>" +
        "</div>";

}


async function updateRecentTransactions(currentTotalBalance) {

    if (sessionStorage.getItem("userType") !== "user") {
        renderRecentEmpty("Sign in to view transactions", "Your transaction history will appear here.");
        return;
    }

    let transactions;

    try {
        transactions = await CryptoWalletAPI.request("/transactions/");
    }
    catch (error) {
        renderRecentEmpty("Sign in to view transactions", "Your transaction history will appear here.");
        return;
    }

    if (transactions.length === 0) {
        renderRecentEmpty("No transactions yet", "Your transactions will appear here.");
        return;
    }

    renderBalanceSparkline(transactions, currentTotalBalance);

    const latestTransactions =
        [...transactions]
            .sort(function(a, b) { return new Date(b.created_at) - new Date(a.created_at); })
            .slice(0, 5);

    recentBody.innerHTML =
        "<div class=\"transaction-list\">" +
            latestTransactions.map(function(transaction) {

                const amount = getTransactionAmount(transaction);

                return (
                    "<div class=\"transaction-item " + amount.className + "\">" +
                        "<div>" +
                            "<strong>" + getTransactionLabel(transaction) + "</strong>" +
                            "<small>" + getTransactionDescription(transaction) + "</small>" +
                            "<small>" + formatDate(transaction.created_at) + "</small>" +
                        "</div>" +
                        "<strong class=\"transaction-amount " + amount.className + "\">" +
                            amount.text +
                        "</strong>" +
                    "</div>"
                );

            }).join("") +
        "</div>";

}



/* =====================================================
   GUEST MESSAGE
===================================================== */

function updateGuestMessage() {

    guestMessage.style.display =
        sessionStorage.getItem("userType") === "user" ? "none" : "block";

}



/* =====================================================
   SIGN IN BUTTON
===================================================== */

if (signInButton) {

    signInButton.addEventListener("click", function() {
        window.location.href = "login.html";
    });

}



/* =====================================================
   LOGOUT
===================================================== */

if (logoutButton) {

    logoutButton.addEventListener("click", function() {

        CryptoWalletAPI.clearTokens();
        sessionStorage.clear();
        window.location.href = "login.html";

    });

}



/* =====================================================
   INITIALIZE
===================================================== */

async function initializeDashboard() {

    updateUserInformation();
    updateGuestMessage();

    await updateStats();

    const summaryBalance = totalBalanceEl.dataset.rawUsd || 0;

    await updatePortfolio();
    await updateRecentTransactions(
        Number(String(totalBalanceEl.dataset.value || "0").replace(/[^0-9.-]/g, ""))
    );

}


initializeDashboard();
