/* =====================================================
   CRYPTOWALLET
   ADMIN MONITORING DASHBOARD (Django API version)

   Every endpoint this page calls requires an admin role on
   the backend — a non-staff user
   who somehow lands here just sees an access-denied message,
   since the real enforcement lives server-side regardless.
===================================================== */

if (!CryptoWalletAPI.requireAdmin("../login.html")) {
    throw new Error("Administrative access is required.");
}



/* =====================================================
   DOM
===================================================== */

const adminAccessError =
    document.getElementById("adminAccessError");

const adminContent =
    document.getElementById("adminContent");

const adminStats =
    document.getElementById("adminStats");

const volumeChart =
    document.getElementById("volumeChart");

const currencyVolumeTable =
    document.getElementById("currencyVolumeTable");

const flaggedUsersList =
    document.getElementById("flaggedUsersList");

const pendingKYCList =
    document.getElementById("pendingKYCList");

const avatar =
    document.getElementById("avatar");

const logout =
    document.getElementById("logout");

const toast =
    document.getElementById("toast");

const adminUsersList = document.getElementById("adminUsersList");
const adminUserSearch = document.getElementById("adminUserSearch");
const adminUserType = document.getElementById("adminUserType");
const adminDisputesList = document.getElementById("adminDisputesList");
const adminTransactionsList = document.getElementById("adminTransactionsList");
const adminFeeLimits = document.getElementById("adminFeeLimits");
const adminLiquidity = document.getElementById("adminLiquidity");
const adminAuditEvents = document.getElementById("adminAuditEvents");


/* =====================================================
   TOAST
===================================================== */

function showToast(message) {

    if (!toast) return;

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

    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;

}



/* =====================================================
   HEADLINE STATS
===================================================== */

function renderStats(summary) {

    if (!adminStats) return;

    const cards = [
        { label: "Total Users", value: summary.total_users },
        { label: "Active Users", value: summary.active_users },
        { label: "Flagged Accounts", value: summary.flagged_users },
        { label: "Pending KYC", value: summary.pending_kyc },
        { label: "Total Transactions", value: summary.total_transactions },
        { label: "Total Wallets", value: summary.total_wallets }
    ];

    adminStats.innerHTML = cards.map(function(card) {

        return (
            '<div class="stat-card">' +
                '<span class="stat-label">' + escapeHTML(card.label) + '</span>' +
                '<strong class="stat-value">' + escapeHTML(card.value) + '</strong>' +
            '</div>'
        );

    }).join("");

}



/* =====================================================
   VOLUME CHART (plain CSS bars — no chart library needed)
===================================================== */

function renderVolumeChart(dailySeries) {

    if (!volumeChart) return;

    if (!dailySeries || dailySeries.length === 0) {

        volumeChart.innerHTML = '<p class="hint">No transactions in the last 14 days.</p>';
        return;

    }

    const maxVolume = Math.max.apply(null, dailySeries.map(function(d) {
        return Number(d.volume);
    }));

    volumeChart.innerHTML = dailySeries.map(function(day) {

        const heightPct = maxVolume > 0
            ? Math.max(4, (Number(day.volume) / maxVolume) * 100)
            : 4;

        const dateLabel = new Date(day.day).toLocaleDateString(undefined, {
            month: "short", day: "numeric"
        });

        return (
            '<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;">' +
                '<div title="' + escapeHTML(day.count) + ' txns, ' + escapeHTML(day.volume) + ' volume" ' +
                    'style="width:100%;background:linear-gradient(180deg,#5b6cff,#7b8cff);border-radius:4px 4px 0 0;height:' +
                    heightPct + '%;min-height:4px;"></div>' +
                '<small class="hint" style="margin-top:6px;font-size:11px;white-space:nowrap;">' +
                    escapeHTML(dateLabel) +
                '</small>' +
            '</div>'
        );

    }).join("");

}



/* =====================================================
   VOLUME BY CURRENCY
===================================================== */

function renderCurrencyVolume(rows) {

    if (!currencyVolumeTable) return;

    if (!rows || rows.length === 0) {

        currencyVolumeTable.innerHTML = '<p class="hint">No transaction volume yet.</p>';
        return;

    }

    currencyVolumeTable.innerHTML = rows.map(function(row) {

        return (
            '<div class="list-row">' +
                '<div><strong>' + escapeHTML(row.currency) + '</strong></div>' +
                '<div>' + escapeHTML(row.count) + ' transactions</div>' +
                '<div>' + escapeHTML(row.total) + ' total</div>' +
            '</div>'
        );

    }).join("");

}



/* =====================================================
   FLAGGED USERS (FRAUD REVIEW)
===================================================== */

async function loadFlaggedUsers() {

    if (!flaggedUsersList) return;

    try {

        const users = await CryptoWalletAPI.request("/admin/flagged-users/");

        if (users.length === 0) {

            flaggedUsersList.innerHTML = '<p class="hint">No flagged accounts right now. 🎉</p>';
            return;

        }

        flaggedUsersList.innerHTML = users.map(function(user) {

            return (
                '<div class="list-row" data-id="' + user.id + '">' +
                    '<div>' +
                        '<strong>' + escapeHTML(user.name) + '</strong> (' + escapeHTML(user.phone) + ')' +
                        '<br><small class="hint">' + escapeHTML(user.email) + '</small>' +
                    '</div>' +
                    '<div>' +
                        '<button class="clear-flag-btn" data-id="' + user.id + '">Clear Flag</button>' +
                    '</div>' +
                '</div>'
            );

        }).join("");

        document.querySelectorAll(".clear-flag-btn").forEach(function(button) {

            button.addEventListener("click", async function() {

                try {

                    await CryptoWalletAPI.request(
                        "/admin/flagged-users/" + button.dataset.id + "/clear/",
                        { method: "POST" }
                    );

                    showToast("Flag cleared.");
                    loadFlaggedUsers();
                    loadSummary();

                }

                catch (error) {

                    showToast(error.message);

                }

            });

        });

    }

    catch (error) {

        flaggedUsersList.innerHTML = '<p class="hint">Couldn\'t load flagged accounts.</p>';

    }

}



/* =====================================================
   PENDING KYC
===================================================== */

async function loadAdminUsers() {
    if (!adminUsersList) return;
    const params = new URLSearchParams();
    if (adminUserSearch && adminUserSearch.value) params.set("search", adminUserSearch.value);
    if (adminUserType && adminUserType.value) params.set("account_type", adminUserType.value);
    try {
        const users = await CryptoWalletAPI.request("/admin/users/?" + params.toString());
        adminUsersList.innerHTML = users.length ? users.map(function(user) {
            const next = user.status === "ACTIVE" ? "SUSPENDED" : "ACTIVE";
            return '<div class="list-row"><div><strong>' + escapeHTML(user.name) +
                '</strong> <small class="hint">' + escapeHTML(user.account_type) +
                '</small><br><small class="hint">' + escapeHTML(user.email) +
                ' · ' + escapeHTML(user.phone) + '</small></div><div>' +
                '<span class="hint">' + escapeHTML(user.status) + '</span> ' +
                '<button class="admin-status-btn" data-id="' + user.id +
                '" data-status="' + next + '">' + (next === "ACTIVE" ? "Activate" : "Suspend") +
                '</button></div></div>';
        }).join("") : '<p class="hint">No matching accounts.</p>';
        document.querySelectorAll(".admin-status-btn").forEach(function(button) {
            button.addEventListener("click", async function() {
                try {
                    await CryptoWalletAPI.request("/admin/users/" + button.dataset.id + "/status/", {
                        method: "POST", body: { status: button.dataset.status }
                    });
                    showToast("Account status updated.");
                    loadAdminUsers();
                } catch (error) { showToast(error.message); }
            });
        });
    } catch (error) {
        adminUsersList.innerHTML = '<p class="hint">Couldn\'t load accounts.</p>';
    }
}

async function loadAdminControls() {
    if (!adminDisputesList) return;
    try {
        const transactions = await CryptoWalletAPI.request("/admin/transactions/?limit=10");
        adminTransactionsList.innerHTML = transactions.length ? transactions.map(function(tx) {
            const canReverse = tx.status === "COMPLETED" && tx.transaction_type !== "REVERSAL";
            return '<div class="list-row"><div><strong>' + escapeHTML(tx.transaction_id) +
                '</strong><br><small class="hint">' + escapeHTML(tx.transaction_type) +
                ' · ' + escapeHTML(tx.amount) + ' · ' + escapeHTML(tx.date) +
                '</small></div><div><span class="hint">' + escapeHTML(tx.status) + '</span>' +
                (canReverse
                    ? ' <button class="reverse-transaction-btn" data-id="' +
                      escapeHTML(tx.transaction_id) + '">Reverse</button>'
                    : '') +
                '</div></div>';
        }).join("") : '<p class="hint">No transactions recorded.</p>';
        document.querySelectorAll(".reverse-transaction-btn").forEach(function(button) {
            button.addEventListener("click", async function() {
                const reason = window.prompt(
                    "Enter the reason. The original transaction will be preserved and a compensating transaction will be created:"
                );
                if (!reason || !reason.trim()) return;
                if (!window.confirm("Confirm reversal of " + button.dataset.id + "?")) return;
                try {
                    await CryptoWalletAPI.request(
                        "/admin/transactions/" + button.dataset.id + "/reverse/",
                        { method: "POST", body: { reason: reason.trim() } }
                    );
                    showToast("Transaction reversed and balances compensated.");
                    loadAdminControls();
                    loadSummary();
                } catch (error) {
                    showToast(error.message);
                }
            });
        });
        const disputes = await CryptoWalletAPI.request("/admin/disputes/?status=OPEN");
        adminDisputesList.innerHTML = disputes.length ? disputes.map(function(dispute) {
            return '<div class="list-row"><div><strong>' + escapeHTML(dispute.dispute_id) +
                '</strong><br><small class="hint">' + escapeHTML(dispute.reason) +
                ' · ' + escapeHTML(dispute.amount) + ' ' + escapeHTML(dispute.currency) +
                '</small></div><button class="resolve-dispute-btn" data-id="' +
                escapeHTML(dispute.dispute_id) + '">Resolve</button></div>';
        }).join("") : '<p class="hint">No open disputes.</p>';
        document.querySelectorAll(".resolve-dispute-btn").forEach(function(button) {
            button.addEventListener("click", async function() {
                const resolution = window.prompt("Resolution notes:") || "";
                if (!resolution) return;
                try {
                    await CryptoWalletAPI.request("/admin/disputes/" + button.dataset.id + "/resolve/", {
                        method: "POST", body: { status: "RESOLVED", resolution: resolution }
                    });
                    showToast("Dispute resolved.");
                    loadAdminControls();
                } catch (error) { showToast(error.message); }
            });
        });
        const fees = await CryptoWalletAPI.request("/admin/fees-limits/");
        adminFeeLimits.innerHTML = fees.length ? fees.map(function(config) {
            return '<div class="list-row"><strong>' + escapeHTML(config.config_key) +
                '</strong><span>' + escapeHTML(config.fee_percent) + '% · daily ' +
                escapeHTML(config.daily_limit || "unlimited") + '</span></div>';
        }).join("") : '<p class="hint">No configurable fee or limit policies.</p>';
        const liquidity = await CryptoWalletAPI.request("/admin/liquidity/");
        adminLiquidity.innerHTML = (liquidity.wallet_balances || []).map(function(row) {
            return '<div class="list-row"><strong>' + escapeHTML(row.currency) +
                '</strong><span>Customer balance ' + escapeHTML(row.customer_balance) +
                ' · ' + escapeHTML(row.wallet_count) + ' wallets</span></div>';
        }).join("");
        const events = await CryptoWalletAPI.request("/admin/audit-events/?limit=20");
        adminAuditEvents.innerHTML = events.length ? events.map(function(event) {
            return '<div class="list-row"><div><strong>' + escapeHTML(event.action) +
                '</strong> · ' + escapeHTML(event.resource_type) + '</div><small class="hint">' +
                escapeHTML(event.created_at) + ' · hash ' + escapeHTML(event.event_hash) + '</small></div>';
        }).join("") : '<p class="hint">No admin events recorded.</p>';
    } catch (error) {
        adminDisputesList.innerHTML = '<p class="hint">Control-plane data requires finance/operations access.</p>';
    }
}

async function loadPendingKYC() {

    if (!pendingKYCList) return;

    try {

        const submissions = await CryptoWalletAPI.request("/admin/kyc/");

        const pending = submissions.filter(function(k) {
            return k.verification_status === "PENDING";
        });

        if (pending.length === 0) {

            pendingKYCList.innerHTML = '<p class="hint">No pending KYC submissions.</p>';
            return;

        }

        pendingKYCList.innerHTML = pending.map(function(kyc) {

            return (
                '<div class="list-row" data-id="' + kyc.id + '">' +
                    '<div>' +
                        '<strong>' + escapeHTML(kyc.user_name || kyc.user) + '</strong>' +
                        '<br><small class="hint">NID: ' + escapeHTML(kyc.nid_number || "—") +
                        ' · Passport: ' + escapeHTML(kyc.passport_number || "—") + '</small>' +
                    '</div>' +
                    '<div>' +
                        '<button class="approve-kyc-btn" data-id="' + kyc.id + '">Approve</button> ' +
                        '<button class="reject-kyc-btn" data-id="' + kyc.id + '">Reject</button>' +
                    '</div>' +
                '</div>'
            );

        }).join("");

        document.querySelectorAll(".approve-kyc-btn").forEach(function(button) {

            button.addEventListener("click", async function() {

                try {

                    await CryptoWalletAPI.request(
                        "/admin/kyc/" + button.dataset.id + "/approve/",
                        { method: "POST" }
                    );

                    showToast("KYC approved.");
                    loadPendingKYC();
                    loadSummary();

                }

                catch (error) {

                    showToast(error.message);

                }

            });

        });

        document.querySelectorAll(".reject-kyc-btn").forEach(function(button) {

            button.addEventListener("click", async function() {

                const remarks = window.prompt("Reason for rejection (optional):") || "";

                try {

                    await CryptoWalletAPI.request(
                        "/admin/kyc/" + button.dataset.id + "/reject/",
                        { method: "POST", body: { remarks: remarks } }
                    );

                    showToast("KYC rejected.");
                    loadPendingKYC();
                    loadSummary();

                }

                catch (error) {

                    showToast(error.message);

                }

            });

        });

    }

    catch (error) {

        pendingKYCList.innerHTML = '<p class="hint">Couldn\'t load KYC submissions.</p>';

    }

}



/* =====================================================
   LOAD SUMMARY (STATS + CHART + CURRENCY BREAKDOWN)
===================================================== */

async function loadSummary() {

    try {

        const summary = await CryptoWalletAPI.request("/admin/analytics/summary/");

        adminAccessError.style.display = "none";
        adminContent.style.display = "block";

        renderStats(summary);
        renderVolumeChart(summary.daily_series);
        renderCurrencyVolume(summary.volume_by_currency);

    }

    catch (error) {

        adminContent.style.display = "none";
        adminAccessError.style.display = "block";

        adminAccessError.textContent =
            error.status === 403 || error.status === 401
                ? "You don't have admin access. This page is for staff accounts only."
                : ("Couldn't load admin data: " + error.message);

    }

}



/* =====================================================
   PROFILE (avatar initial)
===================================================== */

async function loadProfileForAvatar() {

    try {

        const user = await CryptoWalletAPI.request("/profile/");

        if (avatar) {

            avatar.textContent = user.name.charAt(0).toUpperCase();

        }

    }

    catch (error) {

        // Non-critical — avatar just stays at its default letter.

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
loadSummary();
loadFlaggedUsers();
loadPendingKYC();
loadAdminUsers();
loadAdminControls();
if (document.getElementById("adminUserRefresh")) {
    document.getElementById("adminUserRefresh").addEventListener("click", loadAdminUsers);
}
