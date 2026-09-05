(function () {
    "use strict";

    const THEME_KEY = "cryptoWalletTheme";

    function applyTheme(theme) {
        if (theme === "dark") {
            document.documentElement.setAttribute("data-theme", "dark");
        } else {
            document.documentElement.removeAttribute("data-theme");
        }

        updateToggleButtons(theme);
    }

    function updateToggleButtons(theme) {
        const buttons = document.querySelectorAll("[data-theme-toggle]");

        buttons.forEach(function (button) {
            button.setAttribute(
                "aria-pressed",
                theme === "dark" ? "true" : "false"
            );
        });
    }

    function getTheme() {
        return localStorage.getItem(THEME_KEY) || "light";
    }

    function toggleTheme() {
        const currentTheme = getTheme();
        const newTheme = currentTheme === "dark" ? "light" : "dark";

        localStorage.setItem(THEME_KEY, newTheme);
        applyTheme(newTheme);
    }

    function initTheme() {
        const savedTheme = getTheme();

        applyTheme(savedTheme);

        const buttons = document.querySelectorAll("[data-theme-toggle]");

        buttons.forEach(function (button) {
            button.addEventListener("click", toggleTheme);
        });
    }

    // Apply theme as soon as the page loads
    initTheme();

    // Make functions available if needed elsewhere
    window.CryptoWalletTheme = {
        get: getTheme,
        toggle: toggleTheme,
        apply: applyTheme
    };
})();