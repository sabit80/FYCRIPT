# CryptoWallet — Full-Stack (MySQL Edition)

A bKash-style multi-currency wallet app: Django REST Framework backend on
**MySQL**, plain HTML/CSS/JS frontend. One person = one account =
one phone number. Each account can hold **many wallets** (fiat and
crypto), sends money to other accounts by **phone number** (always
landing in the receiver's default receive wallet, auto-converted if
currencies differ), and can freely shift funds between its own wallets.
One account can connect one or more bank accounts.

This build implements every entity from the ER diagram you supplied:
`USER`, `ROLE`, `USER_ROLE`, `KYC`, `BANK_ACCOUNT`, `CURRENCY`, `WALLET`,
`CRYPTO_ADDRESS`, `EXCHANGE_RATE`, `TRANSACTION`, `NOTIFICATION`,
`AUDIT_LOG` (plus `LOGIN_SESSION`, kept from the original build for the
Settings → Active Sessions panel — it isn't in the diagram but doesn't
conflict with it).

```
CryptoWallet-fullstack-mysql/
├── backend/            Django + DRF API (MySQL)
│   ├── wallet/          the one app: models/serializers/views/urls/admin
│   ├── requirements.txt
│   └── .env.example
├── database/
│   └── schema.sql       plain-SQL mirror of the ERD (reference / manual setup)
└── frontend/            static HTML/CSS/JS (unchanged tech, updated pages)
```


## How money moves (the business rules you asked for)

- **Register** → creates the account (unique phone + email) and
  automatically opens **one default receive wallet** in your chosen
  currency. That's the wallet other people's transfers land in.
- **Add wallets** → a user can open as many additional fiat or crypto
  wallets as they like (Wallets page). Crypto wallets get an
  auto-generated deposit address (`CRYPTO_ADDRESS`).
- **Send to a phone number** → exactly like bKash: money always lands
  in the *receiver's default receive wallet*, converted automatically
  via the `EXCHANGE_RATE` table if the sender's wallet is a different
  currency. The receiver can then shift it into any of their own
  wallets.
- **Shift between your own wallets** → pick a destination wallet
  instead of a phone number on the Send page; instant, and converted
  automatically if currencies differ.
- **Bank accounts** → one account can connect one or many bank
  accounts (Settings page).
- **KYC** → zero-or-one submission per account, with a
  pending/approved/rejected status.
- Every send/shift/exchange/deposit/login/KYC-submit/bank-account-change
  writes an `AUDIT_LOG` row and (where relevant) a `NOTIFICATION`.


## 1. Backend setup with Railway MySQL (Windows PowerShell)

From the repository root:

```powershell
cd backend
py -m venv venv
.\venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env` and set the Railway connection string:

```dotenv
DATABASE_URL=mysql://USERNAME:PASSWORD@HOST:PORT/DATABASE
```

Use the complete `DATABASE_URL` provided by Railway. Do not commit this
value because it contains database credentials. The application reads
`DATABASE_URL` in `cryptowallet_backend/settings.py`; no local MySQL
server is required.

Run migrations against the Railway database:

```powershell
python manage.py migrate
python manage.py seed_data       # currencies, roles, starter exchange rates
python manage.py createsuperuser # for /admin/
```

The migrations also install the MySQL stored procedures in
`database/raw_sql/procedures/`. These procedures perform the critical
wallet operations (transfers, deposits, withdrawals, money requests,
group-payment shares, scheduled payments, and wallet registration).

Run the backend with Daphne (recommended because the project supports
WebSockets):

```powershell
daphne cryptowallet_backend.asgi:application
```

For normal HTTP-only development, Django's server can also be used:

```powershell
python manage.py runserver
```

The API is now at `http://127.0.0.1:8000/api/`, admin at
`http://127.0.0.1:8000/admin/`.

`database/schema.sql` is a reference schema. Do not run it manually on
Railway when using Django migrations.

**Note on the default-wallet rule:** unlike PostgreSQL, MySQL has no
conditional/partial unique index, so "exactly one default receive
wallet per user" isn't a DB-level constraint here — `Wallet.save()`
in `wallet/models.py` enforces it by unsetting any previous default
before saving a new one.

### Managing exchange rates

`seed_data` seeds every currency pair against a starting rate table.
From then on, update rates either in `/admin/` (Exchange Rate model)
or by re-running `seed_data` (it's idempotent — `update_or_create`).


## 2. Frontend setup

The frontend is static — no build step. Serve `frontend/` with any
static server and open `index.html` or `login.html`.

Option A — Python static server:

```powershell
# Open a second PowerShell terminal at the repository root
cd frontend
python -m http.server 5501
```

Open `http://127.0.0.1:5501/login.html`.

Option B — VS Code Live Server:

1. Open the `frontend` folder in VS Code.
2. Right-click `login.html`.
3. Select **Open with Live Server**.

If you serve it from a different port than the ones already in
`CORS_ALLOWED_ORIGINS` (see `.env.example`), add that origin to your
`.env`, or set `CORS_ALLOW_ALL_ORIGINS=true` while developing.

`frontend/js/api.js` points at `http://127.0.0.1:8000/api` by default
— update `API_BASE_URL` there if your backend runs elsewhere.

## 3. Useful commands

Run these commands from the `backend` directory with the virtual
environment activated:

```powershell
python manage.py check
python manage.py test wallet
python manage.py showmigrations wallet
python manage.py makemigrations wallet
python manage.py migrate
```

Stop a running server with `Ctrl+C` in its terminal. Stop the frontend
static server separately with `Ctrl+C` in its terminal.


## 4. Quick tour

1. **Create Account** — pick a preferred receive currency; this opens
   your default wallet automatically.
2. **Wallets** — add more fiat/crypto wallets; crypto wallets show a
   deposit address.
3. **Receive** — shows your phone number (share this to get paid) and
   per-wallet receive info.
4. **Send** — choose "Another Account (Phone Number)" to pay someone
   else, or "My Own Wallet (Shift Funds)" to move money between your
   wallets. Both convert automatically across currencies.
5. **Settings** — manage bank accounts and submit KYC.
6. **Transactions / Dashboard / Exchange** — unchanged pages, now
   backed by the real `EXCHANGE_RATE` table and a single-row-per-
   transfer `TRANSACTION` table.


## Notes / things you may want to change

- Default seeded currencies: USD, BDT, EUR, GBP (fiat), BTC, ETH, USDT
  (crypto). Add more in `/admin/` → Currency, then re-run
  `seed_data` after adding matching rate rows if you want automatic
  conversion for them.
- Transfer fee is currently `0` on every transaction — the `fee`
  column exists on `Transaction` if you want to introduce one later
  (e.g. a flat fee or percentage on external `SEND`s).
- Exchange rates in this build are simple static rows seeded once;
  swap `seed_data` for a scheduled job hitting a live rates API if you
  want them to move in real time.
