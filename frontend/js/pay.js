/* =====================================================
   CRYPTOWALLET — PUBLIC PAYMENT LINK PAGE

   Reads ?link=<link_id> from the URL. The payment itself still
   requires the payer to be logged in (they choose which of their
   own wallets to pay from) — this page just handles the "not
   logged in yet" case gracefully instead of silently failing.
===================================================== */

function escapeHTML(value) {

    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;

}

function getLinkIdFromURL() {

    const params = new URLSearchParams(window.location.search);
    return params.get("link");

}

async function init() {

    const linkId = getLinkIdFromURL();

    const loadingEl = document.getElementById("payLoading");
    const contentEl = document.getElementById("payContent");
    const loginRequiredEl = document.getElementById("payLoginRequired");

    if (!linkId) {

        loadingEl.textContent = "No payment link specified.";
        return;

    }

    if (!CryptoWalletAPI.isLoggedIn()) {

        loadingEl.style.display = "none";
        loginRequiredEl.style.display = "block";
        return;

    }

    try {

        const link = await CryptoWalletAPI.request("/payment-links/" + linkId + "/pay/");

        document.getElementById("payTitle").textContent = link.title;
        document.getElementById("payMerchant").textContent = "To: " + link.merchant_name;

        const amountGroup = document.getElementById("payAmountGroup");
        const amountInput = document.getElementById("payAmount");

        if (link.amount) {

            amountInput.value = link.amount;
            amountInput.disabled = true;
            amountGroup.querySelector("label").textContent =
                "Amount (fixed at " + link.amount + " " + link.currency + ")";

        }

        const wallets = await CryptoWalletAPI.request("/wallets/");
        const walletSelect = document.getElementById("payWalletSelect");

        walletSelect.innerHTML = wallets
            .filter(function(w) { return w.wallet_status === "ACTIVE"; })
            .map(function(w) {
                return '<option value="' + w.wallet_id + '">' +
                    escapeHTML(w.name) + " (" + w.currency + ", " + w.balance + ")</option>";
            })
            .join("");

        loadingEl.style.display = "none";
        contentEl.style.display = "block";

        document.getElementById("payButton").addEventListener("click", async function() {

            const errorEl = document.getElementById("payError");
            errorEl.textContent = "";

            const body = { payer_wallet_id: walletSelect.value };

            if (!link.amount) {

                body.amount = amountInput.value;

            }

            try {

                await CryptoWalletAPI.request("/payment-links/" + linkId + "/pay/", {

                    method: "POST",
                    body: body

                });

                contentEl.style.display = "none";
                document.getElementById("paySuccess").style.display = "block";

            } catch (error) {

                errorEl.textContent = error.message;

            }

        });

    } catch (error) {

        loadingEl.textContent = error.message || "This payment link isn't available.";

    }

}

init();
