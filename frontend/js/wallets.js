
//Wallets · JS
/* =====================================================
   CRYPTOWALLET
   WALLETS PAGE (Django API version)
===================================================== */
 
 
/* =====================================================
   REQUIRE LOGIN
 
   Guests don't have an account to hold wallets, same
   rule as the original localStorage version.
===================================================== */
 
CryptoWalletAPI.requireLogin("../login.html");
 
 
const currentUserName =
    sessionStorage.getItem("userName");
 
 
 
/* =====================================================
   DOM ELEMENTS
===================================================== */
 
const walletForm =
    document.getElementById("walletForm");
 
const walletNameInput =
    document.getElementById("walletName");
 
const currencyInput =
    document.getElementById("currency");
 
const walletNameError =
    document.getElementById("walletNameError");
 
const currencyError =
    document.getElementById("currencyError");
 
const walletList =
    document.getElementById("walletList");
 
const totalWalletsEl =
    document.getElementById("totalWallets");
 
const totalCurrenciesEl =
    document.getElementById("totalCurrencies");
 
const avatar =
    document.getElementById("avatar");
 
const logout =
    document.getElementById("logout");
 
const toast =
    document.getElementById("toast");
 
 
 
/* =====================================================
   SHOW TOAST
===================================================== */
 
function showToast(message) {
 
    if (!toast) {
 
        return;
 
    }
 
    toast.textContent = message;
    toast.classList.add("show");
 
    setTimeout(function() {
 
        toast.classList.remove("show");
 
    }, 2500);
 
}
 
 
 
/* =====================================================
   ESCAPE HTML
===================================================== */
 
function escapeHTML(value) {
 
    const div =
        document.createElement("div");
 
    div.textContent = value;
 
    return div.innerHTML;
 
}
 
 
 
/* =====================================================
   FORMAT WALLET BALANCE
===================================================== */
 
function formatWalletBalance(balance, currency) {
 
    const amount =
        Number(balance || 0);
 
    const decimals =
        (currency === "BTC" || currency === "ETH") ? 6 : 2;
 
    return (
        amount.toLocaleString(undefined, {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals
        }) + " " + currency
    );
 
}
 
 
 
/* =====================================================
   CLEAR FORM ERRORS
===================================================== */
 
function clearWalletFormErrors() {
 
    walletNameError.textContent = "";
    currencyError.textContent = "";
 
}
 
 
 
/* =====================================================
   LOAD + RENDER WALLETS
===================================================== */
 
async function renderWallets() {
 
    if (!walletList) {
 
        return;
 
    }
 
    let wallets;
 
    try {
 
        wallets = await CryptoWalletAPI.request("/wallets/");
 
    }
 
    catch (error) {
 
        showToast(error.message);
        return;
 
    }
 
 
    /* SUMMARY CARDS */
 
    if (totalWalletsEl) {
 
        totalWalletsEl.textContent = wallets.length;
 
    }
 
    if (totalCurrenciesEl) {
 
        const currencies =
            new Set(wallets.map(function(wallet) {
 
                return wallet.currency;
 
            }));
 
        totalCurrenciesEl.textContent = currencies.size;
 
    }
 
 
    /* EMPTY STATE */
 
    if (wallets.length === 0) {
 
        walletList.innerHTML =
            "<div class=\"empty-wallet\">" +
                "<div class=\"empty-icon\">▣</div>" +
                "<strong>No wallets yet</strong>" +
                "<p>Create your first wallet above.</p>" +
            "</div>";
 
        return;
 
    }
 
 
    /* WALLET CARDS */
 
    walletList.innerHTML =
        wallets.map(function(wallet) {
 
            return (
                "<div class=\"wallet-card\">" +
                    "<div class=\"wallet-top\">" +
                        "<div class=\"currency-icon\">" +
                            escapeHTML(wallet.currency) +
                        "</div>" +
                        "<div class=\"wallet-actions\">" +
                            "<button class=\"fund-wallet\" data-id=\"" +
                                wallet.wallet_id +
                                "\" title=\"Add funds\">+</button>" +
                            (wallet.is_default_receive
                                ? ""
                                : "<button class=\"freeze-wallet\" data-id=\"" +
                                    wallet.wallet_id +
                                    "\" title=\"" +
                                    (wallet.wallet_status === "FROZEN" ? "Unfreeze wallet" : "Freeze wallet") +
                                    "\">" +
                                    (wallet.wallet_status === "FROZEN" ? "🔓" : "🔒") +
                                    "</button>") +
                            (wallet.is_default_receive || wallet.wallet_status === "FROZEN"
                                ? ""
                                : "<button class=\"set-default-wallet\" data-id=\"" +
                                    wallet.wallet_id +
                                    "\" title=\"Set as default receive wallet\">★</button>") +
                            (wallet.is_default_receive
                                ? ""
                                : "<button class=\"delete-wallet\" data-id=\"" +
                                    wallet.wallet_id +
                                    "\" title=\"Delete wallet\">✕</button>") +
                        "</div>" +
                    "</div>" +
                    "<div class=\"wallet-name\">" +
                        escapeHTML(wallet.name) +
                        (wallet.is_default_receive
                            ? " <span class=\"default-badge\">★ Default Receive</span>"
                            : "") +
                        (wallet.wallet_status === "FROZEN"
                            ? " <span class=\"default-badge\" style=\"background:#555;\">❄ Frozen</span>"
                            : "") +
                    "</div>" +
                    "<div class=\"wallet-currency\">" +
                        escapeHTML(wallet.currency) +
                    "</div>" +
                    "<div class=\"wallet-balance\">" +
                        formatWalletBalance(wallet.balance, wallet.currency) +
                    "</div>" +
                    "<div class=\"wallet-balance-label\">" +
                        "Current balance" +
                    "</div>" +
                "</div>"
            );
 
        }).join("");
 
 
    /* FREEZE / UNFREEZE BUTTONS */
 
    walletList.querySelectorAll(".freeze-wallet").forEach(function(button) {
 
        button.addEventListener("click", async function() {
 
            try {
 
                await CryptoWalletAPI.request(
                    "/wallets/" + button.dataset.id + "/freeze-toggle/",
                    { method: "POST" }
                );
 
                await renderWallets();
                showToast("Wallet status updated.");
 
            }
 
            catch (error) {
 
                showToast(error.message);
 
            }
 
        });
 
    });
 
 
    /* SET AS DEFAULT BUTTONS */
 
    walletList.querySelectorAll(".set-default-wallet").forEach(function(button) {
 
        button.addEventListener("click", async function() {
 
            try {
 
                await CryptoWalletAPI.request(
                    "/wallets/" + button.dataset.id + "/set-default/",
                    { method: "POST" }
                );
 
                await renderWallets();
                showToast("Default receive wallet updated.");
 
            }
 
            catch (error) {
 
                showToast(error.message);
 
            }
 
        });
 
    });
 
 
    /* DELETE BUTTONS */
 
    walletList.querySelectorAll(".delete-wallet").forEach(function(button) {
 
        button.addEventListener("click", async function() {
 
            try {
 
                await CryptoWalletAPI.request(
                    "/wallets/" + button.dataset.id + "/",
                    { method: "DELETE" }
                );
 
                await renderWallets();
 
                showToast("Wallet deleted.");
 
            }
 
            catch (error) {
 
                showToast(error.message);
 
            }
 
        });
 
    });
 
 
    /* FUND BUTTONS
 
       There's no dedicated "add funds" form in this page's
       HTML, so this uses a simple prompt() for the amount —
       good enough for a demo wallet. A nicer inline form can
       replace this later without touching the API call.
    */
 
    walletList.querySelectorAll(".fund-wallet").forEach(function(button) {
 
        button.addEventListener("click", async function() {
 
            const amount =
                window.prompt("Amount to add to this wallet:");
 
            if (amount === null) {
 
                return;
 
            }
 
            const numericAmount =
                Number(amount);
 
            if (!numericAmount || numericAmount <= 0) {
 
                showToast("Please enter a valid amount.");
                return;
 
            }
 
            try {
 
                await CryptoWalletAPI.request(
                    "/wallets/" + button.dataset.id + "/fund/",
                    { method: "POST", body: { amount: numericAmount } }
                );
 
                await renderWallets();
 
                showToast("Wallet funded.");
                if (typeof showSuccessCheck === "function") showSuccessCheck("Funded");
 
            }
 
            catch (error) {
 
                showToast(error.message);
 
            }
 
        });
 
    });
 
}
 
 
 
/* =====================================================
   CREATE WALLET
===================================================== */
 
if (walletForm) {
 
    walletForm.addEventListener("submit", async function(event) {
 
        event.preventDefault();
 
        clearWalletFormErrors();
 
        const name =
            walletNameInput.value.trim();
 
        const currency =
            currencyInput.value;
 
        if (!name) {
 
            walletNameError.textContent =
                "Please enter a wallet name.";
            return;
 
        }
 
        if (!currency) {
 
            currencyError.textContent =
                "Please select a currency.";
            return;
 
        }
 
        try {
 
            await CryptoWalletAPI.request("/wallets/", {
 
                method: "POST",
                body: { name: name, currency: currency }
 
            });
 
            walletForm.reset();
 
            await renderWallets();
 
            showToast(name + " wallet created.");
 
        }
 
        catch (error) {
 
            showToast(error.message);
 
        }
 
    });
 
}
 
 
 
/* =====================================================
   AVATAR
===================================================== */
 
if (avatar && currentUserName) {
 
    avatar.textContent =
        currentUserName.charAt(0).toUpperCase();
 
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
   INITIAL RENDER
===================================================== */
 
renderWallets();
 



