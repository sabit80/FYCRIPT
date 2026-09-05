
//Login · JS
/* =====================================================
   CRYPTOWALLET
   LOGIN SYSTEM (Django API version)
===================================================== */
 
 
/* =====================================================
   POST-LOGIN REDIRECT
 
   Staff/admin accounts (is_staff on the User model — set
   automatically for anyone created via `createsuperuser`,
   or manually via Django admin) land on the admin dashboard
   instead of the normal user dashboard. Everyone else goes
   to index.html as before.
===================================================== */
 
function redirectAfterLogin(user) {
 
    if (user && user.is_staff) {
 
        window.location.href = "pages/admin.html";
 
    } else {
 
        window.location.href = "index.html";
 
    }
 
}
 
 
/* =====================================================
   DOM ELEMENTS
===================================================== */
 
const loginForm =
    document.getElementById("loginForm");
 
const emailInput =
    document.getElementById("email");
 
const passwordInput =
    document.getElementById("password");
 
const emailError =
    document.getElementById("emailError");
 
const passwordError =
    document.getElementById("passwordError");
 
const guestButton =
    document.getElementById("guestButton");
 
const toast =
    document.getElementById("toast");
 
 
/* =====================================================
   2FA CHALLENGE MODAL (injected once, shown when the
   login endpoint returns { two_factor_required: true })
===================================================== */
 
let pendingLoginToken = null;
 
function build2FAModal() {
 
    const overlay = document.createElement("div");
    overlay.id = "twoFAOverlay";
    overlay.style.cssText =
        "position:fixed;inset:0;background:rgba(0,0,0,.55);" +
        "display:none;align-items:center;justify-content:center;z-index:9999;";
 
    overlay.innerHTML =
        '<div style="background:var(--card-bg,#181c2b);color:var(--text,#fff);' +
        'padding:28px;border-radius:14px;max-width:340px;width:90%;text-align:center;' +
        'box-shadow:0 10px 40px rgba(0,0,0,.4);">' +
        '<h3 style="margin:0 0 8px;">Two-Factor Verification</h3>' +
        '<p style="opacity:.8;font-size:14px;margin:0 0 16px;">' +
        'Enter the 6-digit code from your authenticator app, or one of your recovery codes.</p>' +
        '<input id="twoFACodeInput" inputmode="numeric" maxlength="10" placeholder="123456" ' +
        'style="width:100%;padding:12px;border-radius:8px;border:1px solid #444;' +
        'background:#0e1220;color:#fff;text-align:center;font-size:20px;letter-spacing:4px;margin-bottom:10px;">' +
        '<p id="twoFAError" style="color:#ff6b6b;font-size:13px;min-height:18px;margin:0 0 12px;"></p>' +
        '<button id="twoFASubmit" style="width:100%;padding:12px;border:none;border-radius:8px;' +
        'background:#5b6cff;color:#fff;font-weight:600;cursor:pointer;">Verify</button>' +
        '<button id="twoFACancel" style="width:100%;padding:10px;border:none;background:transparent;' +
        'color:#aaa;margin-top:8px;cursor:pointer;">Cancel</button>' +
        '</div>';
 
    document.body.appendChild(overlay);
 
    document.getElementById("twoFACancel").addEventListener("click", function() {
        overlay.style.display = "none";
        pendingLoginToken = null;
    });
 
    document.getElementById("twoFASubmit").addEventListener("click", submit2FACode);
    document.getElementById("twoFACodeInput").addEventListener("keydown", function(e) {
        if (e.key === "Enter") submit2FACode();
    });
 
    return overlay;
}
 
const twoFAOverlay = build2FAModal();
 
function show2FAModal(loginToken) {
    pendingLoginToken = loginToken;
    document.getElementById("twoFAError").textContent = "";
    document.getElementById("twoFACodeInput").value = "";
    twoFAOverlay.style.display = "flex";
    document.getElementById("twoFACodeInput").focus();
}
 
async function submit2FACode() {
 
    const code = document.getElementById("twoFACodeInput").value.trim();
    const errorEl = document.getElementById("twoFAError");
 
    if (!code) {
        errorEl.textContent = "Enter a code first.";
        return;
    }
 
    try {
 
        const data = await CryptoWalletAPI.request("/auth/login/verify-2fa/", {
            method: "POST",
            auth: false,
            body: { login_token: pendingLoginToken, code: code }
        });
 
        CryptoWalletAPI.setTokens(data.access, data.refresh);
 
        sessionStorage.setItem("userType", "user");
        sessionStorage.setItem("userName", data.user.name);
        sessionStorage.setItem("userEmail", data.user.email);
        sessionStorage.setItem("userPhone", data.user.phone);
 
        twoFAOverlay.style.display = "none";
        showToast("Login successful!");
 
        setTimeout(function() {
            redirectAfterLogin(data.user);
        }, 700);
 
    }
    catch (error) {
        errorEl.textContent = error.message;
    }
 
}
 
 
 
/* =====================================================
   CLEAR ERRORS
===================================================== */
 
function clearErrors() {
 
    emailError.textContent = "";
    passwordError.textContent = "";
 
}
 
 
 
/* =====================================================
   SHOW TOAST
===================================================== */
 
function showToast(message) {
 
    toast.textContent = message;
    toast.classList.add("show");
 
    setTimeout(function() {
 
        toast.classList.remove("show");
 
    }, 2500);
 
}
 
 
 
/* =====================================================
   LOGIN
===================================================== */
 
loginForm.addEventListener("submit", async function(event) {
 
    event.preventDefault();
 
    clearErrors();
 
 
    const email =
        emailInput.value.trim().toLowerCase();
 
    const password =
        passwordInput.value;
 
 
    if (!email) {
 
        emailError.textContent = "Please enter your email.";
        return;
 
    }
 
    if (!password) {
 
        passwordError.textContent = "Please enter your password.";
        return;
 
    }
 
 
    try {
 
        const data =
            await CryptoWalletAPI.request("/auth/login/", {
 
                method: "POST",
                auth: false,
                body: { email: email, password: password }
 
            });
 
 
        if (data.two_factor_required) {
 
            show2FAModal(data.login_token);
            return;
 
        }
 
 
        CryptoWalletAPI.setTokens(data.access, data.refresh);
 
        sessionStorage.setItem("userType", "user");
        sessionStorage.setItem("userName", data.user.name);
        sessionStorage.setItem("userEmail", data.user.email);
        sessionStorage.setItem("userPhone", data.user.phone);
 
 
        showToast("Login successful!");
 
        setTimeout(function() {
 
            redirectAfterLogin(data.user);
 
        }, 700);
 
    }
 
    catch (error) {
 
        /*
            The backend doesn't distinguish "no such
            email" from "wrong password" (on purpose,
            so people can't use this form to find out
            which emails are registered) — show the
            message under the password field.
        */
        passwordError.textContent =
            error.message;
 
    }
 
});
 
 
 
/* =====================================================
   GUEST LOGIN
 
   Guests never hit the backend — same as before, this
   is purely a local sessionStorage flag that the other
   pages check.
===================================================== */
 
guestButton.addEventListener("click", function() {
 
    CryptoWalletAPI.clearTokens();
 
    sessionStorage.setItem("userType", "guest");
    sessionStorage.removeItem("userEmail");
    sessionStorage.removeItem("userName");
 
 
    showToast("Continuing as Guest...");
 
    setTimeout(function() {
 
        window.location.href = "index.html";
 
    }, 700);
 
});
 
 
 
/* =====================================================
   BIOMETRIC / PASSKEY LOGIN
 
   Requires the email field to already be filled in (WebAuthn
   needs to know which account's registered credentials to
   challenge against) — the password field is not used here.
===================================================== */
 
const passkeyLoginButton = document.getElementById("passkeyLoginButton");
const passkeyError = document.getElementById("passkeyError");
 
if (passkeyLoginButton) {
 
    passkeyLoginButton.addEventListener("click", async function() {
 
        passkeyError.textContent = "";
 
        const email = emailInput.value.trim();
 
        if (!email) {
 
            passkeyError.textContent = "Enter your email first, then tap this button.";
            return;
 
        }
 
        try {
 
            const data = await CryptoWalletWebAuthn.loginWithPasskey(email);
 
            CryptoWalletAPI.setTokens(data.access, data.refresh);
 
            sessionStorage.setItem("userType", "user");
            sessionStorage.setItem("userName", data.user.name);
            sessionStorage.setItem("userEmail", data.user.email);
            sessionStorage.setItem("userPhone", data.user.phone);
 
            showToast("Login successful!");
 
            setTimeout(function() {
                redirectAfterLogin(data.user);
            }, 700);
 
        } catch (error) {
 
            passkeyError.textContent = error.message;
 
        }
 
    });
 
}
 



