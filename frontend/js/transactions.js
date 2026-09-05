/* =====================================================
   CRYPTOWALLET
   TRANSACTIONS PAGE (Django API version)

   The backend's Transaction model uses one consistent
   pair of field names for every type:
     currency / amount              -> the "primary" side
     counterparty_currency / _amount -> the other side
   (a SEND's primary side is what left your wallet, an
   EXCHANGE's primary side is the "from" wallet, etc.)
   That's simpler than the old localStorage version,
   which used a different field name per transaction type
   (receivedAmount, sentAmount, amountSent, amountReceived...).
===================================================== */

CryptoWalletAPI.requireLogin("../login.html");

const currentUserName =
    sessionStorage.getItem("userName");



/* =====================================================
   DOM
===================================================== */

const transactionList =
    document.getElementById("transactionList");

const totalTransactions =
    document.getElementById("totalTransactions");

const totalReceived =
    document.getElementById("totalReceived");

const totalSent =
    document.getElementById("totalSent");

const typeFilter =
    document.getElementById("typeFilter");

const currencyFilter =
    document.getElementById("currencyFilter");

const avatar =
    document.getElementById("avatar");

const logout =
    document.getElementById("logout");



/* =====================================================
   STATE
===================================================== */

let allTransactions = [];



/* =====================================================
   FORMAT AMOUNT
===================================================== */

function formatAmount(amount, currency) {

    const value =
        Number(amount || 0);

    if (currency === "BTC" || currency === "ETH") {

        return value.toFixed(8) + " " + currency;

    }

    const symbols = { USD: "$", BDT: "৳", EUR: "€", USDT: "$" };

    if (symbols[currency]) {

        return symbols[currency] + value.toFixed(2);

    }

    return value.toFixed(2) + " " + (currency || "");

}



/* =====================================================
   ICON / LABEL / CLASS
===================================================== */

function getTransactionIcon(type) {

    const icons = { DEPOSIT: "↓", SEND: "↑", RECEIVE: "↓", EXCHANGE: "⇄", SHIFT: "⇄" };
    return icons[type] || "⇄";

}


function getTransactionLabel(type) {

    const labels = {
        DEPOSIT: "Deposit", SEND: "Sent",
        RECEIVE: "Received", EXCHANGE: "Exchange", SHIFT: "Shifted"
    };
    return labels[type] || "Transaction";

}


function getTransactionClass(type) {

    if (type === "SEND") return "sent";
    if (type === "RECEIVE" || type === "DEPOSIT") return "received";
    if (type === "EXCHANGE" || type === "SHIFT") return "exchange";
    return "";

}



/* =====================================================
   FORMAT DATE
===================================================== */

function formatDate(date) {

    if (!date) {

        return "-";

    }

    const parsed = new Date(date);

    if (Number.isNaN(parsed.getTime())) {

        return "-";

    }

    return parsed.toLocaleString();

}



/* =====================================================
   ESCAPE HTML
===================================================== */

function escapeHTML(value) {

    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");

}



/* =====================================================
   CURRENCIES INVOLVED IN A TRANSACTION
===================================================== */

function getTransactionCurrencies(transaction) {

    const currencies = new Set();

    if (transaction.currency) {
        currencies.add(transaction.currency);
    }

    if (transaction.counterparty_currency) {
        currencies.add(transaction.counterparty_currency);
    }

    return Array.from(currencies);

}


function matchesCurrency(transaction, selectedCurrency) {

    if (selectedCurrency === "ALL") {

        return true;

    }

    return getTransactionCurrencies(transaction).includes(selectedCurrency);

}



/* =====================================================
   LOAD CURRENCY FILTER OPTIONS
===================================================== */

function loadCurrencyFilter() {

    const currencies = new Set();

    allTransactions.forEach(function(transaction) {

        getTransactionCurrencies(transaction).forEach(function(currency) {

            currencies.add(currency);

        });

    });

    currencyFilter.innerHTML =
        "<option value=\"ALL\">All Currencies</option>";

    Array.from(currencies).sort().forEach(function(currency) {

        const option = document.createElement("option");
        option.value = currency;
        option.textContent = currency;

        currencyFilter.appendChild(option);

    });

}



/* =====================================================
   LOAD CATEGORY FILTER OPTIONS
===================================================== */

function loadCategoryFilter() {

    const categoryFilter = document.getElementById("categoryFilter");

    if (!categoryFilter) return;

    const categories = new Set();

    allTransactions.forEach(function(transaction) {

        if (transaction.category) {

            categories.add(transaction.category);

        }

    });

    categoryFilter.innerHTML =
        "<option value=\"ALL\">All Categories</option>";

    Array.from(categories).sort().forEach(function(category) {

        const option = document.createElement("option");
        option.value = category;
        option.textContent = category;

        categoryFilter.appendChild(option);

    });

}



/* =====================================================
   DESCRIPTIONS
===================================================== */

function getSendDescription(transaction) {

    const recipient =
        transaction.counterparty_wallet_name || "Unknown wallet";

    if (transaction.counterparty_amount !== undefined && transaction.counterparty_currency) {

        return "Sent to " + escapeHTML(recipient) +
            " • Recipient received " +
            formatAmount(transaction.counterparty_amount, transaction.counterparty_currency);

    }

    return "Sent to " + escapeHTML(recipient);

}


function getReceiveDescription(transaction) {

    const sender =
        transaction.counterparty_wallet_name || "Unknown wallet";

    if (transaction.counterparty_amount !== undefined && transaction.counterparty_currency) {

        return "Received from " + escapeHTML(sender) +
            " • Sender sent " +
            formatAmount(transaction.counterparty_amount, transaction.counterparty_currency);

    }

    return "Received from " + escapeHTML(sender);

}


function getExchangeDescription(transaction) {

    const fromWallet = transaction.wallet_name || "Unknown wallet";
    const toWallet = transaction.counterparty_wallet_name || "Unknown wallet";

    return (
        escapeHTML(fromWallet) + " → " + escapeHTML(toWallet) + " • " +
        formatAmount(transaction.amount, transaction.currency) + " → " +
        formatAmount(transaction.counterparty_amount, transaction.counterparty_currency)
    );

}


function getDepositDescription(transaction) {

    return "Money deposited into " + escapeHTML(transaction.wallet_name || "Wallet");

}


function getTransactionDescription(transaction) {

    switch (transaction.type) {

        case "SEND": return getSendDescription(transaction);
        case "RECEIVE": return getReceiveDescription(transaction);
        case "EXCHANGE": return getExchangeDescription(transaction);
        case "SHIFT": return getExchangeDescription(transaction);
        case "DEPOSIT": return getDepositDescription(transaction);
        default: return "Financial activity";

    }

}



/* =====================================================
   MAIN AMOUNT (for the right-hand side of each row)
===================================================== */

function getMainTransactionAmount(transaction) {

    switch (transaction.type) {

        case "SEND":
            return { amount: transaction.amount, currency: transaction.currency, sign: "-" };

        case "RECEIVE":
        case "DEPOSIT":
            return { amount: transaction.amount, currency: transaction.currency, sign: "+" };

        case "EXCHANGE":
            return { amount: transaction.amount, currency: transaction.currency, sign: "⇄" };

        case "SHIFT":
            return { amount: transaction.amount, currency: transaction.currency, sign: "⇄" };

        default:
            return { amount: 0, currency: "", sign: "" };

    }

}



/* =====================================================
   TOTALS (SEND vs RECEIVE/DEPOSIT), per currency
===================================================== */

function calculateTotals(transactions) {

    const received = {};
    const sent = {};

    transactions.forEach(function(transaction) {

        const amount = Number(transaction.amount || 0);
        const currency = transaction.currency;

        if (!currency || !Number.isFinite(amount)) {

            return;

        }

        if (transaction.type === "RECEIVE" || transaction.type === "DEPOSIT") {

            received[currency] = (received[currency] || 0) + amount;

        }

        if (transaction.type === "SEND") {

            sent[currency] = (sent[currency] || 0) + amount;

        }

        /*
            EXCHANGE isn't counted in either total — it moves
            money between your own wallets rather than
            in/out of your account, same as the original.
        */

    });

    return { received: received, sent: sent };

}


function formatCurrencyTotals(totals) {

    const currencies = Object.keys(totals);

    if (currencies.length === 0) {

        return "$0.00";

    }

    return currencies.sort().map(function(currency) {

        return formatAmount(totals[currency], currency);

    }).join(" + ");

}


function updateSummary(transactions) {

    if (totalTransactions) {

        totalTransactions.textContent = transactions.length;

    }

    const totals = calculateTotals(transactions);

    if (totalReceived) {

        totalReceived.textContent = formatCurrencyTotals(totals.received);

    }

    if (totalSent) {

        totalSent.textContent = formatCurrencyTotals(totals.sent);

    }

}



/* =====================================================
   RENDER
===================================================== */

function renderTransactions() {

    const selectedType = typeFilter.value;
    const selectedCurrency = currencyFilter.value;
    const categoryFilterEl = document.getElementById("categoryFilter");
    const selectedCategory = categoryFilterEl ? categoryFilterEl.value : "ALL";

    const filtered = allTransactions.filter(function(transaction) {

        const typeMatch =
            selectedType === "ALL" || transaction.type === selectedType;

        const categoryMatch =
            selectedCategory === "ALL" || transaction.category === selectedCategory;

        return typeMatch && categoryMatch && matchesCurrency(transaction, selectedCurrency);

    });

    updateSummary(allTransactions);

    if (filtered.length === 0) {

        transactionList.innerHTML =
            "<div class=\"empty\">" +
                "<div class=\"empty-icon\">⇄</div>" +
                "<strong>No transactions found</strong>" +
                "<p>Your transaction history will appear here.</p>" +
            "</div>";

        return;

    }

    filtered.sort(function(a, b) {

        return new Date(b.created_at) - new Date(a.created_at);

    });

    transactionList.innerHTML =
        filtered.map(function(transaction) {

            const mainAmount = getMainTransactionAmount(transaction);
            const amountText = formatAmount(mainAmount.amount, mainAmount.currency);
            const transactionClass = getTransactionClass(transaction.type);
            const sign = mainAmount.sign === "⇄" ? "⇄ " : mainAmount.sign + " ";

            return (
                "<div class=\"transaction-item " + transactionClass + "\">" +
                    "<div class=\"transaction-left\">" +
                        "<div class=\"transaction-icon\">" +
                            getTransactionIcon(transaction.type) +
                        "</div>" +
                        "<div class=\"transaction-info\">" +
                            "<strong>" + getTransactionLabel(transaction.type) + "</strong>" +
                            "<small>" + getTransactionDescription(transaction) +
                                (transaction.category
                                    ? " · <span class=\"category-tag\">" + transaction.category + "</span>"
                                    : "") +
                            "</small>" +
                        "</div>" +
                    "</div>" +
                    "<div class=\"transaction-right\">" +
                        "<span class=\"transaction-amount " + transactionClass + "\">" +
                            sign + amountText +
                        "</span>" +
                        "<span class=\"transaction-date\">" +
                            formatDate(transaction.created_at) +
                        "</span>" +
                    "</div>" +
                "</div>"
            );

        }).join("");

}



/* =====================================================
   LOAD TRANSACTIONS
===================================================== */

async function loadTransactions() {

    try {

        allTransactions = await CryptoWalletAPI.request("/transactions/");

    }

    catch (error) {

        transactionList.innerHTML =
            "<div class=\"empty\"><strong>" + error.message + "</strong></div>";
        return;

    }

    loadCurrencyFilter();
    loadCategoryFilter();
    renderTransactions();

}



/* =====================================================
   FILTER EVENTS
===================================================== */

typeFilter.addEventListener("change", renderTransactions);
currencyFilter.addEventListener("change", renderTransactions);

const categoryFilterEl2 = document.getElementById("categoryFilter");
if (categoryFilterEl2) {
    categoryFilterEl2.addEventListener("change", renderTransactions);
}



/* =====================================================
   AVATAR
===================================================== */

if (currentUserName) {

    avatar.textContent = currentUserName.charAt(0).toUpperCase();

}



/* =====================================================
   LOGOUT
===================================================== */

logout.addEventListener("click", function() {

    CryptoWalletAPI.clearTokens();
    sessionStorage.clear();

    window.location.href = "../login.html";

});



/* =====================================================
   EXPORT CSV

   The export endpoint returns a raw CSV file, not JSON, so
   this bypasses CryptoWalletAPI.request() and does a plain
   authenticated fetch instead, then triggers a browser
   download from the resulting blob.
===================================================== */

const exportCSVButton =
    document.getElementById("exportCSVButton");

if (exportCSVButton) {

    exportCSVButton.addEventListener("click", async function() {

        try {

            const response =
                await fetch(CryptoWalletAPI.apiBaseUrl + "/transactions/export/", {

                    headers: {
                        Authorization: "Bearer " + CryptoWalletAPI.getAccessToken()
                    }

                });

            if (!response.ok) {

                throw new Error("Couldn't export transactions right now.");

            }

            const blob =
                await response.blob();

            const url =
                window.URL.createObjectURL(blob);

            const link =
                document.createElement("a");

            link.href = url;
            link.download = "cryptowallet_transactions.csv";
            document.body.appendChild(link);
            link.click();
            link.remove();

            window.URL.revokeObjectURL(url);

        }

        catch (error) {

            alert(error.message);

        }

    });

}



/* =====================================================
   EXPORT PDF
===================================================== */

const exportPDFButton =
    document.getElementById("exportPDFButton");

if (exportPDFButton) {

    exportPDFButton.addEventListener("click", async function() {

        try {

            const response =
                await fetch(CryptoWalletAPI.apiBaseUrl + "/transactions/export-pdf/", {

                    headers: {
                        Authorization: "Bearer " + CryptoWalletAPI.getAccessToken()
                    }

                });

            if (!response.ok) {

                throw new Error("Couldn't export the PDF statement right now.");

            }

            const blob =
                await response.blob();

            const url =
                window.URL.createObjectURL(blob);

            const link =
                document.createElement("a");

            link.href = url;
            link.download = "cryptowallet_statement.pdf";
            document.body.appendChild(link);
            link.click();
            link.remove();

            window.URL.revokeObjectURL(url);

        }

        catch (error) {

            alert(error.message);

        }

    });

}



/* =====================================================
   INITIALIZE
===================================================== */

loadTransactions();
