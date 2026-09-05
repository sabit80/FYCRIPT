"""
Raw-SQL data access layer — the project's "own ORM".

CSE216 (60% milestone) requires every database read/write to be a
hand-written, parameterised SQL statement rather than Django's ORM query
builder (`.objects.filter/get/create/update/exists/count/...`, and
instance `.save()` / `.delete()`). This module is the one place that
talks to the database with `cursor.execute(...)`; every view/serializer
in this app goes through the functions here instead of touching
`Model.objects` or calling `.save()`/`.delete()` on a model instance.

Django's Model *classes* in models.py are kept only as schema/migration
definitions (so `manage.py migrate` can still create the tables) and
because SimpleJWT's authentication needs a model instance for
`request.user`. No business logic anywhere in this app calls a
query-builder method or an instance `.save()`/`.delete()` — see
`hydrate()` below for how model instances get populated for the DRF
serializers without ever touching the database.

Every function here uses %s placeholders and passes parameters as a
list/tuple — never string-formats a value into SQL. That is what keeps
every query in this module injection-safe.
"""

from django.db import connection


# =====================================================
# LOW-LEVEL CURSOR HELPERS
# =====================================================

def dictfetchone(cursor):
    """Return a single row as a dict, or None."""
    if cursor.description is None:
        return None
    columns = [col[0] for col in cursor.description]
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(zip(columns, row))


def dictfetchall(cursor):
    """Return all rows as a list of dicts."""
    if cursor.description is None:
        return []
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetchone(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return dictfetchone(cursor)


def fetchall(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return dictfetchall(cursor)


def execute(sql, params=None):
    """INSERT/UPDATE/DELETE. Returns (rowcount, lastrowid)."""
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return cursor.rowcount, cursor.lastrowid


def scalar(sql, params=None):
    """Run a query and return the single column of the first row (or None)."""
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        row = cursor.fetchone()
        return row[0] if row else None


# =====================================================
# TABLE REGISTRY
#
# Django's default table name for an app model is
# "<app_label>_<modelname lower-cased>" and the default column name for
# a ForeignKey field is "<field name>_id" — both confirmed against the
# real migrated schema (see MIGRATION_NOTES.md "How to verify"). Listed
# here once so every helper below can look a table name up by model
# class instead of repeating string literals everywhere.
# =====================================================

def _tables():
    # Imported lazily to dodge any import-order issues with models.py.
    from . import models as m
    return {
        m.User: 'wallet_user',
        m.Role: 'wallet_role',
        m.UserRole: 'wallet_userrole',
        m.KYC: 'wallet_kyc',
        m.BankAccount: 'wallet_bankaccount',
        m.Currency: 'wallet_currency',
        m.Wallet: 'wallet_wallet',
        m.CryptoAddress: 'wallet_cryptoaddress',
        m.ExchangeRate: 'wallet_exchangerate',
        m.Transaction: 'wallet_transaction',
        m.Notification: 'wallet_notification',
        m.AuditLog: 'wallet_auditlog',
        m.LoginSession: 'wallet_loginsession',
        m.MoneyRequest: 'wallet_moneyrequest',
        m.ScheduledPayment: 'wallet_scheduledpayment',
        m.GroupPayment: 'wallet_grouppayment',
        m.GroupPaymentParticipant: 'wallet_grouppaymentparticipant',
        m.SavingsGoal: 'wallet_savingsgoal',
        m.PriceAlert: 'wallet_pricealert',
        m.PaymentLink: 'wallet_paymentlink',
    }


def table_name(model_cls):
    return _tables()[model_cls]


# =====================================================
# GENERIC CRUD — the "own ORM" surface every view/serializer uses
# =====================================================

def insert(model_cls, **fields):
    """INSERT one row. Returns the AUTO_INCREMENT id (lastrowid) for
    tables with an integer PK; for tables with an app-assigned string
    PK (wallet_id, transaction_id, ...) the caller already put that
    value in `fields`, so the return value can just be ignored."""
    table = table_name(model_cls)
    cols = list(fields.keys())
    placeholders = ', '.join(['%s'] * len(cols))
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    _rowcount, lastrowid = execute(sql, [fields[c] for c in cols])
    return lastrowid


def update_by_pk(model_cls, pk_col, pk_val, **fields):
    """UPDATE exactly one row by primary key. No-ops (0 fields) safely."""
    if not fields:
        return 0
    table = table_name(model_cls)
    set_clause = ', '.join(f"{c} = %s" for c in fields)
    sql = f"UPDATE {table} SET {set_clause} WHERE {pk_col} = %s"
    rowcount, _ = execute(sql, list(fields.values()) + [pk_val])
    return rowcount


def update_where(model_cls, where_sql, where_params, **fields):
    """UPDATE every row matching a raw WHERE clause (caller supplies
    the clause + its params, e.g. 'user_id = %s AND is_default_receive = 1')."""
    if not fields:
        return 0
    table = table_name(model_cls)
    set_clause = ', '.join(f"{c} = %s" for c in fields)
    sql = f"UPDATE {table} SET {set_clause} WHERE {where_sql}"
    rowcount, _ = execute(sql, list(fields.values()) + list(where_params))
    return rowcount


def delete_by_pk(model_cls, pk_col, pk_val):
    table = table_name(model_cls)
    rowcount, _ = execute(f"DELETE FROM {table} WHERE {pk_col} = %s", [pk_val])
    return rowcount


def get_row(model_cls, pk_col, pk_val):
    """SELECT * for one row by primary key, or None."""
    table = table_name(model_cls)
    return fetchone(f"SELECT * FROM {table} WHERE {pk_col} = %s LIMIT 1", [pk_val])


def find_one(model_cls, where_sql, where_params=None, order_by=None):
    table = table_name(model_cls)
    sql = f"SELECT * FROM {table} WHERE {where_sql}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    sql += " LIMIT 1"
    return fetchone(sql, where_params or [])


def find_all(model_cls, where_sql=None, where_params=None, order_by=None, limit=None):
    table = table_name(model_cls)
    sql = f"SELECT * FROM {table}"
    if where_sql:
        sql += f" WHERE {where_sql}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return fetchall(sql, where_params or [])


def count_where(model_cls, where_sql=None, where_params=None):
    table = table_name(model_cls)
    sql = f"SELECT COUNT(*) FROM {table}"
    if where_sql:
        sql += f" WHERE {where_sql}"
    return scalar(sql, where_params or []) or 0


def exists_where(model_cls, where_sql, where_params=None):
    return count_where(model_cls, where_sql, where_params) > 0


def upsert(model_cls, match_sql, match_params, defaults):
    """Raw-SQL replacement for `Model.objects.update_or_create(**match,
    defaults=defaults)`: UPDATE the matching row if one exists,
    otherwise INSERT match fields + defaults together. `match_sql` is a
    plain `col = %s AND col2 = %s`-style WHERE clause; `match_params`
    are its values in the same order. Returns (row_dict, created)."""
    existing = find_one(model_cls, match_sql, match_params)
    if existing:
        if defaults:
            update_where(model_cls, match_sql, match_params, **defaults)
        return find_one(model_cls, match_sql, match_params), False

    # match_sql is always simple "col = %s [AND col2 = %s ...]" here,
    # built by this module's own callers (see seed_data.py /
    # sync_live_rates.py), so parsing the column names back out is safe.
    match_cols = [part.split('=')[0].strip() for part in match_sql.split(' AND ')]
    fields = dict(zip(match_cols, match_params))
    fields.update(defaults)
    insert(model_cls, **fields)
    return find_one(model_cls, match_sql, match_params), True


def get_or_create_simple(model_cls, **match):
    """Raw-SQL replacement for `Model.objects.get_or_create(**match)`
    for models with no extra defaults beyond the match fields
    themselves (e.g. Role.get_or_create(role_name=...))."""
    where_sql = ' AND '.join(f"{k} = %s" for k in match)
    existing = find_one(model_cls, where_sql, list(match.values()))
    if existing:
        return existing, False
    new_id = insert(model_cls, **match)
    row = get_row(model_cls, 'id', new_id) if new_id else find_one(model_cls, where_sql, list(match.values()))
    return row, True


# =====================================================
# HYDRATION — turn a raw dict row into an (unsaved) Django model
# instance so DRF's ModelSerializer keeps working unchanged.
#
# `Model(**row)` never touches the database by itself — it just sets
# python attributes. Passing foreign-key columns as `<field>_id=value`
# (exactly the column name `SELECT *` gives back) avoids Django's FK
# descriptor doing a lazy SELECT the first time related code reads
# `.currency` / `.user` etc. For serializer fields that traverse a
# relation by name (e.g. `source='user.name'`, `wallet.currency.type`),
# the caller passes the already-hydrated related instance(s) as extra
# keyword args here, which get attached directly — again with no query.
# =====================================================

def hydrate(model_cls, row, **related):
    if row is None:
        return None
    obj = model_cls(**row)
    for attr, value in related.items():
        setattr(obj, attr, value)
    return obj


def hydrate_all(model_cls, rows, **related):
    return [hydrate(model_cls, row, **related) for row in rows]


# =====================================================
# WALLET — single-default-receive-wallet rule
#
# MySQL has no conditional/partial unique index, so "exactly one
# default receive wallet per user" can't be a DB constraint here.
# This replaces the raw UPDATE that used to live inside
# Wallet.save() (see models.py) — call it before inserting/updating a
# wallet row with is_default_receive=True.
# =====================================================

def unset_other_default_wallets(user_id, except_wallet_id=None):
    from . import models as m
    where_sql = "user_id = %s AND is_default_receive = 1"
    params = [user_id]
    if except_wallet_id:
        where_sql += " AND wallet_id != %s"
        params.append(except_wallet_id)
    return update_where(m.Wallet, where_sql, params, is_default_receive=False)
