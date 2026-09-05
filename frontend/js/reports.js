/* =====================================================
   CRYPTOWALLET
   REPORTS PAGE (Django API version)
===================================================== */

CryptoWalletAPI.requireLogin("../login.html");



/* =====================================================
   DOM
===================================================== */

const typeSummary =
    document.getElementById("typeSummary");

const currencyBreakdown =
    document.getElementById("currencyBreakdown");

const reportsEmpty =
    document.getElementById("reportsEmpty");

const avatar =
    document.getElementById("avatar");

const logout =
    document.getElementById("logout");



/* =====================================================
   FORMAT NUMBER
===================================================== */

function formatAmount(amount) {

    return Number(amount || 0).toLocaleString(undefined, {
        maximumFractionDigits: 6
    });

}



/* =====================================================
   RENDER TYPE SUMMARY
===================================================== */

function renderTypeSummary(transactions) {

    if (!typeSummary) return;

    const counts = { SEND: 0, RECEIVE: 0, EXCHANGE: 0, DEPOSIT: 0 };

    transactions.forEach(function(tx) {

        if (counts[tx.type] !== undefined) {

            counts[tx.type] += 1;

        }

    });

    const labels = {
        SEND: "Sent", RECEIVE: "Received",
        EXCHANGE: "Exchanged", DEPOSIT: "Deposited"
    };

    typeSummary.innerHTML =
        Object.keys(labels).map(function(key) {

            return (
                "<div class=\"stat-card\">" +
                    "<span>" + labels[key] + "</span>" +
                    "<strong>" + counts[key] + "</strong>" +
                "</div>"
            );

        }).join("");

}



/* =====================================================
   RENDER CURRENCY BREAKDOWN
===================================================== */

function renderCurrencyBreakdown(transactions) {

    if (!currencyBreakdown) return;

    if (transactions.length === 0) {

        currencyBreakdown.innerHTML = "";

        if (reportsEmpty) reportsEmpty.style.display = "block";

        return;

    }

    if (reportsEmpty) reportsEmpty.style.display = "none";

    const totals = {};

    transactions.forEach(function(tx) {

        const currency = tx.currency || "USD";

        totals[currency] = (totals[currency] || 0) + Number(tx.amount || 0);

    });

    const maxTotal =
        Math.max.apply(null, Object.values(totals));

    currencyBreakdown.innerHTML =
        Object.keys(totals).map(function(currency) {

            const total = totals[currency];

            const widthPercent =
                maxTotal > 0 ? Math.max(4, (total / maxTotal) * 100) : 0;

            return (
                "<div class=\"breakdown-row\">" +
                    "<div class=\"breakdown-label\">" +
                        "<strong>" + currency + "</strong>" +
                        "<span>" + formatAmount(total) + " " + currency + "</span>" +
                    "</div>" +
                    "<div class=\"breakdown-track\">" +
                        "<div class=\"breakdown-fill\" style=\"width: " + widthPercent + "%\"></div>" +
                    "</div>" +
                "</div>"
            );

        }).join("");

}



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



/* =====================================================
   LOAD + RENDER
===================================================== */

async function loadReports() {

    const currentUserName =
        sessionStorage.getItem("userName");

    if (avatar && currentUserName) {

        avatar.textContent = currentUserName.charAt(0).toUpperCase();

    }

    let transactions;

    try {

        transactions = await CryptoWalletAPI.request("/transactions/");

    }

    catch (error) {

        if (typeSummary) {

            typeSummary.innerHTML =
                "<div class=\"empty\"><strong>" + error.message + "</strong></div>";

        }

        return;

    }

    renderTypeSummary(transactions);
    renderCurrencyBreakdown(transactions);

}


loadReports();
