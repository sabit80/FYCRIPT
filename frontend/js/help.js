/* =====================================================
   CRYPTOWALLET
   HELP & SUPPORT PAGE

   Static FAQ content — guests can view this page too,
   same as the dashboard and the market page.
===================================================== */


/* =====================================================
   CURRENT SESSION (guest allowed)
===================================================== */

const currentUserName =
    sessionStorage.getItem("userName");


/* =====================================================
   DOM
===================================================== */

const faqList =
    document.getElementById("faqList");

const avatar =
    document.getElementById("avatar");

const logout =
    document.getElementById("logout");



/* =====================================================
   FAQ CONTENT
===================================================== */

const FAQS = [

    {
        question: "Is this a real cryptocurrency wallet?",
        answer:
            "No. CryptoWallet is a demo/learning project. Wallets, " +
            "balances and transactions are simulated and stored only " +
            "in your browser — no real funds or blockchain are involved."
    },

    {
        question: "Where is my data stored?",
        answer:
            "Everything (your account, wallets and transaction history) " +
            "is saved in this browser's local storage. Clearing your " +
            "browser data will remove it, and it won't appear on " +
            "another device or browser."
    },

    {
        question: "How do I create a wallet?",
        answer:
            "Go to Wallets from the sidebar, choose a currency, give " +
            "it a name and submit the form. You can fund it afterwards " +
            "from the same page."
    },

    {
        question: "How does Send work?",
        answer:
            "Pick one of your wallets, enter a recipient wallet ID and " +
            "an amount. If the recipient's wallet uses a different " +
            "currency, the amount is converted automatically using the " +
            "rates on the Market page."
    },

    {
        question: "Can I recover my password?",
        answer:
            "There's no email-based recovery in this demo. You can " +
            "change your password any time from Settings while logged in."
    },

    {
        question: "I'm browsing as a Guest — what can I do?",
        answer:
            "Guests can look around the Dashboard, Market and Help " +
            "pages. Creating wallets, sending funds and viewing " +
            "personal reports require a real account."
    }

];



/* =====================================================
   RENDER FAQ LIST
===================================================== */

function renderFaqList() {

    if (!faqList) {

        return;

    }


    faqList.innerHTML =
        FAQS.map(function(item, index) {

            return (
                "<div class=\"faq-item\" data-index=\"" + index + "\">" +
                    "<button type=\"button\" class=\"faq-question\">" +
                        "<span>" + item.question + "</span>" +
                        "<span class=\"arrow\">▾</span>" +
                    "</button>" +
                    "<div class=\"faq-answer\">" + item.answer + "</div>" +
                "</div>"
            );

        }).join("");


    faqList.querySelectorAll(".faq-question").forEach(function(button) {

        button.addEventListener("click", function() {

            button.parentElement.classList.toggle("open");

        });

    });

}


renderFaqList();



/* =====================================================
   AVATAR
===================================================== */

if (avatar) {

    avatar.textContent =
        currentUserName
            ? currentUserName.charAt(0).toUpperCase()
            : "G";

}



/* =====================================================
   LOGOUT
===================================================== */

if (logout) {

    logout.addEventListener("click", function() {

        sessionStorage.clear();

        window.location.href = "../login.html";

    });

}
