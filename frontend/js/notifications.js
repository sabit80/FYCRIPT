/* =====================================================
   CRYPTOWALLET — NOTIFICATION BELL (WebSocket + fallback)

   Injects a bell icon with an unread badge into the header's
   .avatar area on any page that includes this script, opens a
   WebSocket to /ws/notifications/ for instant push, and falls
   back to the existing GET /api/notifications/ list so the
   dropdown still works even if no ASGI server (daphne/uvicorn)
   is running — plain `manage.py runserver` only serves HTTP, so
   the socket simply won't connect in that case, and this script
   degrades to "load on open" instead of instant push.
===================================================== */

(function() {

    if (!window.CryptoWalletAPI || !CryptoWalletAPI.isLoggedIn()) {

        return;

    }

    const avatarEl = document.getElementById("avatar");

    if (!avatarEl || !avatarEl.parentElement) {

        return;

    }


    /* ---------- BUILD THE BELL + DROPDOWN ---------- */

    const wrapper = document.createElement("div");
    wrapper.style.cssText = "position:relative;display:inline-flex;align-items:center;gap:14px;";

    const bell = document.createElement("button");
    bell.type = "button";
    bell.setAttribute("aria-label", "Notifications");
    bell.style.cssText =
        "position:relative;background:none;border:none;font-size:20px;cursor:pointer;color:inherit;";
    bell.innerHTML = "🔔<span id=\"cwNotifBadge\" style=\"display:none;position:absolute;top:-4px;right:-6px;" +
        "background:#d9484f;color:#fff;font-size:10px;border-radius:9px;padding:1px 5px;\">0</span>";

    const dropdown = document.createElement("div");
    dropdown.id = "cwNotifDropdown";
    dropdown.style.cssText =
        "display:none;position:absolute;top:36px;right:0;width:300px;max-height:360px;overflow-y:auto;" +
        "background:var(--surface,#181c2b);border:1px solid var(--border,#333);border-radius:10px;" +
        "box-shadow:0 8px 30px rgba(0,0,0,.3);z-index:1000;padding:8px;";
    dropdown.innerHTML = "<p style='padding:8px;opacity:.7;font-size:13px;'>Loading…</p>";

    wrapper.appendChild(bell);
    wrapper.appendChild(dropdown);

    avatarEl.parentElement.insertBefore(wrapper, avatarEl);


    /* ---------- STATE ---------- */

    let unreadCount = 0;

    function setBadge(count) {

        unreadCount = count;
        const badge = document.getElementById("cwNotifBadge");

        if (!badge) return;

        if (count > 0) {

            badge.style.display = "inline-block";
            badge.textContent = count > 9 ? "9+" : String(count);

        } else {

            badge.style.display = "none";

        }

    }

    function escapeHTML(value) {

        const div = document.createElement("div");
        div.textContent = value == null ? "" : String(value);
        return div.innerHTML;

    }

    function renderList(items) {

        if (items.length === 0) {

            dropdown.innerHTML = "<p style='padding:8px;opacity:.7;font-size:13px;'>No notifications yet.</p>";
            return;

        }

        dropdown.innerHTML = items.map(function(n) {

            const timestamp = n.timestamp || n.created_at;

            return (
                "<div style='padding:8px;border-bottom:1px solid var(--border,#333);font-size:13px;" +
                (n.read_status || n.is_read ? "opacity:.6;" : "") + "'>" +
                    "<div>" + escapeHTML(n.message) + "</div>" +
                    "<div style='opacity:.6;font-size:11px;margin-top:2px;'>" +
                        new Date(timestamp).toLocaleString() +
                    "</div>" +
                "</div>"
            );

        }).join("");

    }


    /* ---------- LOAD VIA REST (always runs; source of truth) ---------- */

    async function loadNotifications() {

        try {

            const items = await CryptoWalletAPI.request("/notifications/");

            renderList(items);
            setBadge(items.filter(function(n) {
                return !(n.read_status || n.is_read);
            }).length);

        } catch (error) {

            dropdown.innerHTML = "<p style='padding:8px;opacity:.7;font-size:13px;'>Couldn't load notifications.</p>";

        }

    }


    bell.addEventListener("click", function() {

        const isOpen = dropdown.style.display === "block";
        dropdown.style.display = isOpen ? "none" : "block";

        if (!isOpen) {

            loadNotifications();

        }

    });

    document.addEventListener("click", function(event) {

        if (!wrapper.contains(event.target)) {

            dropdown.style.display = "none";

        }

    });


    /* ---------- WEBSOCKET (instant push, best-effort) ---------- */

    function connectWebSocket() {

        const token = CryptoWalletAPI.getAccessToken();

        if (!token) return;

        // Derive ws(s)://host from the REST API_BASE_URL rather than
        // hardcoding — e.g. "http://127.0.0.1:8000/api" becomes
        // "ws://127.0.0.1:8000/ws/notifications/".
        const httpBase = CryptoWalletAPI.apiBaseUrl.replace(/\/api\/?$/, "");
        const wsBase = httpBase.replace(/^http/, "ws");

        let socket;

        try {

            socket = new WebSocket(wsBase + "/ws/notifications/?token=" + encodeURIComponent(token));

        } catch (error) {

            return; // WebSocket unsupported/blocked — REST polling on bell-click still works.

        }

        socket.addEventListener("message", function(event) {

            try {

                const payload = JSON.parse(event.data);
                setBadge(unreadCount + 1);

                if (dropdown.style.display === "block") {

                    loadNotifications();

                }

            } catch (error) {

                // Ignore malformed payloads.

            }

        });

        socket.addEventListener("close", function() {

            // No reconnect loop here to keep this lightweight — the
            // bell still works via REST on every click regardless of
            // socket state, so a dropped connection just means the
            // badge stops updating instantly until next page load.

        });

    }


    /* ---------- INITIAL LOAD ---------- */

    loadNotifications();
    connectWebSocket();

})();
