/* =====================================================
   CRYPTOWALLET
   CREATE ACCOUNT SYSTEM (Django API version)
===================================================== */


/* =====================================================
   DOM ELEMENTS
===================================================== */

const registerForm =
    document.getElementById("registerForm");

const nameInput =
    document.getElementById("name");

const emailInput =
    document.getElementById("email");

const phoneInput =
    document.getElementById("phone");

const preferredCurrencyInput =
    document.getElementById("preferredCurrency");

const referralCodeInput =
    document.getElementById("referralCode");

const passwordInput =
    document.getElementById("password");

const confirmPasswordInput =
    document.getElementById("confirmPassword");

const termsInput =
    document.getElementById("terms");

const nameError =
    document.getElementById("nameError");

const emailError =
    document.getElementById("emailError");

const phoneError =
    document.getElementById("phoneError");

const passwordError =
    document.getElementById("passwordError");

const confirmPasswordError =
    document.getElementById("confirmPasswordError");

const termsError =
    document.getElementById("termsError");

const toast =
    document.getElementById("toast");



/* =====================================================
   CLEAR ERRORS
===================================================== */

function clearErrors() {

    nameError.textContent = "";
    emailError.textContent = "";
    phoneError.textContent = "";
    passwordError.textContent = "";
    confirmPasswordError.textContent = "";
    termsError.textContent = "";

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
   VALIDATE NAME
===================================================== */

function validateName(name) {

    if (!name) {

        nameError.textContent = "Please enter your full name.";
        return false;

    }

    if (name.length < 2) {

        nameError.textContent =
            "Name must contain at least 2 characters.";
        return false;

    }

    return true;

}



/* =====================================================
   VALIDATE EMAIL
===================================================== */

function validateEmail(email) {

    if (!email) {

        emailError.textContent = "Please enter your email.";
        return false;

    }

    const emailPattern =
        /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (!emailPattern.test(email)) {

        emailError.textContent =
            "Please enter a valid email address.";
        return false;

    }

    return true;

}



/* =====================================================
   VALIDATE PHONE

   This becomes the account's send/receive number, so it
   has to look like a real phone number — other people
   will type it in on the Send page.
===================================================== */

function validatePhone(phone) {

    if (!phone) {

        phoneError.textContent = "Please enter your phone number.";
        return false;

    }

    const phonePattern =
        /^\+?[0-9]{9,15}$/;

    if (!phonePattern.test(phone)) {

        phoneError.textContent =
            "Enter a valid phone number (9-15 digits).";
        return false;

    }

    return true;

}



/* =====================================================
   VALIDATE PASSWORD
===================================================== */

function validatePassword(password) {

    if (!password) {

        passwordError.textContent = "Please create a password.";
        return false;

    }

    if (password.length < 6) {

        passwordError.textContent =
            "Password must contain at least 6 characters.";
        return false;

    }

    return true;

}



/* =====================================================
   VALIDATE CONFIRM PASSWORD
===================================================== */

function validateConfirmPassword(password, confirmPassword) {

    if (!confirmPassword) {

        confirmPasswordError.textContent =
            "Please confirm your password.";
        return false;

    }

    if (password !== confirmPassword) {

        confirmPasswordError.textContent =
            "Passwords do not match.";
        return false;

    }

    return true;

}



/* =====================================================
   VALIDATE TERMS
===================================================== */

function validateTerms() {

    if (!termsInput.checked) {

        termsError.textContent =
            "You must agree to the terms and conditions.";
        return false;

    }

    return true;

}



/* =====================================================
   REGISTER
===================================================== */

registerForm.addEventListener("submit", async function(event) {

    event.preventDefault();

    clearErrors();


    const name =
        nameInput.value.trim();

    const email =
        emailInput.value.trim().toLowerCase();

    const phone =
        phoneInput.value.trim();

    const preferredCurrency =
        preferredCurrencyInput ? preferredCurrencyInput.value : "BDT";

    const password =
        passwordInput.value;

    const confirmPassword =
        confirmPasswordInput.value;


    const validName = validateName(name);
    const validEmail = validateEmail(email);
    const validPhone = validatePhone(phone);
    const validPassword = validatePassword(password);
    const validConfirmPassword =
        validateConfirmPassword(password, confirmPassword);
    const validTerms = validateTerms();

    if (
        !validName ||
        !validEmail ||
        !validPhone ||
        !validPassword ||
        !validConfirmPassword ||
        !validTerms
    ) {

        return;

    }


    try {

        const data =
            await CryptoWalletAPI.request("/auth/register/", {

                method: "POST",
                auth: false,
                body: {
                    name: name,
                    email: email,
                    phone: phone,
                    preferred_currency: preferredCurrency,
                    referral_code: referralCodeInput ? referralCodeInput.value.trim() : "",
                    password: password,
                    confirmPassword: confirmPassword
                }

            });


        CryptoWalletAPI.setTokens(data.access, data.refresh);

        sessionStorage.setItem("userType", "user");
        sessionStorage.setItem("userName", data.user.name);
        sessionStorage.setItem("userEmail", data.user.email);
        sessionStorage.setItem("userPhone", data.user.phone);


        showToast("Account created!");

        setTimeout(function() {

            window.location.href = "index.html";

        }, 700);

    }

    catch (error) {

        /*
            The backend's most common validation failure
            here is "email already registered" — show it
            under the email field. Anything else (weak
            password, etc.) still surfaces via the toast
            so it isn't silently lost.
        */
        if (error.data && error.data.email) {

            emailError.textContent =
                Array.isArray(error.data.email)
                    ? error.data.email[0]
                    : error.data.email;

        }

        else if (error.data && error.data.phone) {

            phoneError.textContent =
                Array.isArray(error.data.phone)
                    ? error.data.phone[0]
                    : error.data.phone;

        }

        else {

            showToast(error.message);

        }

    }

});
