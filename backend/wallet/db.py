"""
Raw-SQL data access layer â€” the project's "own ORM".

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
query-builder method or an instance `.save()`/`.delete()` â€” see
`hydrate()` below for how model instances get populated for the DRF
serializers without ever touching the database.

Every function here uses %s placeholders and passes parameters as a
list/tuple â€” never string-formats a value into SQL. That is what keeps
every query in this module injection-safe.
"""

from django.db import connection

from .sql_loader import load_sql


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


def call_procedure(name, params=None):
    """Call a MySQL stored procedure with parameterized arguments."""
    with connection.cursor() as cursor:
        cursor.callproc(name, params or [])


def call_wallet_procedure(name, params=None):
    """Execute a mutation procedure and discard any driver result sets."""
    call_procedure(name, params)


# =====================================================
# TABLE REGISTRY
#
# Django's default table name for an app model is
# "<app_label>_<modelname lower-cased>" and the default column name for
# a ForeignKey field is "<field name>_id" â€” both confirmed against the
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


def model_columns(model_cls):
    """Return concrete model columns for explicit SELECT projections."""
    return ', '.join(field.column for field in model_cls._meta.concrete_fields)


# =====================================================
# GENERIC CRUD â€” the "own ORM" surface every view/serializer uses
# =====================================================

def insert(model_cls, **fields):
    """INSERT one row. Returns the AUTO_INCREMENT id (lastrowid) for
    tables with an integer PK; for tables with an app-assigned string
    PK (wallet_id, transaction_id, ...) the caller already put that
    value in `fields`, so the return value can just be ignored."""
    table = table_name(model_cls)
    cols = list(fields.keys())
    placeholders = ', '.join(['%s'] * len(cols))
    sql = load_sql("crud/insert").format(
        table=table,
        columns=", ".join(cols),
        placeholders=placeholders,
    )
    _rowcount, lastrowid = execute(sql, [fields[c] for c in cols])
    return lastrowid


def update_by_pk(model_cls, pk_col, pk_val, **fields):
    """UPDATE exactly one row by primary key. No-ops (0 fields) safely."""
    if not fields:
        return 0
    table = table_name(model_cls)
    set_clause = ', '.join(f"{c} = %s" for c in fields)
    sql = load_sql("crud/update_by_pk").format(
        table=table, set_clause=set_clause, pk_col=pk_col,
    )
    rowcount, _ = execute(sql, list(fields.values()) + [pk_val])
    return rowcount


def update_where(model_cls, where_sql, where_params, **fields):
    """UPDATE every row matching a raw WHERE clause (caller supplies
    the clause + its params, e.g. 'user_id = %s AND is_default_receive = 1')."""
    if not fields:
        return 0
    table = table_name(model_cls)
    set_clause = ', '.join(f"{c} = %s" for c in fields)
    sql = load_sql("crud/update_where").format(
        table=table, set_clause=set_clause, where_sql=where_sql,
    )
    rowcount, _ = execute(sql, list(fields.values()) + list(where_params))
    return rowcount


def delete_by_pk(model_cls, pk_col, pk_val):
    table = table_name(model_cls)
    rowcount, _ = execute(
        load_sql("crud/delete_by_pk").format(table=table, pk_col=pk_col),
        [pk_val],
    )
    return rowcount


def get_row(model_cls, pk_col, pk_val):
    """SELECT * for one row by primary key, or None."""
    table = table_name(model_cls)
    return fetchone(
        load_sql("crud/get_row").format(
            table=table,
            columns=model_columns(model_cls),
            pk_col=pk_col,
        ),
        [pk_val],
    )


def find_one(model_cls, where_sql, where_params=None, order_by=None):
    table = table_name(model_cls)
    sql = load_sql("crud/find_one").format(
        table=table,
        columns=model_columns(model_cls),
        where_sql=where_sql,
        order_clause=f"ORDER BY {order_by}" if order_by else "",
    )
    return fetchone(sql, where_params or [])


def find_all(model_cls, where_sql=None, where_params=None, order_by=None, limit=None):
    table = table_name(model_cls)
    sql = load_sql("crud/find_all").format(
        table=table,
        columns=model_columns(model_cls),
        where_clause=f"WHERE {where_sql}" if where_sql else "",
        order_clause=f"ORDER BY {order_by}" if order_by else "",
        limit_clause=f"LIMIT {int(limit)}" if limit else "",
    )
    return fetchall(sql, where_params or [])


def count_where(model_cls, where_sql=None, where_params=None):
    table = table_name(model_cls)
    sql = load_sql("crud/count_where").format(
        table=table,
        where_clause=f"WHERE {where_sql}" if where_sql else "",
    )
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
# HYDRATION â€” turn a raw dict row into an (unsaved) Django model
# instance so DRF's ModelSerializer keeps working unchanged.
#
# `Model(**row)` never touches the database by itself â€” it just sets
# python attributes. Passing foreign-key columns as `<field>_id=value`
# (exactly the column name `SELECT *` gives back) avoids Django's FK
# descriptor doing a lazy SELECT the first time related code reads
# `.currency` / `.user` etc. For serializer fields that traverse a
# relation by name (e.g. `source='user.name'`, `wallet.currency.type`),
# the caller passes the already-hydrated related instance(s) as extra
# keyword args here, which get attached directly â€” again with no query.
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
# WALLET â€” single-default-receive-wallet rule
#
# MySQL has no conditional/partial unique index, so "exactly one
# default receive wallet per user" can't be a DB constraint here.
# This replaces the raw UPDATE that used to live inside
# Wallet.save() (see models.py) â€” call it before inserting/updating a
# wallet row with is_default_receive=True.
# =====================================================

def unset_other_default_wallets(user_id, except_wallet_id=None):
    if except_wallet_id:
        return execute(
            load_sql("wallet/unset_other_default_wallets"),
            [False, user_id, except_wallet_id],
        )[0]
    return execute(
        load_sql("wallet/unset_all_default_wallets"),
        [False, user_id],
    )[0]


# =====================================================
# EXPLICIT APPLICATION QUERIES
#
# These functions are the public data-access API used by views.py.  Each
# operation has a fixed SQL statement; callers do not provide table names,
# column names, WHERE clauses, or ORDER BY fragments.
# =====================================================

def create_audit_log(user_id, action, remarks, ip_address, timestamp):
    return execute(
        load_sql("app/create_audit_log_1"),
        [user_id, action, remarks, ip_address, timestamp],
    )[1]


def create_notification(user_id, message, notification_type, read_status, timestamp):
    return execute(
        load_sql("app/create_notification_1"),
        [user_id, message, notification_type, read_status, timestamp],
    )[1]


def get_notification_by_id(notification_id):
    return fetchone(
        load_sql("app/get_notification_by_id_1"),
        [notification_id],
    )


def update_user_fields(user_id, fields):
    statements = {
        "recovery_codes_hash": (
            load_sql("app/update_user_fields_7"),
            "recovery_codes_hash",
        ),
        "transaction_pin_hash": (
            load_sql("app/update_user_fields_8"),
            "transaction_pin_hash",
        ),
        "password": (
            load_sql("app/update_user_fields_9"),
            "password",
        ),
        "account_type_business_name": (
            load_sql("app/update_user_fields_10"),
            "account_type_business_name",
        ),
        "deactivate": (
            load_sql("app/update_user_fields_11"),
            "deactivate",
        ),
        "fraud_flag": (
            load_sql("app/update_user_fields_12"),
            "fraud_flag",
        ),
        "clear_fraud_flag": (
            load_sql("app/update_user_fields_13"),
            "clear_fraud_flag",
        ),
    }
    keys = set(fields)
    if keys == {"recovery_codes_hash"}:
        sql, _ = statements["recovery_codes_hash"]
        return execute(sql, [fields["recovery_codes_hash"], user_id])[0]
    if keys == {"transaction_pin_hash"}:
        sql, _ = statements["transaction_pin_hash"]
        return execute(sql, [fields["transaction_pin_hash"], user_id])[0]
    if keys == {"password"}:
        sql, _ = statements["password"]
        return execute(sql, [fields["password"], user_id])[0]
    if keys == {"account_type", "business_name"}:
        sql, _ = statements["account_type_business_name"]
        return execute(sql, [fields["account_type"], fields["business_name"], user_id])[0]
    if keys == {"name"}:
        return execute(
            load_sql("app/update_user_fields_1"),
            [fields["name"], user_id],
        )[0]
    if keys == {"account_type"}:
        return execute(
            load_sql("app/update_user_fields_2"),
            [fields["account_type"], user_id],
        )[0]
    if keys == {"business_name"}:
        return execute(
            load_sql("app/update_user_fields_3"),
            [fields["business_name"], user_id],
        )[0]
    if keys == {"name", "account_type"}:
        return execute(
            load_sql("app/update_user_fields_4"),
            [fields["name"], fields["account_type"], user_id],
        )[0]
    if keys == {"name", "business_name"}:
        return execute(
            load_sql("app/update_user_fields_5"),
            [fields["name"], fields["business_name"], user_id],
        )[0]
    if keys == {"name", "account_type", "business_name"}:
        return execute(
            load_sql("app/update_user_fields_6"),
            [
                fields["name"], fields["account_type"],
                fields["business_name"], user_id,
            ],
        )[0]
    if keys == {"status", "is_active"}:
        sql, _ = statements["deactivate"]
        return execute(sql, [fields["status"], fields["is_active"], user_id])[0]
    if keys == {"is_flagged", "flagged_reason", "flagged_at"}:
        operation = "clear_fraud_flag" if not fields["is_flagged"] else "fraud_flag"
        sql, _ = statements[operation]
        return execute(
            sql,
            [fields["is_flagged"], fields["flagged_reason"], fields["flagged_at"], user_id],
        )[0]
    raise ValueError(f"Unsupported user update fields: {sorted(keys)}")


def create_transaction(transaction_id, fields):
    return execute(
        load_sql("app/create_transaction_1"),
        [
            transaction_id, fields.get("sender_wallet_id"),
            fields.get("receiver_wallet_id"), fields["transaction_type"],
            fields["amount"], fields.get("received_amount"),
            fields.get("exchange_rate"), fields.get("fee"),
            fields.get("status", "COMPLETED"), fields.get("category", ""),
            fields.get("date"),
        ],
    )[1]


def get_transaction_by_id(transaction_id):
    return fetchone(
        load_sql("app/get_transaction_by_id_1"),
        [transaction_id],
    )


def update_wallet_fields(wallet_id, fields):
    if set(fields) == {"balance"}:
        return execute(
            load_sql("app/update_wallet_fields_1"),
            [fields["balance"], wallet_id],
        )[0]
    if set(fields) == {"name"}:
        return execute(
            load_sql("app/update_wallet_fields_2"),
            [fields["name"], wallet_id],
        )[0]
    if set(fields) == {"wallet_status"}:
        return execute(
            load_sql("app/update_wallet_fields_3"),
            [fields["wallet_status"], wallet_id],
        )[0]
    if set(fields) == {"is_default_receive"}:
        return execute(
            load_sql("app/update_wallet_fields_4"),
            [fields["is_default_receive"], wallet_id],
        )[0]
    raise ValueError(f"Unsupported wallet update fields: {sorted(fields)}")


def get_wallet_by_id(wallet_id):
    return fetchone(
        load_sql("app/get_wallet_by_id_1"),
        [wallet_id],
    )


def get_wallet_by_user_id(wallet_id, user_id):
    return fetchone(
        load_sql("app/get_wallet_by_user_id_1"),
        [wallet_id, user_id],
    )


def get_default_wallet_by_user_id(user_id):
    return fetchone(
        load_sql("app/get_default_wallet_by_user_id_1"),
        [user_id],
    )


def get_currency_by_name(currency_name):
    return fetchone(
        load_sql("app/get_currency_by_name_1"),
        [currency_name],
    )


def create_wallet(fields):
    return execute(
        load_sql("app/create_wallet_1"),
        [
            fields["wallet_id"], fields["user_id"], fields["currency_id"],
            fields["balance"], fields["is_default_receive"],
            fields["wallet_status"], fields["name"], fields["created_at"],
        ],
    )[1]


def create_crypto_address(fields):
    return execute(
        load_sql("app/create_crypto_address_1"),
        [
            fields["address_id"], fields["wallet_id"], fields["blockchain"],
            fields["public_address"],
        ],
    )[1]


def get_exchange_rate(from_currency, to_currency):
    return fetchone(
        load_sql("app/get_exchange_rate_1"),
        [from_currency, to_currency],
    )


def list_exchange_rates():
    return fetchall(load_sql("app/list_exchange_rates_1"))


def list_currencies():
    return fetchall(
        load_sql("app/list_currencies_1")
    )


def get_user_by_role_name(role_name):
    return fetchone(
        load_sql("app/get_user_by_role_name_1"),
        [role_name],
    )


def create_role(role_name):
    return execute(
        load_sql("app/create_role_1"),
        [role_name],
    )[1]


def user_role_exists(user_id, role_id):
    return scalar(
        load_sql("app/user_role_exists_1"),
        [user_id, role_id],
    ) > 0


def create_user_role(user_id, role_id, assigned_at):
    return execute(
        load_sql("app/create_user_role_1"),
        [user_id, role_id, assigned_at],
    )[1]


def create_login_session(user_id, ip_address, device_info, login_time):
    return execute(
        load_sql("app/create_login_session_1"),
        [user_id, ip_address, device_info, login_time],
    )[1]


def get_user_by_id(user_id):
    return fetchone(
        load_sql("app/get_user_by_id_1"),
        [user_id],
    )


def get_user_by_email(email):
    return fetchone(
        load_sql("app/get_user_by_email_1"),
        [email],
    )


def get_user_by_phone(phone):
    return fetchone(
        load_sql("app/get_user_by_phone_1"),
        [phone],
    )


def list_bank_accounts(user_id):
    return fetchall(
        load_sql("app/list_bank_accounts_1"),
        [user_id],
    )


def get_bank_account_by_user_id(account_id, user_id):
    return fetchone(
        load_sql("app/get_bank_account_by_user_id_1"),
        [account_id, user_id],
    )


def create_bank_account(fields):
    return execute(
        load_sql("app/create_bank_account_1"),
        [fields["user_id"], fields["bank_name"], fields["account_number"], fields["created_at"]],
    )[1]


def delete_bank_account(account_id):
    return execute(load_sql("app/delete_bank_account_1"), [account_id])[0]


def get_kyc_by_user_id(user_id):
    return fetchone(
        load_sql("app/get_kyc_by_user_id_1"),
        [user_id],
    )


def get_kyc_by_id(kyc_id):
    return fetchone(load_sql("app/get_kyc_by_id_1"), [kyc_id])


def create_kyc(fields):
    return execute(
        load_sql("app/create_kyc_1"),
        [
            fields["user_id"], fields.get("nid_number"), fields.get("passport_number"),
            fields["submission_date"], fields["verification_status"],
            fields.get("reviewed_by_id"), fields.get("reviewed_at"),
            fields.get("admin_remarks"),
        ],
    )[1]


def update_kyc(kyc_id, fields):
    return execute(
        load_sql("app/update_kyc_1"),
        [
            fields.get("nid_number"), fields.get("passport_number"),
            fields["verification_status"], kyc_id,
        ],
    )[0]


def list_wallets(user_id):
    return fetchall(
        load_sql("app/list_wallets_1"),
        [user_id],
    )


def delete_wallet(wallet_id):
    return execute(
        load_sql("app/delete_wallet_1"),
        [wallet_id],
    )[0]


def list_auto_save_goals(user_id):
    return fetchall(
        load_sql("app/list_auto_save_goals_1"),
        [user_id],
    )


def list_login_sessions(user_id):
    return fetchall(
        load_sql("app/list_login_sessions_1"),
        [user_id],
    )


def list_notifications(user_id):
    return fetchall(
        load_sql("app/list_notifications_1"),
        [user_id],
    )


def get_notification_for_user(notification_id, user_id):
    return fetchone(
        load_sql("app/get_notification_for_user_1"),
        [notification_id, user_id],
    )


def mark_notification_read(notification_id):
    return execute(
        load_sql("app/mark_notification_read_1"),
        [True, notification_id],
    )[0]


def list_kyc(status_filter=None):
    if status_filter is None:
        return fetchall(
            load_sql("app/list_kyc_2")
        )
    return fetchall(
        load_sql("app/list_kyc_1"),
        [status_filter],
    )


def approve_kyc(kyc_id, reviewed_by_id, reviewed_at, admin_remarks):
    return execute(
        load_sql("app/approve_kyc_1"),
        ["APPROVED", reviewed_by_id, reviewed_at, admin_remarks, kyc_id],
    )[0]


def reject_kyc(kyc_id, reviewed_by_id, reviewed_at, admin_remarks):
    return execute(
        load_sql("app/reject_kyc_1"),
        ["REJECTED", reviewed_by_id, reviewed_at, admin_remarks, kyc_id],
    )[0]


def count_users():
    return scalar(load_sql("app/count_users_1")) or 0


def count_active_users():
    return scalar(
        load_sql("app/count_active_users_1"),
        ["ACTIVE"],
    ) or 0


def count_flagged_users():
    return scalar(
        load_sql("app/count_flagged_users_1")
    ) or 0


def count_pending_kyc():
    return scalar(
        load_sql("app/count_pending_kyc_1"),
        ["PENDING"],
    ) or 0


def count_transactions():
    return scalar(load_sql("app/count_transactions_1")) or 0


def count_wallets():
    return scalar(load_sql("app/count_wallets_1")) or 0


def transaction_volume_by_currency():
    return fetchall(
        load_sql("app/transaction_volume_by_currency_1")
    )


def transaction_volume_by_day(since):
    return fetchall(
        load_sql("app/transaction_volume_by_day_1"),
        [since],
    )


def list_flagged_users():
    return fetchall(
        load_sql("app/list_flagged_users_1")
    )


def list_scheduled_payments(user_id):
    return fetchall(
        load_sql("app/list_scheduled_payments_1"),
        [user_id],
    )


def user_exists_by_phone(phone):
    return scalar(
        load_sql("app/user_exists_by_phone_1"),
        [phone],
    ) > 0


def create_scheduled_payment(fields):
    return execute(
        load_sql("app/create_scheduled_payment_1"),
        [
            fields["schedule_id"], fields["owner_id"], fields["sender_wallet_id"],
            fields.get("recipient_phone"), fields.get("recipient_wallet_id"),
            fields["amount"], fields.get("note", ""), fields["frequency"],
            fields["next_run_at"], fields.get("last_run_at"), fields["status"],
            fields["created_at"],
        ],
    )[1]


def get_scheduled_payment(schedule_id, owner_id):
    return fetchone(
        load_sql("app/get_scheduled_payment_1"),
        [schedule_id, owner_id],
    )


def update_scheduled_payment_status(schedule_id, status):
    return execute(
        load_sql("app/update_scheduled_payment_status_1"),
        [status, schedule_id],
    )[0]


def get_money_request(request_id, payer_id=None):
    if payer_id is None:
        return fetchone(
            load_sql("app/get_money_request_2"),
            [request_id],
        )
    return fetchone(
        load_sql("app/get_money_request_1"),
        [request_id, payer_id],
    )


def list_money_requests(user_id):
    return fetchall(
        load_sql("app/list_money_requests_1"),
        [user_id, user_id],
    )


def create_money_request(fields):
    return execute(
        load_sql("app/create_money_request_1"),
        [
            fields["request_id"], fields["requester_id"], fields["requester_wallet_id"],
            fields["payer_id"], fields["amount"], fields.get("note", ""),
            fields["status"], fields.get("transaction_id"), fields["created_at"],
            fields.get("responded_at"),
        ],
    )[1]


def update_money_request(request_id, status, transaction_id=None, responded_at=None):
    return execute(
        load_sql("app/update_money_request_1"),
        [status, transaction_id, responded_at, request_id],
    )[0]


def get_group_payment(group_payment_id):
    return fetchone(
        load_sql("app/get_group_payment_1"),
        [group_payment_id],
    )


def list_group_payment_participants(group_payment_id):
    return fetchall(
        load_sql("app/list_group_payment_participants_1"),
        [group_payment_id],
    )


def list_group_payments_for_user(user_id):
    return fetchall(
        load_sql("app/list_group_payments_for_user_1"),
        [user_id, user_id],
    )


def create_group_payment(fields):
    return execute(
        load_sql("app/create_group_payment_1"),
        [
            fields["group_payment_id"], fields["organizer_id"],
            fields["receiver_wallet_id"], fields["title"],
            fields["total_amount"], fields["status"], fields["created_at"],
        ],
    )[1]


def get_group_payment_participant(group_payment_id, user_id):
    return fetchone(
        load_sql("app/get_group_payment_participant_1"),
        [group_payment_id, user_id],
    )


def update_group_payment_participant(participant_id, fields):
    if set(fields) == {"share_amount"}:
        return execute(
            load_sql("app/update_group_payment_participant_2"),
            [fields["share_amount"], participant_id],
        )[0]
    return execute(
        load_sql("app/update_group_payment_participant_1"),
        [fields["status"], fields["transaction_id"], fields["paid_at"], participant_id],
    )[0]


def create_group_payment_participant(fields):
    return execute(
        load_sql("app/create_group_payment_participant_1"),
        [
            fields["group_payment_id"], fields["user_id"], fields["share_amount"],
            fields["status"], fields.get("transaction_id"), fields.get("paid_at"),
        ],
    )[1]


def update_group_payment(group_payment_id, fields):
    return execute(
        load_sql("app/update_group_payment_1"),
        [fields["status"], group_payment_id],
    )[0]


def get_savings_goal(goal_id, user_id=None):
    if user_id is None:
        return fetchone(
            load_sql("app/get_savings_goal_2"),
            [goal_id],
        )
    return fetchone(
        load_sql("app/get_savings_goal_1"),
        [goal_id, user_id],
    )


def list_savings_goals(user_id):
    return fetchall(
        load_sql("app/list_savings_goals_1"),
        [user_id],
    )


def create_savings_goal(fields):
    return execute(
        load_sql("app/create_savings_goal_1"),
        [
            fields["goal_id"], fields["user_id"], fields["savings_wallet_id"],
            fields["name"], fields["target_amount"], fields.get("deadline"),
            fields.get("auto_save_percent", 0), fields["is_active"],
            fields["created_at"],
        ],
    )[1]


def update_savings_goal(goal_id, is_active):
    return execute(
        load_sql("app/update_savings_goal_1"),
        [is_active, goal_id],
    )[0]


def list_price_alerts(user_id):
    return fetchall(
        load_sql("app/list_price_alerts_1"),
        [user_id],
    )


def create_price_alert(fields):
    return execute(
        load_sql("app/create_price_alert_1"),
        [
            fields["alert_id"], fields["user_id"], fields["from_currency"],
            fields["to_currency"], fields["threshold_rate"], fields["is_active"],
            fields.get("triggered_at"), fields["created_at"],
        ],
    )[1]


def get_price_alert(alert_id):
    return fetchone(
        load_sql("app/get_price_alert_1"),
        [alert_id],
    )


def delete_price_alert(alert_id):
    return execute(
        load_sql("app/delete_price_alert_1"),
        [alert_id],
    )[0]


def get_payment_link(link_id, active_only=False):
    if active_only:
        return fetchone(
            load_sql("app/get_payment_link_2"),
            [link_id],
        )
    return fetchone(
        load_sql("app/get_payment_link_1"),
        [link_id],
    )


def list_payment_links(merchant_id):
    return fetchall(
        load_sql("app/list_payment_links_1"),
        [merchant_id],
    )


def create_payment_link(fields):
    return execute(
        load_sql("app/create_payment_link_1"),
        [
            fields["link_id"], fields["merchant_id"], fields["receiving_wallet_id"],
            fields["title"], fields.get("amount"), fields["is_active"],
            fields["created_at"],
        ],
    )[1]


def sent_transactions_since(user_id, since):
    return fetchall(
        load_sql("app/sent_transactions_since_1"),
        [user_id, since],
    )


def count_recent_sends(user_id, since):
    return scalar(
        load_sql("app/count_recent_sends_1"),
        [user_id, since],
    ) or 0


def list_transactions_for_user(user_id, currency=None):
    if currency:
        sql = load_sql("app/list_transactions_for_user_currency")
        params = [user_id, user_id, currency, currency]
    else:
        sql = load_sql("app/list_transactions_for_user")
        params = [user_id, user_id]
    return fetchall(sql, params)


def deactivate_wallets_for_user(user_id):
    return execute(
        load_sql("app/deactivate_wallets_for_user_1"),
        ["FROZEN", user_id],
    )[0]
