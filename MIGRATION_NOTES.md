# ORM → Raw SQL migration status

An earlier version of this file falsely claimed the conversion and the
forgot-password feature were both "done and tested" when neither was
true. This version reflects what has actually been checked: a real,
migrated MySQL/MariaDB schema, real HTTP requests against a running
server, and the project's own test suite — not just a read-through.

## Status: complete

Every business-logic database read/write in this app now goes through
the raw-SQL layer in `wallet/db.py` instead of Django's ORM query
builder or instance `.save()`/`.delete()`. Verify with:

```bash
grep -rn "\.objects\.\|\.save(\|\.delete(" wallet/*.py wallet/management/commands/*.py
```

Every hit that remains is inside a comment or docstring (documenting
what the code used to do, for anyone reading it later) — none are
executable ORM calls. The one exception is `wallet/tests.py`, which
still uses `User.objects.create_superuser(...)` to set up a test
fixture; that's test-only code, not application logic, and was left
alone deliberately so the test suite stays a reliable regression check
against everything else.

### What changed, and how

- **`wallet/db.py`** is the project's "own ORM" (explicitly allowed by
  the assignment): `insert`, `update_by_pk`, `update_where`,
  `delete_by_pk`, `get_row`, `find_one`, `find_all`, `count_where`,
  `exists_where`, `upsert`, `get_or_create_simple`, plus `hydrate()` /
  `hydrate_all()` to turn raw dict rows into (unsaved) Django model
  instances — so DRF's `ModelSerializer`s keep working unchanged, with
  zero ORM queries firing during serialization. Every function uses
  `%s` placeholders with parameters passed separately — never
  string-formats a value into SQL.
- **`wallet/models.py`** — model *classes* are kept only for schema/
  migrations (`manage.py migrate` still needs them) and because
  SimpleJWT needs a model instance for `request.user`. `Wallet.save()`'s
  single-default-wallet logic, `User.kyc_tier()`, and
  `GroupPayment.refresh_status()` were rewritten to query raw SQL
  directly instead of `.filter()/.get()`/relation descriptors.
- **`wallet/serializers.py`** — all `validate_*` methods and
  `RegisterSerializer.create()` are raw SQL. `GroupPaymentSerializer`'s
  `participants` field was changed to a `SerializerMethodField` reading
  from a private `_participants` attribute — the real `participants`
  reverse-FK field is a data descriptor that raises `TypeError` on
  direct assignment ("Direct assignment to the reverse side of a
  related set is prohibited"), which a live test of group-payment
  creation actually hit and which is fixed now.
- **`wallet/views.py`** — every view converted: auth (register, login,
  2FA, change/forgot/reset password, transaction PIN), wallets, bank
  accounts, KYC, send, exchange, transactions (list/CSV/PDF export),
  dashboard, sessions, notifications, admin (KYC queue/approve/reject,
  analytics, flagged users), money requests, scheduled payments, group
  payments, savings goals, price alerts, payment links, account type/
  deactivation.
- **`wallet/jwt_auth_middleware.py`** — WebSocket JWT auth now looks up
  the user via `db.get_row()` instead of `User.objects.get()`.
- **Management commands** (`seed_data`, `sync_live_rates`,
  `check_price_alerts`, `run_scheduled_payments`) — all converted and
  functionally re-run against a live database (seed idempotency
  checked by running twice; a real price alert was created and fired;
  a real scheduled payment was created due-in-the-past and executed,
  confirmed by checking wallet balances before/after).
- **The forgot-password bug is fixed**: the reset link now uses a
  configurable `FRONTEND_URL` setting instead of a hardcoded
  `127.0.0.1:5500`. Verified end-to-end: register → request reset →
  pull the real link from the console email backend → reset → old
  password rejected (401) → new password accepted.
- The real-time notification WebSocket push (previously an ORM
  `post_save` signal, which only fires on `.objects.create()`/
  `.save()`) now fires explicitly from every raw-SQL notification
  insert — see `create_notification()` /
  `_push_notification_over_websocket()` in `views.py`. The old signal
  in `signals.py` is left connected as a harmless no-op safety net in
  case anything outside this codebase still calls
  `Notification.objects.create()` directly (e.g. Django admin).

### What was actually run, not just read

- `python manage.py check` — clean, no errors.
- `python manage.py test wallet` — all 22 existing tests pass,
  unchanged, against every converted view.
- Live HTTP smoke tests against a running `manage.py runserver` with a
  real MariaDB database for: register, login, 2FA setup/verify,
  forgot/reset password (full round trip), wallets (create/list/fund/
  freeze/set-default), bank accounts, KYC, send (cross-user + same-
  user shift), exchange (via the `sp_exchange_funds` stored
  procedure), transactions list/CSV/PDF export, dashboard summary,
  sessions, notifications, group payments (create → participant pays
  → status flips to COMPLETED), savings goals (including
  `progress_percent()`), price alerts (created + triggered via
  `check_price_alerts`), scheduled payments (created + executed via
  `run_scheduled_payments`), admin KYC approve/reject, and admin
  analytics summary.
- Direct database inspection (`mysql -u root cryptowallet_db -e
  "SELECT ..."`) after each of the above to confirm balances,
  transaction rows, and notification rows were written correctly —
  not just that the HTTP response looked right.

### Not touched

- Frontend JS/HTML (`frontend/`) — no ORM code lives there; this pass
  was backend-only, per the actual ask.
- `wallet/tests.py`'s one `User.objects.create_superuser()` fixture
  call, as noted above.
