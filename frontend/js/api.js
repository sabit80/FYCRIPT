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

   Access/refresh tokens live in localStorage (not
   sessionStorage) so a login survives a page refresh in
   the same browser, same as most real apps.
===================================================== */

const ACCESS_TOKEN_KEY = "cryptoWalletAccessToken";
const REFRESH_TOKEN_KEY = "cryptoWalletRefreshToken";


function setTokens(access, refresh) {

    localStorage.setItem(ACCESS_TOKEN_KEY, access);

    if (refresh) {
        localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
    }

}


function getAccessToken() {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
}


function getRefreshToken() {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
}


function clearTokens() {

    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);

}


function isLoggedIn() {
    return Boolean(getAccessToken());
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
    clearTokens: clearTokens,
    isLoggedIn: isLoggedIn,
    requireLogin: requireLogin,
    requireSession: requireSession,
    getAccessToken: getAccessToken,
    apiBaseUrl: API_BASE_URL

};
