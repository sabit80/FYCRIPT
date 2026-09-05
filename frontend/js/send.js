/* =====================================================
   CRYPTOWALLET
   SEND PAGE (phone-based send + own-wallet shift)

   Two modes:
     - "phone": send to another account's phone number.
       Funds always land in THEIR default receive wallet.
     - "wallet": shift funds between two of YOUR OWN wallets.

   The live conversion preview uses the shared EXCHANGE_RATES
   from rates.js — it's just a preview. The actual send is
   validated and executed by the backend against the real
   ExchangeRate table, so the numbers always agree.
===================================================== */

CryptoWalletAPI.requireLogin("../login.html");

const currentUserName =
    sessionStorage.getItem("userName");



/* =====================================================
   DOM
===================================================== */

const senderWallet =
    document.getElementById("senderWallet");

const senderWalletError =
    document.getElementById("senderWalletError");

const modePhone =
    document.getElementById("modePhone");

const modeWallet =
    document.getElementById("modeWallet");

const recipientPhoneGroup =
    document.getElementById("recipientPhoneGroup");

const recipientWalletGroup =
    document.getElementById("recipientWalletGroup");

const recipientPhone =
    document.getElementById("recipientPhone");

const recipientPhoneError =
    document.getElementById("recipientPhoneError");

const recipientWallet =
    document.getElementById("recipientWallet");

const recipientWalletError =
    document.getElementById("recipientWalletError");

const recipientPreview =
    document.getElementById("recipientPreview");

const recipientWalletName =
    document.getElementById("recipientWalletName");

const recipientCurrency =
    document.getElementById("recipientCurrency");

const recipientOwner =
    document.getElementById("recipientOwner");

const amount =
    document.getElementById("amount");

const amountError =
    document.getElementById("amountError");

const currencyLabel =
    document.getElementById("currencyLabel");

const conversionPreview =
    document.getElementById("conversionPreview");

const sendPreview =
    document.getElementById("sendPreview");

const receivePreview =
    document.getElementById("receivePreview");

const ratePreview =
    document.getElementById("ratePreview");

const sendButton =
    document.getElementById("sendButton");

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
let currentRecipient = null;   // { phone, name, receive_currency } or { wallet_id, name, currency }
let sendMode = "phone";



/* =====================================================
   CURRENCY CONVERSION (preview only)
===================================================== */

function convertCurrency(value, fromCurrency, toCurrency) {

    if (fromCurrency === toCurrency) {

        return value;

    }

    const fromRate = EXCHANGE_RATES[fromCurrency];
    const toRate = EXCHANGE_RATES[toCurrency];

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

    senderWalletError.textContent = "";
    recipientPhoneError.textContent = "";
    recipientWalletError.textContent = "";
    amountError.textContent = "";

}



/* =====================================================
   LOAD SENDER WALLETS (also used to populate the
   "shift to my wallet" destination dropdown)
===================================================== */

async function loadSenderWallets() {

    try {

        userWallets = await CryptoWalletAPI.request("/wallets/");

    }

    catch (error) {

        showMessage(error.message, "error");
        return;

    }

    const options =
        "<option value=\"\">Select your wallet</option>" +
        userWallets.map(function(wallet) {

            return (
                "<option value=\"" + wallet.wallet_id + "\">" +
                    wallet.name + " (" + wallet.currency + ") — " +
                    Number(wallet.balance).toLocaleString() +
                    (wallet.is_default_receive ? " ★ default" : "") +
                "</option>"
            );

        }).join("");

    senderWallet.innerHTML = options;

    recipientWallet.innerHTML =
        "<option value=\"\">Select a wallet to move funds into</option>" +
        userWallets.map(function(wallet) {

            return (
                "<option value=\"" + wallet.wallet_id + "\">" +
                    wallet.name + " (" + wallet.currency + ")" +
                    (wallet.is_default_receive ? " ★ default" : "") +
                "</option>"
            );

        }).join("");

}


function getSelectedSenderWallet() {

    const id = senderWallet.value;

    if (!id) {

        return null;

    }

    return userWallets.find(function(wallet) {

        return wallet.wallet_id === id;

    });

}



/* =====================================================
   SEND MODE SWITCH
===================================================== */

function applySendMode() {

    sendMode = modeWallet.checked ? "wallet" : "phone";

    currentRecipient = null;
    recipientPreview.classList.add("hidden");
    conversionPreview.classList.add("hidden");
    clearErrors();
    message.classList.add("hidden");

    if (sendMode === "phone") {

        recipientPhoneGroup.classList.remove("hidden");
        recipientWalletGroup.classList.add("hidden");
        recipientPhone.value = "";

    } else {

        recipientPhoneGroup.classList.add("hidden");
        recipientWalletGroup.classList.remove("hidden");
        recipientWallet.value = "";

    }

}


modePhone.addEventListener("change", applySendMode);
modeWallet.addEventListener("change", applySendMode);



/* =====================================================
   RECIPIENT LOOKUP — PHONE (debounced)
===================================================== */

let recipientLookupTimer = null;

function checkRecipientPhone() {

    clearTimeout(recipientLookupTimer);

    const phone = recipientPhone.value.trim();

    currentRecipient = null;
    recipientPreview.classList.add("hidden");

    if (!phone) {

        return;

    }

    recipientLookupTimer = setTimeout(async function() {

        try {

            const account =
                await CryptoWalletAPI.request(
                    "/accounts/lookup/" + encodeURIComponent(phone) + "/"
                );

            currentRecipient = {
                phone: account.phone,
                name: account.name,
                currency: account.receive_currency
            };

            recipientPhoneError.textContent = "";
            recipientWalletName.textContent = "Default Receive Wallet";
            recipientCurrency.textContent = account.receive_currency || "-";
            recipientOwner.textContent = account.name + " (" + account.phone + ")";

            recipientPreview.classList.remove("hidden");

            updateConversionPreview();

        }

        catch (error) {

            recipientPhoneError.textContent =
                error.message || "No account found for this number.";

        }

    }, 400);

}



/* =====================================================
   RECIPIENT SELECTION — OWN WALLET (shift)
===================================================== */

function selectRecipientWallet() {

    const id = recipientWallet.value;

    currentRecipient = null;
    recipientPreview.classList.add("hidden");

    if (!id) {

        return;

    }

    const wallet = userWallets.find(function(w) {
        return w.wallet_id === id;
    });

    if (!wallet) {

        return;

    }

    if (wallet.wallet_id === senderWallet.value) {

        recipientWalletError.textContent =
            "Choose a different destination wallet.";
        return;

    }

    currentRecipient = {
        wallet_id: wallet.wallet_id,
        name: wallet.name,
        currency: wallet.currency
    };

    recipientWalletError.textContent = "";
    recipientWalletName.textContent = wallet.name;
    recipientCurrency.textContent = wallet.currency;
    recipientOwner.textContent = "You";

    recipientPreview.classList.remove("hidden");

    updateConversionPreview();

}



/* =====================================================
   CONVERSION PREVIEW
===================================================== */

function updateConversionPreview() {

    const sender = getSelectedSenderWallet();
    const value = Number(amount.value);

    if (!sender || !currentRecipient || !value || value <= 0) {

        conversionPreview.classList.add("hidden");
        return;

    }

    const toCurrency = currentRecipient.currency;

    const converted =
        convertCurrency(value, sender.currency, toCurrency);

    const rate =
        convertCurrency(1, sender.currency, toCurrency);

    if (converted === null) {

        conversionPreview.classList.add("hidden");
        return;

    }

    sendPreview.textContent = formatAmount(value, sender.currency);
    receivePreview.textContent = formatAmount(converted, toCurrency);
    ratePreview.textContent =
        "1 " + sender.currency + " = " + rate.toFixed(6) + " " + toCurrency;

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

recipientPhone.addEventListener("input", function() {

    clearErrors();
    message.classList.add("hidden");
    checkRecipientPhone();

});


recipientWallet.addEventListener("change", function() {

    clearErrors();
    message.classList.add("hidden");
    selectRecipientWallet();

});


senderWallet.addEventListener("change", function() {

    clearErrors();
    message.classList.add("hidden");

    const wallet = getSelectedSenderWallet();

    currencyLabel.textContent = wallet ? wallet.currency : "-";

    if (sendMode === "wallet") {

        selectRecipientWallet();

    } else {

        updateConversionPreview();

    }

});


amount.addEventListener("input", function() {

    clearErrors();
    message.classList.add("hidden");
    updateConversionPreview();

});


document.addEventListener("rates:loaded", updateConversionPreview);



/* =====================================================
   SEND TRANSACTION
===================================================== */

sendButton.addEventListener("click", async function() {

    clearErrors();
    message.classList.add("hidden");

    const sender = getSelectedSenderWallet();

    if (!sender) {

        senderWalletError.textContent = "Please select a wallet.";
        return;

    }

    if (!currentRecipient) {

        if (sendMode === "phone") {

            recipientPhoneError.textContent =
                "Please enter a valid recipient phone number.";

        } else {

            recipientWalletError.textContent =
                "Please select a destination wallet.";

        }

        return;

    }

    const value = Number(amount.value);

    if (!value || value <= 0) {

        amountError.textContent = "Please enter a valid amount.";
        return;

    }

    if (value > Number(sender.balance)) {

        amountError.textContent = "Insufficient balance in this wallet.";
        return;

    }

    const body = {
        sender_wallet_id: sender.wallet_id,
        amount: value
    };

    const sendCategoryEl = document.getElementById("sendCategory");

    if (sendCategoryEl && sendCategoryEl.value) {

        body.category = sendCategoryEl.value;

    }

    if (sendMode === "phone") {

        body.recipient_phone = currentRecipient.phone;

    } else {

        body.recipient_wallet_id = currentRecipient.wallet_id;

    }

    sendButton.disabled = true;

    try {

        await submitSendRequest(body);

        showMessage(
            sendMode === "phone"
                ? "Money sent! It's now in the recipient's receive wallet."
                : "Funds shifted between your wallets.",
            "success"
        );
        if (typeof showSuccessCheck === "function") showSuccessCheck("Sent");

        amount.value = "";
        recipientPhone.value = "";
        recipientWallet.value = "";
        currentRecipient = null;
        recipientPreview.classList.add("hidden");
        conversionPreview.classList.add("hidden");

        await loadSenderWallets();
        currencyLabel.textContent = "-";
        senderWallet.value = "";

    }

    catch (error) {

        if (error) showMessage(error.message, "error");

    }

    finally {

        sendButton.disabled = false;

    }

});


/* =====================================================
   TRANSACTION PIN

   The backend only requires "pin" in the request body if
   the account has one set (SendSerializer.pin is optional —
   see require_pin_if_set() in wallet/views.py). So the flow
   here is: try without a PIN first; if the API comes back
   with a 400 naming the "pin" field, open the PIN pad and
   retry once with it included. Accounts that never set a
   PIN never see this modal at all.
===================================================== */

async function submitSendRequest(body) {

    try {

        return await CryptoWalletAPI.request("/send/", { method: "POST", body: body });

    }

    catch (error) {

        const pinRequired = error.status === 400 && error.data && error.data.pin;

        if (!pinRequired) throw error;

        const pin = await openPinPad({
            title: "Confirm with your PIN",
            subtitle: "Enter your transaction PIN to send " + body.amount + ".",
        });

        if (pin === null) throw null; // user cancelled -- no error message shown

        return await CryptoWalletAPI.request("/send/", {
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
   QR CODE SCANNING (recipient phone auto-fill)

   Uses jsQR (loaded via CDN in send.html) to decode frames
   from the device camera. The Receive page encodes
   "cryptowallet://send?phone=...&name=..." — this pulls
   the phone param back out and fills recipientPhone.
===================================================== */

const scanQRButton = document.getElementById("scanQRButton");
const qrScanOverlay = document.getElementById("qrScanOverlay");
const qrScanVideo = document.getElementById("qrScanVideo");
const qrScanStatus = document.getElementById("qrScanStatus");
const qrScanCancel = document.getElementById("qrScanCancel");

let qrScanStream = null;
let qrScanRAF = null;

function stopQRScan() {

    if (qrScanRAF) {

        cancelAnimationFrame(qrScanRAF);
        qrScanRAF = null;

    }

    if (qrScanStream) {

        qrScanStream.getTracks().forEach(function(track) { track.stop(); });
        qrScanStream = null;

    }

    qrScanOverlay.style.display = "none";

}

function parsePhoneFromQR(text) {

    try {

        // cryptowallet://send?phone=...&name=...
        const query = text.split("?")[1] || "";
        const params = new URLSearchParams(query);
        return params.get("phone");

    } catch (error) {

        return null;

    }

}

async function startQRScan() {

    if (typeof jsQR === "undefined") {

        showMessage("QR scanning isn't available right now.", "error");
        return;

    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {

        showMessage("Your browser doesn't support camera access.", "error");
        return;

    }

    qrScanOverlay.style.display = "flex";
    qrScanStatus.textContent = "Point your camera at the QR code.";

    try {

        qrScanStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "environment" }
        });

        qrScanVideo.srcObject = qrScanStream;
        await qrScanVideo.play();

        const canvas = document.createElement("canvas");
        const context = canvas.getContext("2d");

        const tick = function() {

            if (!qrScanStream) return;

            if (qrScanVideo.readyState === qrScanVideo.HAVE_ENOUGH_DATA) {

                canvas.width = qrScanVideo.videoWidth;
                canvas.height = qrScanVideo.videoHeight;
                context.drawImage(qrScanVideo, 0, 0, canvas.width, canvas.height);

                const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
                const code = jsQR(imageData.data, imageData.width, imageData.height);

                if (code) {

                    const phone = parsePhoneFromQR(code.data);

                    if (phone) {

                        recipientPhone.value = phone;
                        recipientPhone.dispatchEvent(new Event("input"));
                        stopQRScan();
                        showMessage("Recipient filled in from QR code.", "success");
                        return;

                    }

                }

            }

            qrScanRAF = requestAnimationFrame(tick);

        };

        qrScanRAF = requestAnimationFrame(tick);

    }

    catch (error) {

        qrScanStatus.textContent = "Couldn't access the camera.";

    }

}

if (scanQRButton) {

    scanQRButton.addEventListener("click", startQRScan);

}

if (qrScanCancel) {

    qrScanCancel.addEventListener("click", stopQRScan);

}



/* =====================================================
   INITIAL LOAD
===================================================== */

loadSenderWallets();
applySendMode();
