/* =====================================================
   CRYPTOWALLET
   EXCHANGE PAGE (Django API version)
===================================================== */

CryptoWalletAPI.requireLogin("../login.html");

const currentUserName =
    sessionStorage.getItem("userName");



/* =====================================================
   DOM
===================================================== */

const fromWallet =
    document.getElementById("fromWallet");

const fromBalance =
    document.getElementById("fromBalance");

const fromWalletError =
    document.getElementById("fromWalletError");

const exchangeAmount =
    document.getElementById("exchangeAmount");

const fromCurrency =
    document.getElementById("fromCurrency");

const amountError =
    document.getElementById("amountError");

const toWallet =
    document.getElementById("toWallet");

const toBalance =
    document.getElementById("toBalance");

const toWalletError =
    document.getElementById("toWalletError");

const conversionPreview =
    document.getElementById("conversionPreview");

const sendPreview =
    document.getElementById("sendPreview");

const receivePreview =
    document.getElementById("receivePreview");

const ratePreview =
    document.getElementById("ratePreview");

const exchangeButton =
    document.getElementById("exchangeButton");

const message =
    document.getElementById("message");

const avatar =
    document.getElementById("avatar");

const logout =
    document.getElementById("logout");



/* =====================================================
   STATE
===================================================== */

let userWallets = [];



/* =====================================================
   CURRENCY CONVERSION (preview only — see send.js
   for the same note about rates.js vs the backend)
===================================================== */

function convertCurrency(value, from, to) {

    if (from === to) {

        return value;

    }

    const fromRate = EXCHANGE_RATES[from];
    const toRate = EXCHANGE_RATES[to];

    if (fromRate === undefined || toRate === undefined) {

        return null;

    }

    return (value / fromRate) * toRate;

}


function formatAmount(value, currency) {

    return Number(value).toLocaleString(undefined, {
        maximumFractionDigits: 6
    }) + " " + currency;

}



/* =====================================================
   CLEAR ERRORS
===================================================== */

function clearErrors() {

    fromWalletError.textContent = "";
    toWalletError.textContent = "";
    amountError.textContent = "";

}



/* =====================================================
   LOAD WALLETS
===================================================== */

function walletOptions(selectedId) {

    return "<option value=\"\">Select wallet</option>" +
        userWallets.map(function(wallet) {

            const selected = wallet.wallet_id === selectedId ? " selected" : "";

            return (
                "<option value=\"" + wallet.wallet_id + "\"" + selected + ">" +
                    wallet.name + " (" + wallet.currency + ")" +
                "</option>"
            );

        }).join("");

}


async function loadWallets() {

    try {

        userWallets = await CryptoWalletAPI.request("/wallets/");

    }

    catch (error) {

        showMessage(error.message, "error");
        return;

    }

    fromWallet.innerHTML = walletOptions();
    toWallet.innerHTML = walletOptions();

}


function findWallet(id) {

    return userWallets.find(function(wallet) {

        return wallet.wallet_id === id;

    });

}



/* =====================================================
   UPDATE FROM / TO
===================================================== */

function updateFromWallet() {

    const wallet = findWallet(fromWallet.value);

    fromCurrency.textContent = wallet ? wallet.currency : "-";
    fromBalance.textContent = wallet
        ? "Balance: " + formatAmount(wallet.balance, wallet.currency)
        : "";

    updatePreview();

}


function updateToWallet() {

    const wallet = findWallet(toWallet.value);

    toBalance.textContent = wallet
        ? "Balance: " + formatAmount(wallet.balance, wallet.currency)
        : "";

    updatePreview();

}



/* =====================================================
   PREVIEW
===================================================== */

function updatePreview() {

    const from = findWallet(fromWallet.value);
    const to = findWallet(toWallet.value);
    const value = Number(exchangeAmount.value);

    if (!from || !to || !value || value <= 0) {

        conversionPreview.classList.add("hidden");
        return;

    }

    const converted = convertCurrency(value, from.currency, to.currency);
    const rate = convertCurrency(1, from.currency, to.currency);

    sendPreview.textContent = formatAmount(value, from.currency);
    receivePreview.textContent = formatAmount(converted, to.currency);
    ratePreview.textContent =
        "1 " + from.currency + " = " + rate.toFixed(6) + " " + to.currency;

    conversionPreview.classList.remove("hidden");

}



/* =====================================================
   SHOW MESSAGE
===================================================== */

function showMessage(text, type) {

    message.textContent = text;
    message.className = "message " + (type === "error" ? "error-message" : "success-message");
    message.classList.remove("hidden");

}



/* =====================================================
   EVENTS
===================================================== */

fromWallet.addEventListener("change", function() {

    clearErrors();
    message.classList.add("hidden");
    updateFromWallet();

});

toWallet.addEventListener("change", function() {

    clearErrors();
    message.classList.add("hidden");
    updateToWallet();

});

exchangeAmount.addEventListener("input", function() {

    clearErrors();
    message.classList.add("hidden");
    updatePreview();

});



/* =====================================================
   EXCHANGE
===================================================== */

exchangeButton.addEventListener("click", async function() {

    clearErrors();
    message.classList.add("hidden");

    const from = findWallet(fromWallet.value);
    const to = findWallet(toWallet.value);
    const value = Number(exchangeAmount.value);

    if (!from) {

        fromWalletError.textContent = "Please select a wallet.";
        return;

    }

    if (!to) {

        toWalletError.textContent = "Please select a wallet.";
        return;

    }

    if (from.wallet_id === to.wallet_id) {

        toWalletError.textContent = "Please select two different wallets.";
        return;

    }

    if (!value || value <= 0) {

        amountError.textContent = "Please enter a valid amount.";
        return;

    }

    if (value > Number(from.balance)) {

        amountError.textContent = "Insufficient balance in this wallet.";
        return;

    }

    exchangeButton.disabled = true;

    const body = {
        from_wallet_id: from.wallet_id,
        to_wallet_id: to.wallet_id,
        amount: value
    };

    try {

        await submitExchangeRequest(body);

        showMessage("Exchange completed!", "success");
        if (typeof showSuccessCheck === "function") showSuccessCheck("Exchanged");

        exchangeAmount.value = "";
        conversionPreview.classList.add("hidden");

        const previousFrom = fromWallet.value;
        const previousTo = toWallet.value;

        await loadWallets();

        fromWallet.value = previousFrom;
        toWallet.value = previousTo;

        updateFromWallet();
        updateToWallet();

    }

    catch (error) {

        if (error) showMessage(error.message, "error");

    }

    finally {

        exchangeButton.disabled = false;

    }

});


/* =====================================================
   TRANSACTION PIN — same optional-PIN retry pattern as
   send.js's submitSendRequest(). See the comment there.
===================================================== */

async function submitExchangeRequest(body) {

    try {

        return await CryptoWalletAPI.request("/exchange/", { method: "POST", body: body });

    }

    catch (error) {

        const pinRequired = error.status === 400 && error.data && error.data.pin;

        if (!pinRequired) throw error;

        const pin = await openPinPad({
            title: "Confirm with your PIN",
            subtitle: "Enter your transaction PIN to complete this exchange.",
        });

        if (pin === null) throw null;

        return await CryptoWalletAPI.request("/exchange/", {
            method: "POST",
            body: Object.assign({}, body, { pin: pin }),
        });

    }

}



/* =====================================================
   AVATAR
===================================================== */

if (avatar && currentUserName) {

    avatar.textContent = currentUserName.charAt(0).toUpperCase();

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
   INITIAL LOAD
===================================================== */

loadWallets();
