/* =====================================================
   CRYPTOWALLET — LIGHTWEIGHT I18N (EN / BN TOGGLE)

   A deliberately small approach: every translatable element in
   the HTML gets a `data-i18n="key"` attribute (for its text
   content) or `data-i18n-placeholder="key"` (for input
   placeholders). This script swaps text based on the saved
   language preference. Not every string on every page has been
   tagged yet — this wires up the mechanism plus the Settings
   page's own labels; extending coverage to every page is just a
   matter of adding more data-i18n attributes and DICTIONARY
   entries, following the same pattern.

   Preference is stored in localStorage (a UI preference, not
   account data — deliberately NOT sent to the backend) so it
   persists across sessions on this device.
===================================================== */

const CryptoWalletI18N = (function() {

    const STORAGE_KEY = "cryptowallet_language";

    const DICTIONARY = {

        en: {
            settings_title: "Settings",
            two_factor_title: "Two-Factor Authentication (2FA)",
            scheduled_payments_title: "Scheduled Payments",
            account_type_title: "Account Type",
            payment_links_title: "Payment Links",
            savings_goals_title: "Savings Goals",
            rate_alerts_title: "Rate Alerts",
            biometric_title: "Biometric / Passkey Login",
            language_title: "Language",
            deactivate_title: "Deactivate Account",
            save_button: "Save",
            create_button: "Create"
        },

        bn: {
            settings_title: "সেটিংস",
            two_factor_title: "টু-ফ্যাক্টর অথেনটিকেশন (2FA)",
            scheduled_payments_title: "শিডিউলড পেমেন্ট",
            account_type_title: "অ্যাকাউন্ট টাইপ",
            payment_links_title: "পেমেন্ট লিংক",
            savings_goals_title: "সেভিংস গোল",
            rate_alerts_title: "রেট অ্যালার্ট",
            biometric_title: "বায়োমেট্রিক / পাসকি লগইন",
            language_title: "ভাষা",
            deactivate_title: "অ্যাকাউন্ট নিষ্ক্রিয় করুন",
            save_button: "সংরক্ষণ করুন",
            create_button: "তৈরি করুন"
        }

    };

    function getLanguage() {

        return window.localStorage.getItem(STORAGE_KEY) || "en";

    }

    function setLanguage(lang) {

        window.localStorage.setItem(STORAGE_KEY, lang);
        applyToPage();

    }

    function applyToPage() {

        const lang = getLanguage();
        const dict = DICTIONARY[lang] || DICTIONARY.en;

        document.querySelectorAll("[data-i18n]").forEach(function(el) {

            const key = el.getAttribute("data-i18n");
            if (dict[key]) el.textContent = dict[key];

        });

        document.querySelectorAll("[data-i18n-placeholder]").forEach(function(el) {

            const key = el.getAttribute("data-i18n-placeholder");
            if (dict[key]) el.setAttribute("placeholder", dict[key]);

        });

        const selector = document.getElementById("languageSelect");
        if (selector) selector.value = lang;

    }

    return {
        getLanguage: getLanguage,
        setLanguage: setLanguage,
        applyToPage: applyToPage
    };

})();


document.addEventListener("DOMContentLoaded", function() {

    CryptoWalletI18N.applyToPage();

    const selector = document.getElementById("languageSelect");

    if (selector) {

        selector.addEventListener("change", function() {

            CryptoWalletI18N.setLanguage(selector.value);

        });

    }

});


window.CryptoWalletI18N = CryptoWalletI18N;
