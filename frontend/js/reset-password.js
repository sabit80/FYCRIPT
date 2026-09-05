/* =====================================================
   CRYPTOWALLET
   RESET PASSWORD (confirm step, reached via the emailed
   link: reset-password.html?uid=...&token=...)
===================================================== */

const resetForm =
    document.getElementById("resetForm");

const newPasswordInput =
    document.getElementById("newPassword");

const confirmPasswordInput =
    document.getElementById("confirmPassword");

const newPasswordError =
    document.getElementById("newPasswordError");

const confirmPasswordError =
    document.getElementById("confirmPasswordError");

const submitButton =
    document.getElementById("submitButton");

const invalidLinkPanel =
    document.getElementById("invalidLinkPanel");

const successPanel =
    document.getElementById("successPanel");

const backToLoginRow =
    document.getElementById("backToLoginRow");

const toast =
    document.getElementById("toast");



/* =====================================================
   READ uid / token FROM THE URL
===================================================== */

const params =
    new URLSearchParams(window.location.search);

const uid =
    params.get("uid");

const token =
    params.get("token");

const linkIsValid =
    Boolean(uid && token);

if (!linkIsValid) {

    resetForm.style.display = "none";
    backToLoginRow.style.display = "none";
    invalidLinkPanel.classList.add("show");

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
   CLEAR ERRORS
===================================================== */

function clearErrors() {

    newPasswordError.textContent = "";
    confirmPasswordError.textContent = "";

}



/* =====================================================
   SUBMIT
===================================================== */

resetForm.addEventListener("submit", async function(event) {

    event.preventDefault();

    if (!linkIsValid) return;

    clearErrors();

    const newPassword =
        newPasswordInput.value;

    const confirmPassword =
        confirmPasswordInput.value;

    if (!newPassword) {

        newPasswordError.textContent = "Please enter a new password.";
        return;

    }

    if (newPassword.length < 8) {

        newPasswordError.textContent = "Password must be at least 8 characters.";
        return;

    }

    if (newPassword !== confirmPassword) {

        confirmPasswordError.textContent = "Passwords do not match.";
        return;

    }

    submitButton.disabled = true;
    submitButton.textContent = "Resetting...";

    try {

        await CryptoWalletAPI.request("/auth/password-reset/confirm/", {

            method: "POST",
            auth: false,
            body: {
                uid: uid,
                token: token,
                newPassword: newPassword
            }

        });

        resetForm.style.display = "none";
        backToLoginRow.style.display = "none";
        successPanel.classList.add("show");

    }

    catch (error) {

        /*
            Most common cases here: the link has expired or
            was already used ("detail" from the backend), or
            the new password failed Django's strength
            validators (a "newPassword" field error) — either
            way error.message already resolves to the right
            text (see api.js's firstErrorMessage()).
        */
        newPasswordError.textContent = error.message;

        submitButton.disabled = false;
        submitButton.textContent = "Reset Password";

    }

});
