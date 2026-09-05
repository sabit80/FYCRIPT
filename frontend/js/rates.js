/* =====================================================
   CRYPTOWALLET
   SHARED EXCHANGE RATES (preview only)

   The backend's ExchangeRate table (CURRENCY "converts"
   CURRENCY in the ER diagram) is the real source of truth
   for every send/exchange — this file only powers the
   live on-screen preview so the numbers feel instant while
   typing. EXCHANGE_RATES stays "1 USD = X <currency>",
   same shape as before, so send.js / exchange.js /
   dashboard.js don't need to change how they read it —
   it's just populated from the API now instead of hardcoded.
===================================================== */

const EXCHANGE_RATES = {

    USD: 1,
    BDT: 120,
    EUR: 0.92,
    GBP: 0.79,
    BTC: 0.000015,
    ETH: 0.00032,
    USDT: 1

};


async function loadLiveRates() {

    try {

        const rows =
            await CryptoWalletAPI.request("/rates/", { auth: false });

        rows.forEach(function(row) {

            if (row.from_curr === "USD") {

                EXCHANGE_RATES[row.to_curr] = Number(row.rate);

            }

        });

        EXCHANGE_RATES.USD = 1;

        document.dispatchEvent(new CustomEvent("rates:loaded"));

    }

    catch (error) {

        // Keep the static fallback above — the backend still
        // validates and applies the real rate on every request.

    }

}


loadLiveRates();
