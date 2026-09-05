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


## 1. MySQL setup

Install MySQL (8.0.16+, for `CHECK` constraint support) if you don't
have it, then create the database and user (adjust the password to
whatever you put in `.env`):

```bash
mysql -u root -p
```

```sql
CREATE DATABASE cryptowallet_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'cryptowallet_user'@'localhost' IDENTIFIED BY 'CryptoWallet@123';
GRANT ALL PRIVILEGES ON cryptowallet_db.* TO 'cryptowallet_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

You do **not** need to run `database/schema.sql` manually if you use
Django's migrations below — that file is just a plain-SQL reference
mirroring the same tables, kept in case you ever want to stand the
schema up without Django.


## 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# edit .env if your DB name/user/password/host differ

python manage.py makemigrations wallet
python manage.py migrate

python manage.py seed_data       # currencies, roles, starter exchange rates
python manage.py createsuperuser # for /admin/

python manage.py runserver
```

The API is now at `http://127.0.0.1:8000/api/`, admin at
`http://127.0.0.1:8000/admin/`.

**Why `makemigrations` instead of shipped migration files?** The
models changed enough from the very first build (custom phone-based
User, new Currency/Wallet/ExchangeRate/CryptoAddress tables) that
hand-editing old migrations would be more fragile than generating
fresh ones against your actual MySQL connection. It's one extra
command, run once.

**Note on the default-wallet rule:** unlike PostgreSQL, MySQL has no
conditional/partial unique index, so "exactly one default receive
wallet per user" isn't a DB-level constraint here — `Wallet.save()`
in `wallet/models.py` enforces it by unsetting any previous default
before saving a new one.

### Managing exchange rates

`seed_data` seeds every currency pair against a starting rate table.
From then on, update rates either in `/admin/` (Exchange Rate model)
or by re-running `seed_data` (it's idempotent — `update_or_create`).


## 3. Frontend setup

The frontend is static — no build step. Serve `frontend/` with any
static server (VS Code Live Server, `python -m http.server`, etc.) and
open `index.html` / `login.html` / `create-account.html`.

If you serve it from a different port than the ones already in
`CORS_ALLOWED_ORIGINS` (see `.env.example`), add that origin to your
`.env`, or set `CORS_ALLOW_ALL_ORIGINS=true` while developing.

`frontend/js/api.js` points at `http://127.0.0.1:8000/api` by default
— update `API_BASE_URL` there if your backend runs elsewhere.


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


//RUN::

cd backend

.\venv\Scripts\activate

daphne cryptowallet_backend.asgi:application

then for frontend connection

go live login.html

//STOP 

kill live server

Ctrl +C in backend terminal