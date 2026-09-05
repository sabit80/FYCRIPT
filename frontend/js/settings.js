/* =====================================================
   CRYPTOWALLET
   SETTINGS PAGE (Django API version)
===================================================== */

CryptoWalletAPI.requireLogin("../login.html");



/* =====================================================
   DOM
===================================================== */

const profileForm =
    document.getElementById("profileForm");

const nameInput =
    document.getElementById("name");

const emailInput =
    document.getElementById("email");

const phoneInput =
    document.getElementById("phone");

const nameError =
    document.getElementById("nameError");

const passwordForm =
    document.getElementById("passwordForm");

const currentPasswordInput =
    document.getElementById("currentPassword");

const newPasswordInput =
    document.getElementById("newPassword");

const confirmNewPasswordInput =
    document.getElementById("confirmNewPassword");

const currentPasswordError =
    document.getElementById("currentPasswordError");

const newPasswordError =
    document.getElementById("newPasswordError");

const confirmNewPasswordError =
    document.getElementById("confirmNewPasswordError");

const avatar =
    document.getElementById("avatar");

const logout =
    document.getElementById("logout");

const toast =
    document.getElementById("toast");



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
   LOAD PROFILE
===================================================== */

async function loadProfile() {

    try {

        const user =
            await CryptoWalletAPI.request("/profile/");

        nameInput.value = user.name;
        emailInput.value = user.email;

        if (phoneInput) {

            phoneInput.value = user.phone;

        }

        if (avatar) {

            avatar.textContent = user.name.charAt(0).toUpperCase();

        }

        /*
            Keep sessionStorage's cached name in sync in case
            it drifted (e.g. updated from another tab).
        */
        sessionStorage.setItem("userName", user.name);

    }

    catch (error) {

        showToast(error.message);

    }

}



/* =====================================================
   UPDATE PROFILE
===================================================== */

if (profileForm) {

    profileForm.addEventListener("submit", async function(event) {

        event.preventDefault();

        nameError.textContent = "";

        const newName =
            nameInput.value.trim();

        if (!newName) {

            nameError.textContent = "Please enter your name.";
            return;

        }

        try {

            const user =
                await CryptoWalletAPI.request("/profile/", {

                    method: "PATCH",
                    body: { name: newName }

                });

            sessionStorage.setItem("userName", user.name);

            if (avatar) {

                avatar.textContent = user.name.charAt(0).toUpperCase();

            }

            showToast("Profile updated!");

        }

        catch (error) {

            nameError.textContent = error.message;

        }

    });

}



/* =====================================================
   UPDATE PASSWORD
===================================================== */

if (passwordForm) {

    passwordForm.addEventListener("submit", async function(event) {

        event.preventDefault();

        [currentPasswordError, newPasswordError, confirmNewPasswordError]
            .forEach(function(el) { el.textContent = ""; });


        if (newPasswordInput.value.length < 6) {

            newPasswordError.textContent =
                "Password must contain at least 6 characters.";
            return;

        }

        if (newPasswordInput.value !== confirmNewPasswordInput.value) {

            confirmNewPasswordError.textContent =
                "Passwords do not match.";
            return;

        }

        try {

            await CryptoWalletAPI.request("/profile/change-password/", {

                method: "POST",
                body: {
                    currentPassword: currentPasswordInput.value,
                    newPassword: newPasswordInput.value
                }

            });

            passwordForm.reset();

            showToast("Password updated!");

        }

        catch (error) {

            if (error.data && error.data.currentPassword) {

                currentPasswordError.textContent =
                    Array.isArray(error.data.currentPassword)
                        ? error.data.currentPassword[0]
                        : error.data.currentPassword;

            }

            else {

                showToast(error.message);

            }

        }

    });

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
   BANK ACCOUNTS
===================================================== */

const bankAccountList =
    document.getElementById("bankAccountList");

const bankAccountForm =
    document.getElementById("bankAccountForm");

const bankNameInput =
    document.getElementById("bankName");

const bankAccountNumberInput =
    document.getElementById("bankAccountNumber");

const bankNameError =
    document.getElementById("bankNameError");

const bankAccountNumberError =
    document.getElementById("bankAccountNumberError");


function escapeHTML(value) {

    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;

}


async function loadBankAccounts() {

    if (!bankAccountList) return;

    try {

        const accounts =
            await CryptoWalletAPI.request("/bank-accounts/");

        if (accounts.length === 0) {

            bankAccountList.innerHTML =
                "<p class=\"hint\">No bank accounts connected yet.</p>";
            return;

        }

        bankAccountList.innerHTML =
            accounts.map(function(account) {

                return (
                    "<div class=\"bank-account-row\">" +
                        "<span>" +
                            escapeHTML(account.bank_name) + " — " +
                            escapeHTML(account.account_number) +
                        "</span>" +
                        "<div class=\"bank-account-actions\">" +
                            "<button type=\"button\" class=\"deposit-bank\" data-id=\"" +
                                account.id + "\" data-bank=\"" + escapeHTML(account.bank_name) +
                                "\">Deposit</button>" +
                            "<button type=\"button\" class=\"withdraw-bank\" data-id=\"" +
                                account.id + "\" data-bank=\"" + escapeHTML(account.bank_name) +
                                "\">Withdraw</button>" +
                            "<button type=\"button\" class=\"remove-bank\" data-id=\"" +
                                account.id + "\">Remove</button>" +
                        "</div>" +
                    "</div>"
                );

            }).join("");

        bankAccountList.querySelectorAll(".remove-bank").forEach(function(button) {

            button.addEventListener("click", async function() {

                try {

                    await CryptoWalletAPI.request(
                        "/bank-accounts/" + button.dataset.id + "/",
                        { method: "DELETE" }
                    );

                    await loadBankAccounts();
                    showToast("Bank account removed.");

                }

                catch (error) {

                    showToast(error.message);

                }

            });

        });

        bankAccountList.querySelectorAll(".deposit-bank").forEach(function(button) {
            button.addEventListener("click", function() {
                runBankTransfer(button.dataset.id, button.dataset.bank, "deposit");
            });
        });

        bankAccountList.querySelectorAll(".withdraw-bank").forEach(function(button) {
            button.addEventListener("click", function() {
                runBankTransfer(button.dataset.id, button.dataset.bank, "withdraw");
            });
        });

    }

    catch (error) {

        showToast(error.message);

    }

}


/* =====================================================
   BANK DEPOSIT / WITHDRAW

   Simple prompt()-based flow: pick one of your wallets by
   ID (shown in the list) and an amount, then call the
   matching backend endpoint. Money only ever moves between
   a wallet you own and a bank account you own — no real
   bank connection, this is a simulated transfer for the
   project.
===================================================== */

async function runBankTransfer(bankAccountId, bankName, direction) {

    let wallets;

    try {
        wallets = await CryptoWalletAPI.request("/wallets/");
    }
    catch (error) {
        showToast("Couldn't load your wallets.");
        return;
    }

    if (!wallets || wallets.length === 0) {
        showToast("Create a wallet first.");
        return;
    }

    const walletChoices = wallets.map(function(w) {
        return w.wallet_id + "  (" + w.name + " — " + w.currency + " " + w.balance + ")";
    }).join("\n");

    const walletId = window.prompt(
        (direction === "deposit"
            ? "Deposit into which wallet? (from " + bankName + ")"
            : "Withdraw from which wallet? (to " + bankName + ")") +
        "\n\nYour wallets:\n" + walletChoices +
        "\n\nEnter the Wallet ID exactly as shown above:"
    );

    if (!walletId) return;

    const amountRaw = window.prompt("Amount:");
    if (!amountRaw) return;

    const amount = Number(amountRaw);
    if (!amount || amount <= 0) {
        showToast("Enter a valid amount.");
        return;
    }

    try {

        await CryptoWalletAPI.request(
            "/bank-accounts/" + bankAccountId + "/" + direction + "/",
            {
                method: "POST",
                body: { wallet_id: walletId.trim(), amount: amount }
            }
        );

        showToast(
            direction === "deposit"
                ? "Deposit successful."
                : "Withdrawal successful."
        );

    }

    catch (error) {

        showToast(error.message || "Transfer failed.");

    }

}


if (bankAccountForm) {

    bankAccountForm.addEventListener("submit", async function(event) {

        event.preventDefault();

        bankNameError.textContent = "";
        bankAccountNumberError.textContent = "";

        try {

            await CryptoWalletAPI.request("/bank-accounts/", {

                method: "POST",
                body: {
                    bank_name: bankNameInput.value.trim(),
                    account_number: bankAccountNumberInput.value.trim()
                }

            });

            bankAccountForm.reset();
            await loadBankAccounts();
            showToast("Bank account added.");

        }

        catch (error) {

            if (error.data && error.data.bank_name) {

                bankNameError.textContent =
                    Array.isArray(error.data.bank_name)
                        ? error.data.bank_name[0]
                        : error.data.bank_name;

            }

            else if (error.data && error.data.account_number) {

                bankAccountNumberError.textContent =
                    Array.isArray(error.data.account_number)
                        ? error.data.account_number[0]
                        : error.data.account_number;

            }

            else {

                showToast(error.message);

            }

        }

    });

}



/* =====================================================
   KYC
===================================================== */

const kycForm =
    document.getElementById("kycForm");

const nidNumberInput =
    document.getElementById("nidNumber");

const passportNumberInput =
    document.getElementById("passportNumber");

const nidNumberError =
    document.getElementById("nidNumberError");

const passportNumberError =
    document.getElementById("passportNumberError");

const kycStatusHint =
    document.getElementById("kycStatusHint");


async function loadKYC() {

    if (!kycStatusHint) return;

    try {

        const kyc =
            await CryptoWalletAPI.request("/kyc/");

        nidNumberInput.value = kyc.nid_number || "";
        passportNumberInput.value = kyc.passport_number || "";
        kycStatusHint.textContent =
            "Status: " + kyc.verification_status +
            " (submitted " + new Date(kyc.submission_date).toLocaleDateString() + ")";

    }

    catch (error) {

        kycStatusHint.textContent = "Submit your ID to verify your account.";

    }

}


if (kycForm) {

    kycForm.addEventListener("submit", async function(event) {

        event.preventDefault();

        nidNumberError.textContent = "";
        passportNumberError.textContent = "";

        const nid = nidNumberInput.value.trim();
        const passport = passportNumberInput.value.trim();

        if (!nid && !passport) {

            nidNumberError.textContent =
                "Provide at least an NID number or a passport number.";
            return;

        }

        try {

            await CryptoWalletAPI.request("/kyc/", {

                method: "POST",
                body: {
                    nid_number: nid || null,
                    passport_number: passport || null
                }

            });

            await loadKYC();
            showToast("KYC submitted for review.");

        }

        catch (error) {

            showToast(error.message);

        }

    });

}



/* =====================================================
   INITIAL LOAD
===================================================== */

loadProfile();
loadBankAccounts();
loadKYC();
load2FAStatus();
loadScheduledPayments();
populateSchedWalletSelect();



/* =====================================================
   TWO-FACTOR AUTHENTICATION
===================================================== */

const twoFAStatusHint = document.getElementById("twoFAStatusHint");
const twoFADisabledBlock = document.getElementById("twoFADisabledBlock");
const twoFASetupBlock = document.getElementById("twoFASetupBlock");
const twoFARecoveryBlock = document.getElementById("twoFARecoveryBlock");
const twoFAEnabledBlock = document.getElementById("twoFAEnabledBlock");
const start2FASetupButton = document.getElementById("start2FASetupButton");
const confirm2FAButton = document.getElementById("confirm2FAButton");
const disable2FAButton = document.getElementById("disable2FAButton");
const twoFAQRImage = document.getElementById("twoFAQRImage");
const twoFASecretText = document.getElementById("twoFASecretText");
const twoFAConfirmCode = document.getElementById("twoFAConfirmCode");
const twoFAConfirmError = document.getElementById("twoFAConfirmError");
const twoFARecoveryCodes = document.getElementById("twoFARecoveryCodes");
const disable2FAPassword = document.getElementById("disable2FAPassword");
const disable2FAError = document.getElementById("disable2FAError");

async function load2FAStatus() {

    if (!twoFAStatusHint) return;

    try {

        const user = await CryptoWalletAPI.request("/profile/");

        if (user.two_factor_enabled) {

            twoFAStatusHint.textContent = "2FA is currently ON for your account.";
            twoFADisabledBlock.style.display = "none";
            twoFAEnabledBlock.style.display = "block";

        } else {

            twoFAStatusHint.textContent = "2FA is currently OFF. Turn it on for extra security.";
            twoFADisabledBlock.style.display = "block";
            twoFAEnabledBlock.style.display = "none";

        }

    } catch (error) {

        twoFAStatusHint.textContent = "Couldn't load 2FA status.";

    }

}

if (start2FASetupButton) {

    start2FASetupButton.addEventListener("click", async function() {

        try {

            const data = await CryptoWalletAPI.request("/profile/2fa/setup/", {
                method: "POST"
            });

            twoFAQRImage.src = data.qr_code_base64;
            twoFASecretText.textContent = data.secret;
            twoFASetupBlock.style.display = "block";
            twoFADisabledBlock.style.display = "none";

        } catch (error) {

            showToast(error.message);

        }

    });

}

if (confirm2FAButton) {

    confirm2FAButton.addEventListener("click", async function() {

        twoFAConfirmError.textContent = "";

        const code = twoFAConfirmCode.value.trim();

        if (!code) {
            twoFAConfirmError.textContent = "Enter the code from your app.";
            return;
        }

        try {

            const data = await CryptoWalletAPI.request("/profile/2fa/confirm/", {
                method: "POST",
                body: { code: code }
            });

            twoFASetupBlock.style.display = "none";
            twoFARecoveryBlock.style.display = "block";
            twoFARecoveryCodes.innerHTML = data.recovery_codes
                .map(function(c) { return "<div>" + escapeHTML(c) + "</div>"; })
                .join("");

            showToast("Two-factor authentication enabled!");
            load2FAStatus();

        } catch (error) {

            twoFAConfirmError.textContent = error.message;

        }

    });

}

if (disable2FAButton) {

    disable2FAButton.addEventListener("click", async function() {

        disable2FAError.textContent = "";

        const password = disable2FAPassword.value;

        if (!password) {
            disable2FAError.textContent = "Enter your password.";
            return;
        }

        try {

            await CryptoWalletAPI.request("/profile/2fa/disable/", {
                method: "POST",
                body: { password: password }
            });

            disable2FAPassword.value = "";
            showToast("Two-factor authentication disabled.");
            load2FAStatus();

        } catch (error) {

            disable2FAError.textContent = error.message;

        }

    });

}



/* =====================================================
   SCHEDULED / RECURRING PAYMENTS
===================================================== */

const scheduledPaymentList = document.getElementById("scheduledPaymentList");
const scheduledPaymentForm = document.getElementById("scheduledPaymentForm");
const schedWalletSelect = document.getElementById("schedWalletSelect");
const scheduledPaymentError = document.getElementById("scheduledPaymentError");

async function populateSchedWalletSelect() {

    if (!schedWalletSelect) return;

    try {

        const wallets = await CryptoWalletAPI.request("/wallets/");

        schedWalletSelect.innerHTML = wallets
            .filter(function(w) { return w.wallet_status === "ACTIVE"; })
            .map(function(w) {
                return '<option value="' + w.wallet_id + '">' +
                    escapeHTML(w.name) + " (" + w.currency + ", " + w.balance + ")</option>";
            })
            .join("");

    } catch (error) {

        // Silent — the form just won't have options if this fails.

    }

}

async function loadScheduledPayments() {

    if (!scheduledPaymentList) return;

    try {

        const schedules = await CryptoWalletAPI.request("/scheduled-payments/");

        if (schedules.length === 0) {

            scheduledPaymentList.innerHTML =
                '<p class="hint">No scheduled payments yet.</p>';
            return;

        }

        scheduledPaymentList.innerHTML = schedules.map(function(s) {

            const target = s.recipient_phone || s.recipient_wallet_id || "—";

            return (
                '<div class="list-row" data-id="' + s.schedule_id + '">' +
                    '<div>' +
                        '<strong>' + escapeHTML(String(s.amount)) + '</strong> to ' +
                        escapeHTML(target) + ' — ' + escapeHTML(s.frequency) +
                        '<br><small class="hint">Next: ' +
                        new Date(s.next_run_at).toLocaleString() +
                        ' · Status: ' + escapeHTML(s.status) +
                        (s.note ? ' · ' + escapeHTML(s.note) : '') +
                        '</small>' +
                    '</div>' +
                    '<div>' +
                        (s.status !== "CANCELLED"
                            ? '<button class="sched-pause-btn" data-id="' + s.schedule_id + '">' +
                              (s.status === "PAUSED" ? "Resume" : "Pause") + '</button> ' +
                              '<button class="sched-cancel-btn" data-id="' + s.schedule_id + '">Cancel</button>'
                            : '') +
                    '</div>' +
                '</div>'
            );

        }).join("");

        Array.prototype.forEach.call(
            document.querySelectorAll(".sched-pause-btn"),
            function(button) {

                button.addEventListener("click", async function() {

                    try {

                        await CryptoWalletAPI.request(
                            "/scheduled-payments/" + button.dataset.id + "/pause-toggle/",
                            { method: "POST" }
                        );

                        loadScheduledPayments();

                    } catch (error) {

                        showToast(error.message);

                    }

                });

            }
        );

        Array.prototype.forEach.call(
            document.querySelectorAll(".sched-cancel-btn"),
            function(button) {

                button.addEventListener("click", async function() {

                    try {

                        await CryptoWalletAPI.request(
                            "/scheduled-payments/" + button.dataset.id + "/cancel/",
                            { method: "POST" }
                        );

                        loadScheduledPayments();

                    } catch (error) {

                        showToast(error.message);

                    }

                });

            }
        );

    } catch (error) {

        scheduledPaymentList.innerHTML =
            '<p class="hint">Couldn\'t load scheduled payments.</p>';

    }

}

if (scheduledPaymentForm) {

    scheduledPaymentForm.addEventListener("submit", async function(event) {

        event.preventDefault();

        scheduledPaymentError.textContent = "";

        const walletId = schedWalletSelect.value;
        const phone = document.getElementById("schedRecipientPhone").value.trim();
        const amount = document.getElementById("schedAmount").value;
        const frequency = document.getElementById("schedFrequency").value;
        const nextRun = document.getElementById("schedNextRun").value;
        const note = document.getElementById("schedNote").value.trim();

        if (!walletId || !phone || !amount || !nextRun) {

            scheduledPaymentError.textContent = "Please fill in all required fields.";
            return;

        }

        try {

            await CryptoWalletAPI.request("/scheduled-payments/", {

                method: "POST",
                body: {
                    sender_wallet_id: walletId,
                    recipient_phone: phone,
                    amount: amount,
                    frequency: frequency,
                    next_run_at: new Date(nextRun).toISOString(),
                    note: note
                }

            });

            scheduledPaymentForm.reset();
            showToast("Scheduled payment created!");
            loadScheduledPayments();

        } catch (error) {

            scheduledPaymentError.textContent = error.message;

        }

    });

}



/* =====================================================
   ACCOUNT TYPE (PERSONAL / MERCHANT)
===================================================== */

const accountTypeSelect = document.getElementById("accountTypeSelect");
const businessNameGroup = document.getElementById("businessNameGroup");
const businessNameInput = document.getElementById("businessNameInput");
const saveAccountTypeButton = document.getElementById("saveAccountTypeButton");
const accountTypeError = document.getElementById("accountTypeError");
const paymentLinksSection = document.getElementById("paymentLinksSection");

function toggleBusinessNameVisibility() {

    if (!accountTypeSelect) return;

    const isMerchant = accountTypeSelect.value === "MERCHANT";
    businessNameGroup.style.display = isMerchant ? "block" : "none";
    if (paymentLinksSection) paymentLinksSection.style.display = isMerchant ? "block" : "none";

}

async function loadAccountType() {

    if (!accountTypeSelect) return;

    try {

        const user = await CryptoWalletAPI.request("/profile/");

        accountTypeSelect.value = user.account_type || "PERSONAL";
        businessNameInput.value = user.business_name || "";
        toggleBusinessNameVisibility();

        if (user.account_type === "MERCHANT") {

            loadPaymentLinks();
            populateLinkWalletSelect();

        }

    } catch (error) {

        // Non-critical.

    }

}

if (accountTypeSelect) {

    accountTypeSelect.addEventListener("change", toggleBusinessNameVisibility);

}

if (saveAccountTypeButton) {

    saveAccountTypeButton.addEventListener("click", async function() {

        accountTypeError.textContent = "";

        try {

            await CryptoWalletAPI.request("/profile/account-type/", {

                method: "POST",
                body: {
                    account_type: accountTypeSelect.value,
                    business_name: businessNameInput.value.trim()
                }

            });

            showToast("Account type updated!");
            toggleBusinessNameVisibility();

            if (accountTypeSelect.value === "MERCHANT") {

                loadPaymentLinks();
                populateLinkWalletSelect();

            }

        } catch (error) {

            accountTypeError.textContent = error.message;

        }

    });

}



/* =====================================================
   MERCHANT PAYMENT LINKS
===================================================== */

const paymentLinkList = document.getElementById("paymentLinkList");
const paymentLinkForm = document.getElementById("paymentLinkForm");
const linkWalletSelect = document.getElementById("linkWalletSelect");
const paymentLinkError = document.getElementById("paymentLinkError");

async function populateLinkWalletSelect() {

    if (!linkWalletSelect) return;

    try {

        const wallets = await CryptoWalletAPI.request("/wallets/");

        linkWalletSelect.innerHTML = wallets
            .filter(function(w) { return w.wallet_status === "ACTIVE"; })
            .map(function(w) {
                return '<option value="' + w.wallet_id + '">' +
                    escapeHTML(w.name) + " (" + w.currency + ")</option>";
            })
            .join("");

    } catch (error) {

        // Silent.

    }

}

async function loadPaymentLinks() {

    if (!paymentLinkList) return;

    try {

        const links = await CryptoWalletAPI.request("/payment-links/");

        if (links.length === 0) {

            paymentLinkList.innerHTML = '<p class="hint">No payment links yet.</p>';
            return;

        }

        const baseUrl = window.location.origin + window.location.pathname.replace("settings.html", "pay.html");

        paymentLinkList.innerHTML = links.map(function(link) {

            const url = baseUrl + "?link=" + link.link_id;

            return (
                '<div class="list-row">' +
                    '<div>' +
                        '<strong>' + escapeHTML(link.title) + '</strong>' +
                        (link.amount ? ' — ' + escapeHTML(link.amount) : ' — any amount') +
                        '<br><small class="hint">' + escapeHTML(url) + '</small>' +
                    '</div>' +
                    '<div>' +
                        '<button class="copy-link-btn" data-url="' + escapeHTML(url) + '">Copy Link</button>' +
                    '</div>' +
                '</div>'
            );

        }).join("");

        document.querySelectorAll(".copy-link-btn").forEach(function(button) {

            button.addEventListener("click", async function() {

                try {

                    await navigator.clipboard.writeText(button.dataset.url);
                    showToast("Link copied!");

                } catch (error) {

                    showToast("Couldn't copy the link.");

                }

            });

        });

    } catch (error) {

        paymentLinkList.innerHTML = '<p class="hint">Couldn\'t load payment links.</p>';

    }

}

if (paymentLinkForm) {

    paymentLinkForm.addEventListener("submit", async function(event) {

        event.preventDefault();

        paymentLinkError.textContent = "";

        const walletId = linkWalletSelect.value;
        const title = document.getElementById("linkTitle").value.trim();
        const amount = document.getElementById("linkAmount").value;

        if (!walletId || !title) {

            paymentLinkError.textContent = "Please fill in the required fields.";
            return;

        }

        try {

            await CryptoWalletAPI.request("/payment-links/", {

                method: "POST",
                body: {
                    receiving_wallet: walletId,
                    title: title,
                    amount: amount || null
                }

            });

            paymentLinkForm.reset();
            showToast("Payment link created!");
            loadPaymentLinks();

        } catch (error) {

            paymentLinkError.textContent = error.message;

        }

    });

}



/* =====================================================
   SAVINGS GOALS
===================================================== */

const savingsGoalList = document.getElementById("savingsGoalList");
const savingsGoalForm = document.getElementById("savingsGoalForm");
const savingsWalletSelect = document.getElementById("savingsWalletSelect");
const savingsGoalError = document.getElementById("savingsGoalError");

async function populateSavingsWalletSelect() {

    if (!savingsWalletSelect) return;

    try {

        const wallets = await CryptoWalletAPI.request("/wallets/");

        savingsWalletSelect.innerHTML = wallets
            .filter(function(w) { return w.wallet_status === "ACTIVE"; })
            .map(function(w) {
                return '<option value="' + w.wallet_id + '">' +
                    escapeHTML(w.name) + " (" + w.currency + ", " + w.balance + ")</option>";
            })
            .join("");

    } catch (error) {

        // Silent.

    }

}

async function loadSavingsGoals() {

    if (!savingsGoalList) return;

    try {

        const goals = await CryptoWalletAPI.request("/savings-goals/");

        if (goals.length === 0) {

            savingsGoalList.innerHTML = '<p class="hint">No savings goals yet.</p>';
            return;

        }

        savingsGoalList.innerHTML = goals.map(function(goal) {

            return (
                '<div class="list-row" data-id="' + goal.goal_id + '">' +
                    '<div>' +
                        '<strong>' + escapeHTML(goal.name) + '</strong>' +
                        '<br><small class="hint">' +
                            escapeHTML(goal.progress_percent) + '% of ' + escapeHTML(goal.target_amount) +
                            (goal.auto_save_percent > 0
                                ? ' · auto-saving ' + escapeHTML(goal.auto_save_percent) + '% of every Send'
                                : '') +
                        '</small>' +
                    '</div>' +
                    '<div>' +
                        (goal.is_active
                            ? '<button class="deactivate-goal-btn" data-id="' + goal.goal_id + '">Stop</button>'
                            : '<span class="hint">Stopped</span>') +
                    '</div>' +
                '</div>'
            );

        }).join("");

        document.querySelectorAll(".deactivate-goal-btn").forEach(function(button) {

            button.addEventListener("click", async function() {

                try {

                    await CryptoWalletAPI.request(
                        "/savings-goals/" + button.dataset.id + "/deactivate/",
                        { method: "POST" }
                    );

                    loadSavingsGoals();

                } catch (error) {

                    showToast(error.message);

                }

            });

        });

    } catch (error) {

        savingsGoalList.innerHTML = '<p class="hint">Couldn\'t load savings goals.</p>';

    }

}

if (savingsGoalForm) {

    savingsGoalForm.addEventListener("submit", async function(event) {

        event.preventDefault();

        savingsGoalError.textContent = "";

        const walletId = savingsWalletSelect.value;
        const name = document.getElementById("goalName").value.trim();
        const target = document.getElementById("goalTarget").value;
        const autoSave = document.getElementById("goalAutoSavePercent").value || "0";

        if (!walletId || !name || !target) {

            savingsGoalError.textContent = "Please fill in all required fields.";
            return;

        }

        try {

            await CryptoWalletAPI.request("/savings-goals/", {

                method: "POST",
                body: {
                    savings_wallet_id: walletId,
                    name: name,
                    target_amount: target,
                    auto_save_percent: autoSave
                }

            });

            savingsGoalForm.reset();
            showToast("Savings goal created!");
            loadSavingsGoals();

        } catch (error) {

            savingsGoalError.textContent = error.message;

        }

    });

}



/* =====================================================
   PRICE ALERTS
===================================================== */

const priceAlertList = document.getElementById("priceAlertList");
const priceAlertForm = document.getElementById("priceAlertForm");
const alertFromCurrency = document.getElementById("alertFromCurrency");
const alertToCurrency = document.getElementById("alertToCurrency");
const priceAlertError = document.getElementById("priceAlertError");

async function populateCurrencySelects() {

    if (!alertFromCurrency) return;

    try {

        const currencies = await CryptoWalletAPI.request("/currencies/");

        const options = currencies.map(function(c) {
            return '<option value="' + c.currency_name + '">' + c.currency_name + '</option>';
        }).join("");

        alertFromCurrency.innerHTML = options;
        alertToCurrency.innerHTML = options;

    } catch (error) {

        // Silent.

    }

}

async function loadPriceAlerts() {

    if (!priceAlertList) return;

    try {

        const alerts = await CryptoWalletAPI.request("/price-alerts/");

        if (alerts.length === 0) {

            priceAlertList.innerHTML = '<p class="hint">No rate alerts yet.</p>';
            return;

        }

        priceAlertList.innerHTML = alerts.map(function(alert) {

            return (
                '<div class="list-row" data-id="' + alert.alert_id + '">' +
                    '<div>' +
                        '<strong>' + escapeHTML(alert.from_currency) + ' → ' + escapeHTML(alert.to_currency) + '</strong>' +
                        '<br><small class="hint">Alert at ' + escapeHTML(alert.threshold_rate) +
                            (alert.triggered_at ? ' · Triggered' : (alert.is_active ? ' · Watching' : ' · Off')) +
                        '</small>' +
                    '</div>' +
                    '<div>' +
                        '<button class="delete-alert-btn" data-id="' + alert.alert_id + '">Delete</button>' +
                    '</div>' +
                '</div>'
            );

        }).join("");

        document.querySelectorAll(".delete-alert-btn").forEach(function(button) {

            button.addEventListener("click", async function() {

                try {

                    await CryptoWalletAPI.request(
                        "/price-alerts/" + button.dataset.id + "/",
                        { method: "DELETE" }
                    );

                    loadPriceAlerts();

                } catch (error) {

                    showToast(error.message);

                }

            });

        });

    } catch (error) {

        priceAlertList.innerHTML = '<p class="hint">Couldn\'t load rate alerts.</p>';

    }

}

if (priceAlertForm) {

    priceAlertForm.addEventListener("submit", async function(event) {

        event.preventDefault();

        priceAlertError.textContent = "";

        const from = alertFromCurrency.value;
        const to = alertToCurrency.value;
        const threshold = document.getElementById("alertThreshold").value;

        if (from === to) {

            priceAlertError.textContent = "Choose two different currencies.";
            return;

        }

        try {

            await CryptoWalletAPI.request("/price-alerts/", {

                method: "POST",
                body: {
                    from_currency: from,
                    to_currency: to,
                    threshold_rate: threshold
                }

            });

            priceAlertForm.reset();
            showToast("Rate alert created!");
            loadPriceAlerts();

        } catch (error) {

            priceAlertError.textContent = error.message;

        }

    });

}





/* =====================================================
   DEACTIVATE ACCOUNT
===================================================== */

const deactivateAccountButton = document.getElementById("deactivateAccountButton");
const deactivatePassword = document.getElementById("deactivatePassword");
const deactivateError = document.getElementById("deactivateError");

if (deactivateAccountButton) {

    deactivateAccountButton.addEventListener("click", async function() {

        deactivateError.textContent = "";

        const password = deactivatePassword.value;

        if (!password) {

            deactivateError.textContent = "Enter your password to confirm.";
            return;

        }

        const confirmed = window.confirm(
            "This will deactivate your account and log you out. Continue?"
        );

        if (!confirmed) return;

        try {

            await CryptoWalletAPI.request("/profile/deactivate/", {

                method: "POST",
                body: { password: password }

            });

            CryptoWalletAPI.clearTokens();
            sessionStorage.clear();
            window.location.href = "../login.html";

        } catch (error) {

            deactivateError.textContent = error.message;

        }

    });

}



/* =====================================================
   ADDITIONAL INITIAL LOAD (batch 2 features)
===================================================== */

loadAccountType();
populateSavingsWalletSelect();
loadSavingsGoals();
populateCurrencySelects();
loadPriceAlerts();

