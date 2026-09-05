/* =====================================================
   CRYPTOWALLET
   FORGOT PASSWORD (request a reset link)
===================================================== */

const forgotForm =
    document.getElementById("forgotForm");

const emailInput =
    document.getElementById("email");

const emailError =
    document.getElementById("emailError");

const submitButton =
    document.getElementById("submitButton");

const successPanel =
    document.getElementById("successPanel");

const backToLoginRow =
    document.getElementById("backToLoginRow");

const toast =
    document.getElementById("toast");



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
   SUBMIT
===================================================== */

forgotForm.addEventListener("submit", async function(event) {

    event.preventDefault();

    emailError.textContent = "";

    const email =
        emailInput.value.trim().toLowerCase();

    if (!email) {

        emailError.textContent = "Please enter your email.";
        return;

    }

    submitButton.disabled = true;
    submitButton.textContent = "Sending...";

    try {

        /*
            The backend always returns the same generic
            response whether or not the email is registered
            (so this form can't be used to check which
            emails have accounts) — so we always show the
            same success panel here too, and never reveal
            whether the address matched anything.
        */
        await CryptoWalletAPI.request("/auth/password-reset/request/", {

            method: "POST",
            auth: false,
            body: { email: email }

        });

        forgotForm.style.display = "none";
        backToLoginRow.style.display = "none";
        successPanel.classList.add("show");

    }

    catch (error) {

        showToast(error.message || "Something went wrong. Please try again.");

        submitButton.disabled = false;
        submitButton.textContent = "Send Reset Link";

    }

});
