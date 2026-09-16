/* =====================================================
   CRYPTOWALLET
   API CLIENT

   Every page loads this file first (before its own
   page-specific script) and uses window.CryptoWalletAPI
   instead of touching localStorage/sessionStorage for
   wallets, transactions, users, etc.

   Session flags (userType / userName) are still kept in
   sessionStorage, same as before, purely for quick UI
   checks (avatar initial, guest banner) — the source of
   truth for actual data is now the Django backend.
===================================================== */

const API_BASE_URL =
    "http://127.0.0.1:8000/api";


/* =====================================================
   TOKEN STORAGE

   Access/refresh tokens live in sessionStorage so separate
   browser tabs cannot overwrite one another's authenticated
   account. sessionStorage survives a page refresh in the
   same tab while keeping account A from using account B's token.
===================================================== */

const ACCESS_TOKEN_KEY = "cryptoWalletAccessToken";
const REFRESH_TOKEN_KEY = "cryptoWalletRefreshToken";


function setTokens(access, refresh) {

    sessionStorage.setItem(ACCESS_TOKEN_KEY, access);

    if (refresh) {
        sessionStorage.setItem(REFRESH_TOKEN_KEY, refresh);
    }

}


function getAccessToken() {
    return sessionStorage.getItem(ACCESS_TOKEN_KEY);
}


function getRefreshToken() {
    return sessionStorage.getItem(REFRESH_TOKEN_KEY);
}


function clearTokens() {

    sessionStorage.removeItem(ACCESS_TOKEN_KEY);
    sessionStorage.removeItem(REFRESH_TOKEN_KEY);
    // Remove tokens written by older versions so they cannot be reused.
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);

}


function isLoggedIn() {
    return Boolean(getAccessToken());
}


function setAdministrativeSession(user) {
    sessionStorage.setItem(
        "isAdministrative",
        user && (user.is_staff || user.is_superuser) ? "true" : "false"
    );
}


function isAdministrativeSession() {
    return sessionStorage.getItem("isAdministrative") === "true";
}

function requireAdmin(loginPath) {
    if (!isAdministrativeSession()) {
        window.location.replace(loginPath || "../login.html");
        return false;
    }

    return true;
}


function enforceAdministrativeNavigation() {
    const currentPath = window.location.pathname.toLowerCase();
    const adminPage = currentPath.endsWith("/pages/admin.html");
    const settingsPage = currentPath.endsWith("/pages/settings.html");
    const helpPage = currentPath.endsWith("/pages/help.html");
    const authenticationPage = currentPath.endsWith("/login.html") ||
        currentPath.endsWith("/create-account.html");
    const isAdmin = isAdministrativeSession();

    document.querySelectorAll("a[href]").forEach(function(link) {
        const href = (link.getAttribute("href") || "").toLowerCase();
        const adminLink = href.endsWith("admin.html");

        if (adminLink && !isAdmin) {
            link.remove();
        }

        if (isAdmin && !adminLink && !href.endsWith("settings.html") &&
            !href.endsWith("help.html")) {
            link.remove();
        }
    });

    if (!isAdmin && adminPage) {
        window.location.replace("../index.html");
        return;
    }

    if (isAdmin && !adminPage && !settingsPage && !helpPage &&
        !authenticationPage) {
        window.location.replace(
            currentPath.endsWith("/index.html")
                ? "pages/admin.html"
                : "admin.html"
        );
    }
}


if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enforceAdministrativeNavigation);
} else {
    enforceAdministrativeNavigation();
}



/* =====================================================
   REFRESH ACCESS TOKEN

   Called automatically once by apiRequest() whenever a
   request comes back 401 (expired access token).
===================================================== */

async function refreshAccessToken() {

    const refresh =
        getRefreshToken();

    if (!refresh) {

        return false;

    }

    const response =
        await fetch(API_BASE_URL + "/auth/token/refresh/", {

            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh: refresh })

        });

    if (!response.ok) {

        return false;

    }

    const data =
        await response.json();

    setTokens(data.access, null);

    return true;

}



/* =====================================================
   CORE REQUEST HELPER

   apiRequest("/wallets/", { method: "POST", body: {...} })

   - Adds the Authorization header automatically unless
     { auth: false } is passed (register/login/rates).
   - Parses JSON responses (and tolerates empty bodies,
     e.g. DELETE responses).
   - On a 401, retries once after refreshing the token.
   - Throws an Error whose .data holds the parsed error
     body from DRF, e.g. { email: ["..."] }, so pages can
     show field-specific messages.
===================================================== */

async function apiRequest(path, options) {

    options = options || {};

    const useAuth =
        options.auth !== false;

    const headers = {
        "Content-Type": "application/json"
    };

    if (useAuth) {

        const token =
            getAccessToken();

        if (token) {

            headers.Authorization =
                "Bearer " + token;

        }

    }


    const response =
        await fetch(API_BASE_URL + path, {

            method: options.method || "GET",
            headers: headers,
            body: options.body
                ? JSON.stringify(options.body)
                : undefined

        });


    if (
        response.status === 401 &&
        useAuth &&
        !options._retried
    ) {

        const refreshed =
            await refreshAccessToken();

        if (refreshed) {

            return apiRequest(
                path,
                Object.assign({}, options, { _retried: true })
            );

        }

        clearTokens();
        sessionStorage.clear();

        throw new Error("Session expired. Please log in again.");

    }


    let data = null;

    const text =
        await response.text();

    if (text) {

        try {
            data = JSON.parse(text);
        }
        catch (error) {
            data = null;
        }

    }


    if (!response.ok) {

        const message =
            (data && (data.detail || firstErrorMessage(data))) ||
            "Something went wrong. Please try again.";

        const error =
            new Error(message);

        error.data = data;
        error.status = response.status;

        throw error;

    }


    return data;

}


/*
    DRF validation errors usually look like:
    { "email": ["This field is required."] }
    Pull out the first message so callers have something
    readable without needing to know the field name.
*/
function firstErrorMessage(data) {

    if (typeof data !== "object" || data === null) {

        return null;

    }

    const firstKey =
        Object.keys(data)[0];

    if (!firstKey) {

        return null;

    }

    const value =
        data[firstKey];

    return Array.isArray(value) ? value[0] : String(value);

}



/* =====================================================
   LOGIN GUARD HELPERS

   loginPath is relative to whichever page calls this —
   pages/*.html pass "../login.html", index.html passes
   "login.html".
===================================================== */

function requireLogin(loginPath) {

    if (!isLoggedIn()) {

        window.location.href = loginPath;

    }

}


function requireSession(loginPath) {

    const userType =
        sessionStorage.getItem("userType");

    if (
        !isLoggedIn() &&
        userType !== "guest"
    ) {

        window.location.href = loginPath;

    }

}



/* =====================================================
   PUBLIC API
===================================================== */

window.CryptoWalletAPI = {

    request: apiRequest,
    setTokens: setTokens,
    setAdministrativeSession: setAdministrativeSession,
    isAdministrativeSession: isAdministrativeSession,
    requireAdmin: requireAdmin,
    clearTokens: clearTokens,
    isLoggedIn: isLoggedIn,
    requireLogin: requireLogin,
    requireSession: requireSession,
    getAccessToken: getAccessToken,
    apiBaseUrl: API_BASE_URL

};
