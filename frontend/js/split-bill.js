/* =====================================================
   CRYPTOWALLET — SPLIT BILL (GROUP PAYMENT)
===================================================== */

CryptoWalletAPI.requireLogin("../login.html");


const avatar = document.getElementById("avatar");
const logout = document.getElementById("logout");
const toast = document.getElementById("toast");

const splitReceiverWallet = document.getElementById("splitReceiverWallet");
const createSplitForm = document.getElementById("createSplitForm");
const createSplitError = document.getElementById("createSplitError");
const participantRows = document.getElementById("participantRows");
const addParticipantRowButton = document.getElementById("addParticipantRowButton");
const splitList = document.getElementById("splitList");

let currentUserId = null;
let currentUserWallets = [];


function showToast(message) {

    if (!toast) return;

    toast.textContent = message;
    toast.classList.add("show");

    setTimeout(function() {
        toast.classList.remove("show");
    }, 2500);

}


function escapeHTML(value) {

    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;

}


/* =====================================================
   PARTICIPANT ROWS (dynamic form)
===================================================== */

function addParticipantRow() {

    const row = document.createElement("div");
    row.className = "participant-row";
    row.style.cssText = "display:flex;gap:8px;margin-bottom:8px;";

    row.innerHTML =
        '<input type="tel" placeholder="Phone number" class="participant-phone" style="flex:2;">' +
        '<input type="number" placeholder="Share amount" min="0.00000001" step="0.00000001" class="participant-share" style="flex:1;">' +
        '<button type="button" class="remove-participant-row" style="flex:0;">✕</button>';

    row.querySelector(".remove-participant-row").addEventListener("click", function() {

        row.remove();

    });

    participantRows.appendChild(row);

}

if (addParticipantRowButton) {

    addParticipantRowButton.addEventListener("click", addParticipantRow);

}


/* =====================================================
   LOAD WALLETS FOR THE "COLLECT INTO" SELECT
===================================================== */

async function loadWalletsForSplit() {

    try {

        const wallets = await CryptoWalletAPI.request("/wallets/");

        currentUserWallets = wallets.filter(function(w) {
            return w.wallet_status === "ACTIVE";
        });

        splitReceiverWallet.innerHTML = currentUserWallets
            .map(function(w) {
                return '<option value="' + w.wallet_id + '">' +
                    escapeHTML(w.name) + " (" + w.currency + ")</option>";
            })
            .join("");

    } catch (error) {

        // Silent.

    }

}


/* =====================================================
   CREATE SPLIT
===================================================== */

if (createSplitForm) {

    createSplitForm.addEventListener("submit", async function(event) {

        event.preventDefault();

        createSplitError.textContent = "";

        const walletId = splitReceiverWallet.value;
        const title = document.getElementById("splitTitle").value.trim();
        const total = document.getElementById("splitTotal").value;

        const rows = Array.prototype.slice.call(
            document.querySelectorAll(".participant-row")
        );

        const participants = rows.map(function(row) {

            return {
                phone: row.querySelector(".participant-phone").value.trim(),
                share_amount: row.querySelector(".participant-share").value
            };

        }).filter(function(p) {

            return p.phone && p.share_amount;

        });

        if (!walletId || !title || !total || participants.length === 0) {

            createSplitError.textContent =
                "Fill in the bill details and add at least one participant.";
            return;

        }

        try {

            await CryptoWalletAPI.request("/group-payments/", {

                method: "POST",
                body: {
                    receiver_wallet_id: walletId,
                    title: title,
                    total_amount: total,
                    participants: participants
                }

            });

            createSplitForm.reset();
            participantRows.innerHTML = "";
            addParticipantRow();

            showToast("Split created! Participants have been notified.");
            loadSplits();

        } catch (error) {

            createSplitError.textContent = error.message;

        }

    });

}


/* =====================================================
   LOAD + RENDER MY SPLITS
===================================================== */

async function loadSplits() {

    try {

        const splits = await CryptoWalletAPI.request("/group-payments/");

        if (splits.length === 0) {

            splitList.innerHTML = '<p class="hint">No splits yet.</p>';
            return;

        }

        splitList.innerHTML = splits.map(function(split) {

            const rowsHTML = split.participants.map(function(p) {

                return (
                    '<div class="list-row">' +
                        '<div>' +
                            escapeHTML(p.user_name) + ' (' + escapeHTML(p.user_phone) + ')' +
                            ' — ' + escapeHTML(p.share_amount) +
                            ' <span class="category-tag">' + escapeHTML(p.status) + '</span>' +
                        '</div>' +
                        '<div>' +
                            (p.status === "PENDING"
                                ? '<button class="pay-share-btn" data-group="' + split.group_payment_id + '">Pay My Share</button>'
                                : '') +
                        '</div>' +
                    '</div>'
                );

            }).join("");

            return (
                '<div class="card" style="margin-bottom:14px;">' +
                    '<strong>' + escapeHTML(split.title) + '</strong> — ' +
                    escapeHTML(split.total_amount) +
                    ' <span class="category-tag">' + escapeHTML(split.status) + '</span>' +
                    '<p class="hint">Organized by ' + escapeHTML(split.organizer_name) + '</p>' +
                    rowsHTML +
                '</div>'
            );

        }).join("");

        document.querySelectorAll(".pay-share-btn").forEach(function(button) {

            button.addEventListener("click", async function() {

                if (currentUserWallets.length === 0) {

                    showToast("No active wallet to pay from.");
                    return;

                }

                let payerWalletId = currentUserWallets[0].wallet_id;

                if (currentUserWallets.length > 1) {

                    const choice = window.prompt(
                        "Pay from which wallet?\n" +
                        currentUserWallets.map(function(w, i) {
                            return (i + 1) + ") " + w.name + " (" + w.currency + ", " + w.balance + ")";
                        }).join("\n"),
                        "1"
                    );

                    if (choice === null) return;

                    const index = parseInt(choice, 10) - 1;

                    if (isNaN(index) || !currentUserWallets[index]) {

                        showToast("Invalid choice.");
                        return;

                    }

                    payerWalletId = currentUserWallets[index].wallet_id;

                }

                try {

                    await CryptoWalletAPI.request(
                        "/group-payments/" + button.dataset.group + "/pay/",
                        {
                            method: "POST",
                            body: { payer_wallet_id: payerWalletId }
                        }
                    );

                    showToast("Your share has been paid!");
                    loadSplits();

                } catch (error) {

                    showToast(error.message);

                }

            });

        });

    } catch (error) {

        splitList.innerHTML = '<p class="hint">Couldn\'t load splits.</p>';

    }

}


/* =====================================================
   PROFILE (avatar initial)
===================================================== */

async function loadProfileForAvatar() {

    try {

        const user = await CryptoWalletAPI.request("/profile/");

        currentUserId = user.id;

        if (avatar) {

            avatar.textContent = user.name.charAt(0).toUpperCase();

        }

    } catch (error) {

        // Non-critical.

    }

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

loadProfileForAvatar();
loadWalletsForSplit().then(loadSplits);
addParticipantRow();
