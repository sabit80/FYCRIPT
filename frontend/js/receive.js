/* =====================================================
   CRYPTOWALLET
   RECEIVE PAGE (phone number + per-wallet receive info)
===================================================== */

CryptoWalletAPI.requireLogin("../login.html");

const currentUserName =
    sessionStorage.getItem("userName");

const currentUserPhone =
    sessionStorage.getItem("userPhone");



/* =====================================================
   DOM
===================================================== */

const accountPhone =
    document.getElementById("accountPhone");

const copyAccountNumber =
    document.getElementById("copyAccountNumber");

const accountCopyMessage =
    document.getElementById("accountCopyMessage");

const walletSelect =
    document.getElementById("walletSelect");

const walletError =
    document.getElementById("walletError");

const walletInformation =
    document.getElementById("walletInformation");

const walletName =
    document.getElementById("walletName");

const walletCurrency =
    document.getElementById("walletCurrency");

const walletBalance =
    document.getElementById("walletBalance");

const receiveBox =
    document.getElementById("receiveBox");

const walletIdentifier =
    document.getElementById("walletIdentifier");

const copyButton =
    document.getElementById("copyButton");

const successMessage =
    document.getElementById("successMessage");

const avatar =
    document.getElementById("avatar");

const logout =
    document.getElementById("logout");



/* =====================================================
   STATE
===================================================== */

let userWallets = [];



/* =====================================================
   FORMAT BALANCE
===================================================== */

function formatBalance(balance, currency) {

    return Number(balance).toLocaleString(undefined, {
        maximumFractionDigits: 6
    }) + " " + currency;

}



/* =====================================================
   ACCOUNT PHONE NUMBER (fetched fresh from /profile/ so it's
   always correct even if sessionStorage is stale)
===================================================== */

async function loadAccountPhone() {

    if (currentUserPhone) {

        accountPhone.value = currentUserPhone;

    }

    try {

        const profile = await CryptoWalletAPI.request("/profile/");

        accountPhone.value = profile.phone;
        sessionStorage.setItem("userPhone", profile.phone);

    }

    catch (error) {

        // sessionStorage value (if any) stays as a fallback

    }

}


if (copyAccountNumber) {

    copyAccountNumber.addEventListener("click", async function() {

        try {

            await navigator.clipboard.writeText(accountPhone.value);

            accountCopyMessage.textContent = "Phone number copied!";
            accountCopyMessage.classList.remove("hidden");

        }

        catch (error) {

            accountCopyMessage.textContent =
                "Clipboard API is unavailable. Please copy the number manually.";
            accountCopyMessage.classList.remove("hidden");

        }

    });

}



/* =====================================================
   LOAD WALLETS
===================================================== */

async function loadWallets() {

    try {

        userWallets = await CryptoWalletAPI.request("/wallets/");

    }

    catch (error) {

        walletError.textContent = error.message;
        return;

    }

    if (userWallets.length === 0) {

        walletSelect.innerHTML =
            "<option value=\"\">No wallets yet</option>";
        return;

    }

    walletSelect.innerHTML =
        "<option value=\"\">Select a wallet</option>" +
        userWallets.map(function(wallet) {

            return (
                "<option value=\"" + wallet.wallet_id + "\">" +
                    wallet.name + " (" + wallet.currency + ")" +
                    (wallet.is_default_receive ? " ★ default" : "") +
                "</option>"
            );

        }).join("");

}



/* =====================================================
   SHOW WALLET
===================================================== */

function showWallet(wallet) {

    walletName.textContent = wallet.name;
    walletCurrency.textContent = wallet.currency;
    walletBalance.textContent = formatBalance(wallet.balance, wallet.currency);

    const hasCryptoAddress =
        wallet.currency_type === "CRYPTO" &&
        wallet.crypto_addresses &&
        wallet.crypto_addresses.length > 0;

    if (hasCryptoAddress) {

        const address = wallet.crypto_addresses[0];

        walletIdentifier.value =
            address.public_address + " (" + address.blockchain + ")";

    } else {

        walletIdentifier.value = wallet.wallet_id;

    }

    walletInformation.classList.remove("hidden");
    receiveBox.classList.remove("hidden");

}



/* =====================================================
   EVENTS
===================================================== */

walletSelect.addEventListener("change", function() {

    walletError.textContent = "";
    successMessage.classList.add("hidden");

    const id = walletSelect.value;

    if (!id) {

        walletInformation.classList.add("hidden");
        receiveBox.classList.add("hidden");
        return;

    }

    const wallet = userWallets.find(function(item) {

        return item.wallet_id === id;

    });

    if (wallet) {

        showWallet(wallet);

    }

});


if (copyButton) {

    copyButton.addEventListener("click", async function() {

        try {

            await navigator.clipboard.writeText(
                walletIdentifier.value || walletIdentifier.textContent
            );

            successMessage.textContent = "Copied to clipboard!";
            successMessage.classList.remove("hidden");

        }

        catch (error) {

            successMessage.textContent =
                "Clipboard API is unavailable. Please copy it manually.";
            successMessage.classList.remove("hidden");

        }

    });

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
   RECEIVE QR CODE
===================================================== */

async function loadReceiveQR() {

    const qrImage =
        document.getElementById("receiveQRImage");

    if (!qrImage) {

        return;

    }

    try {

        const data =
            await CryptoWalletAPI.request("/accounts/receive-qr/");

        qrImage.src = data.qr_code_base64;

    }

    catch (error) {

        // Silent — the rest of the Receive page still works fine
        // without the QR image.

    }

}



/* =====================================================
   INITIAL LOAD
===================================================== */

loadAccountPhone();
loadWallets();
loadReceiveQR();
