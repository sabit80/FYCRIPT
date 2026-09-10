"""Simple raw-SQL database functions for CryptoWallet.

The application does not use Django ORM queries for business data.
Each function below has a clear purpose and contains the SQL for that
feature directly. Values are always passed with %s parameters.
"""

import json
from django.db import connection


def _one(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))


def _many(cursor):
    rows = cursor.fetchall()
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def hydrate(model_class, row, **related):
    if row is None:
        return None
    obj = model_class(**row)
    for name, value in related.items():
        setattr(obj, name, value)
    return obj


def hydrate_all(model_class, rows, **related):
    return [hydrate(model_class, row, **related) for row in rows]


# =====================================================
# USERS
# =====================================================

def get_user_by_id(user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_user WHERE id = %s LIMIT 1", [user_id])
        return _one(cursor)


def get_user_by_email(email):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_user WHERE LOWER(email) = LOWER(%s) LIMIT 1", [email])
        return _one(cursor)


def get_user_by_phone(phone):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_user WHERE phone = %s LIMIT 1", [phone])
        return _one(cursor)


def user_email_exists(email):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM wallet_user WHERE LOWER(email) = LOWER(%s)", [email])
        return cursor.fetchone()[0] > 0


def user_phone_exists(phone):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM wallet_user WHERE phone = %s", [phone])
        return cursor.fetchone()[0] > 0


def referral_code_exists(referral_code):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM wallet_user WHERE referral_code = %s", [referral_code])
        return cursor.fetchone()[0] > 0


def get_user_by_referral_code(referral_code):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_user WHERE referral_code = %s LIMIT 1", [referral_code])
        return _one(cursor)


def create_user(fields):
    columns = [
        'password', 'last_login', 'is_superuser', 'first_name', 'last_name',
        'is_staff', 'is_active', 'date_joined', 'email', 'name', 'phone',
        'status', 'registration_date', 'transaction_pin_hash', 'flagged_at',
        'flagged_reason', 'is_flagged', 'recovery_codes_hash', 'referral_code',
        'referred_by_id', 'two_factor_enabled', 'two_factor_secret',
        'account_type', 'business_name',
    ]
    values = [fields[column] for column in columns]
    placeholders = ', '.join(['%s'] * len(columns))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_user (" + ", ".join(columns) + ") VALUES (" + placeholders + ")",
            values,
        )
        return cursor.lastrowid


def update_user(user_id, fields):
    if not fields:
        return 0
    if 'recovery_codes_hash' in fields:
        fields = dict(fields)
        fields['recovery_codes_hash'] = json.dumps(fields['recovery_codes_hash'])
    columns = list(fields.keys())
    set_sql = ", ".join(column + " = %s" for column in columns)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE wallet_user SET " + set_sql + " WHERE id = %s",
            [fields[column] for column in columns] + [user_id],
        )
        return cursor.rowcount


# =====================================================
# ROLES
# =====================================================

def get_role_by_name(role_name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_role WHERE role_name = %s LIMIT 1", [role_name])
        return _one(cursor)


def create_role(role_name):
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO wallet_role (role_name) VALUES (%s)", [role_name])
        return cursor.lastrowid


def user_role_exists(user_id, role_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM wallet_userrole WHERE user_id = %s AND role_id = %s",
            [user_id, role_id],
        )
        return cursor.fetchone()[0] > 0


def assign_user_role(user_id, role_id, assigned_at):
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_userrole (user_id, role_id, assigned_at) VALUES (%s, %s, %s)",
            [user_id, role_id, assigned_at],
        )
        return cursor.lastrowid


def get_user_roles(user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT r.role_name FROM wallet_userrole ur "
            "JOIN wallet_role r ON r.id = ur.role_id WHERE ur.user_id = %s",
            [user_id],
        )
        return _many(cursor)


# =====================================================
# CURRENCIES / RATES
# =====================================================

def get_currency(currency_name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_currency WHERE currency_name = %s LIMIT 1", [currency_name])
        return _one(cursor)


def currency_exists(currency_name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM wallet_currency WHERE currency_name = %s", [currency_name])
        return cursor.fetchone()[0] > 0


def currency_exists_with_type(currency_name, currency_type):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM wallet_currency WHERE currency_name = %s AND type = %s",
            [currency_name, currency_type],
        )
        return cursor.fetchone()[0] > 0


def get_currencies():
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_currency ORDER BY type, currency_name")
        return _many(cursor)


def save_currency(currency_name, currency_type, symbol):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT currency_name FROM wallet_currency WHERE currency_name = %s LIMIT 1",
            [currency_name],
        )
        exists = cursor.fetchone()
        if exists:
            cursor.execute(
                "UPDATE wallet_currency SET type = %s, symbol = %s WHERE currency_name = %s",
                [currency_type, symbol, currency_name],
            )
            return False
        cursor.execute(
            "INSERT INTO wallet_currency (currency_name, type, symbol) VALUES (%s, %s, %s)",
            [currency_name, currency_type, symbol],
        )
        return True


def get_exchange_rate(from_currency, to_currency):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_exchangerate WHERE from_curr_id = %s AND to_curr_id = %s LIMIT 1",
            [from_currency, to_currency],
        )
        return _one(cursor)


def get_exchange_rates():
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_exchangerate")
        return _many(cursor)


def save_exchange_rate(from_currency, to_currency, rate, last_updated):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rate_id FROM wallet_exchangerate WHERE from_curr_id = %s AND to_curr_id = %s LIMIT 1",
            [from_currency, to_currency],
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE wallet_exchangerate SET rate = %s, last_updated = %s WHERE rate_id = %s",
                [rate, last_updated, row[0]],
            )
            return row[0], False
        cursor.execute(
            "INSERT INTO wallet_exchangerate (from_curr_id, to_curr_id, rate, last_updated) VALUES (%s, %s, %s, %s)",
            [from_currency, to_currency, rate, last_updated],
        )
        return cursor.lastrowid, True


# =====================================================
# WALLETS / CRYPTO ADDRESSES
# =====================================================

def get_wallet(wallet_id, user_id=None):
    with connection.cursor() as cursor:
        if user_id is None:
            cursor.execute("SELECT * FROM wallet_wallet WHERE wallet_id = %s LIMIT 1", [wallet_id])
        else:
            cursor.execute(
                "SELECT * FROM wallet_wallet WHERE wallet_id = %s AND user_id = %s LIMIT 1",
                [wallet_id, user_id],
            )
        return _one(cursor)


def get_wallets_for_user(user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_wallet WHERE user_id = %s", [user_id])
        return _many(cursor)


def get_wallets_by_currency(user_id, currency_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_wallet WHERE user_id = %s AND currency_id = %s",
            [user_id, currency_id],
        )
        return _many(cursor)


def get_default_receive_wallet(user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_wallet WHERE user_id = %s AND is_default_receive = 1 LIMIT 1",
            [user_id],
        )
        return _one(cursor)


def lock_wallets_for_update(wallet_ids):
    """Row-lock one or more wallets with SELECT ... FOR UPDATE and return
    their *current, authoritative* rows as {wallet_id: row}.

    Must be called from inside a `db_transaction.atomic()` block (raw
    FOR UPDATE locks are only held/released with the surrounding
    transaction). This exists so every balance read-check-write in the
    app (send, shift, exchange fallback, requests, group payments,
    savings, payment links, scheduled payments, ...) reads the balance
    *after* acquiring the lock instead of relying on a value fetched
    earlier and possibly already stale -- without it, two concurrent
    requests touching the same wallet(s) can both read the same old
    balance, both pass the "sufficient balance" check, and both write,
    corrupting the balance (double-spend / lost update).

    Wallets are always locked in a fixed order (sorted by wallet_id)
    regardless of the order passed in, so two transfers moving money in
    opposite directions between the same two wallets always acquire
    their locks in the same order and can never deadlock each other.
    """
    ids = sorted({wallet_id for wallet_id in wallet_ids if wallet_id})
    if not ids:
        return {}
    placeholders = ', '.join(['%s'] * len(ids))
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_wallet WHERE wallet_id IN (" + placeholders + ") FOR UPDATE",
            ids,
        )
        rows = _many(cursor)
    return {row['wallet_id']: row for row in rows}


def create_wallet(fields):
    columns = list(fields.keys())
    placeholders = ', '.join(['%s'] * len(columns))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_wallet (" + ", ".join(columns) + ") VALUES (" + placeholders + ")",
            [fields[column] for column in columns],
        )
        return fields.get('wallet_id') or cursor.lastrowid


def update_wallet(wallet_id, fields):
    if not fields:
        return 0
    columns = list(fields.keys())
    set_sql = ", ".join(column + " = %s" for column in columns)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE wallet_wallet SET " + set_sql + " WHERE wallet_id = %s",
            [fields[column] for column in columns] + [wallet_id],
        )
        return cursor.rowcount


def freeze_wallets_for_user(user_id):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE wallet_wallet SET wallet_status = 'FROZEN' WHERE user_id = %s", [user_id])
        return cursor.rowcount


def delete_wallet(wallet_id):
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM wallet_wallet WHERE wallet_id = %s", [wallet_id])
        return cursor.rowcount


def unset_other_default_wallets(user_id, except_wallet_id=None):
    if except_wallet_id:
        return execute(
            "UPDATE wallet_wallet SET is_default_receive = %s "
            "WHERE user_id = %s AND is_default_receive = 1 AND wallet_id != %s",
            [False, user_id, except_wallet_id],
        )[0]
    return execute(
        "UPDATE wallet_wallet SET is_default_receive = %s "
        "WHERE user_id = %s AND is_default_receive = 1",
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
        "INSERT INTO wallet_auditlog "
        "(user_id, action, remarks, ip_address, timestamp) "
        "VALUES (%s, %s, %s, %s, %s)",
        [user_id, action, remarks, ip_address, timestamp],
    )[1]


def create_notification(user_id, message, notification_type, read_status, timestamp):
    return execute(
        "INSERT INTO wallet_notification "
        "(user_id, message, type, read_status, timestamp) "
        "VALUES (%s, %s, %s, %s, %s)",
        [user_id, message, notification_type, read_status, timestamp],
    )[1]


def get_notification_by_id(notification_id):
    return fetchone(
        "SELECT * FROM wallet_notification WHERE id = %s LIMIT 1",
        [notification_id],
    )


def update_user_fields(user_id, fields):
    statements = {
        "recovery_codes_hash": (
            "UPDATE wallet_user SET recovery_codes_hash = %s WHERE id = %s",
            "recovery_codes_hash",
        ),
        "transaction_pin_hash": (
            "UPDATE wallet_user SET transaction_pin_hash = %s WHERE id = %s",
            "transaction_pin_hash",
        ),
        "password": (
            "UPDATE wallet_user SET password = %s WHERE id = %s",
            "password",
        ),
        "account_type_business_name": (
            "UPDATE wallet_user SET account_type = %s, business_name = %s WHERE id = %s",
            "account_type_business_name",
        ),
        "deactivate": (
            "UPDATE wallet_user SET status = %s, is_active = %s WHERE id = %s",
            "deactivate",
        ),
        "fraud_flag": (
            "UPDATE wallet_user SET is_flagged = %s, flagged_reason = %s, flagged_at = %s WHERE id = %s",
            "fraud_flag",
        ),
        "clear_fraud_flag": (
            "UPDATE wallet_user SET is_flagged = %s, flagged_reason = %s, flagged_at = %s WHERE id = %s",
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
            "UPDATE wallet_user SET name = %s WHERE id = %s",
            [fields["name"], user_id],
        )[0]
    if keys == {"account_type"}:
        return execute(
            "UPDATE wallet_user SET account_type = %s WHERE id = %s",
            [fields["account_type"], user_id],
        )[0]
    if keys == {"business_name"}:
        return execute(
            "UPDATE wallet_user SET business_name = %s WHERE id = %s",
            [fields["business_name"], user_id],
        )[0]
    if keys == {"name", "account_type"}:
        return execute(
            "UPDATE wallet_user SET name = %s, account_type = %s WHERE id = %s",
            [fields["name"], fields["account_type"], user_id],
        )[0]
    if keys == {"name", "business_name"}:
        return execute(
            "UPDATE wallet_user SET name = %s, business_name = %s WHERE id = %s",
            [fields["name"], fields["business_name"], user_id],
        )[0]
    if keys == {"name", "account_type", "business_name"}:
        return execute(
            "UPDATE wallet_user SET name = %s, account_type = %s, "
            "business_name = %s WHERE id = %s",
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
        "INSERT INTO wallet_transaction "
        "(transaction_id, sender_wallet_id, receiver_wallet_id, transaction_type, "
        "amount, received_amount, exchange_rate, fee, status, category, date) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
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
        "SELECT * FROM wallet_transaction WHERE transaction_id = %s LIMIT 1",
        [transaction_id],
    )


def update_wallet_fields(wallet_id, fields):
    if set(fields) == {"balance"}:
        return execute(
            "UPDATE wallet_wallet SET balance = %s WHERE wallet_id = %s",
            [fields["balance"], wallet_id],
        )[0]
    if set(fields) == {"name"}:
        return execute(
            "UPDATE wallet_wallet SET name = %s WHERE wallet_id = %s",
            [fields["name"], wallet_id],
        )[0]
    if set(fields) == {"wallet_status"}:
        return execute(
            "UPDATE wallet_wallet SET wallet_status = %s WHERE wallet_id = %s",
            [fields["wallet_status"], wallet_id],
        )[0]
    if set(fields) == {"is_default_receive"}:
        return execute(
            "UPDATE wallet_wallet SET is_default_receive = %s WHERE wallet_id = %s",
            [fields["is_default_receive"], wallet_id],
        )[0]
    raise ValueError(f"Unsupported wallet update fields: {sorted(fields)}")


def get_wallet_by_id(wallet_id):
    return fetchone(
        "SELECT * FROM wallet_wallet WHERE wallet_id = %s LIMIT 1",
        [wallet_id],
    )


def get_wallet_by_user_id(wallet_id, user_id):
    return fetchone(
        "SELECT * FROM wallet_wallet "
        "WHERE wallet_id = %s AND user_id = %s LIMIT 1",
        [wallet_id, user_id],
    )


def get_default_wallet_by_user_id(user_id):
    return fetchone(
        "SELECT * FROM wallet_wallet "
        "WHERE user_id = %s AND is_default_receive = 1 LIMIT 1",
        [user_id],
    )


def get_currency_by_name(currency_name):
    return fetchone(
        "SELECT * FROM wallet_currency WHERE currency_name = %s LIMIT 1",
        [currency_name],
    )


def create_wallet(fields):
    return execute(
        "INSERT INTO wallet_wallet "
        "(wallet_id, user_id, currency_id, balance, is_default_receive, "
        "wallet_status, name, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        [
            fields["wallet_id"], fields["user_id"], fields["currency_id"],
            fields["balance"], fields["is_default_receive"],
            fields["wallet_status"], fields["name"], fields["created_at"],
        ],
    )[1]


def create_crypto_address(fields):
    return execute(
        "INSERT INTO wallet_cryptoaddress "
        "(address_id, wallet_id, blockchain, public_address) "
        "VALUES (%s, %s, %s, %s)",
        [
            fields["address_id"], fields["wallet_id"], fields["blockchain"],
            fields["public_address"],
        ],
    )[1]


def get_exchange_rate(from_currency, to_currency):
    return fetchone(
        "SELECT * FROM wallet_exchangerate "
        "WHERE from_curr_id = %s AND to_curr_id = %s LIMIT 1",
        [from_currency, to_currency],
    )


def list_exchange_rates():
    return fetchall("SELECT * FROM wallet_exchangerate")


def list_currencies():
    return fetchall(
        "SELECT * FROM wallet_currency ORDER BY type, currency_name"
    )


def get_user_by_role_name(role_name):
    return fetchone(
        "SELECT * FROM wallet_role WHERE role_name = %s LIMIT 1",
        [role_name],
    )


def create_role(role_name):
    return execute(
        "INSERT INTO wallet_role (role_name) VALUES (%s)",
        [role_name],
    )[1]


def user_role_exists(user_id, role_id):
    return scalar(
        "SELECT COUNT(*) FROM wallet_userrole "
        "WHERE user_id = %s AND role_id = %s",
        [user_id, role_id],
    ) > 0


def create_user_role(user_id, role_id, assigned_at):
    return execute(
        "INSERT INTO wallet_userrole (user_id, role_id, assigned_at) "
        "VALUES (%s, %s, %s)",
        [user_id, role_id, assigned_at],
    )[1]


def create_login_session(user_id, ip_address, device_info, login_time):
    return execute(
        "INSERT INTO wallet_loginsession "
        "(user_id, ip_address, device_info, login_time) VALUES (%s, %s, %s, %s)",
        [user_id, ip_address, device_info, login_time],
    )[1]


def get_user_by_id(user_id):
    return fetchone(
        "SELECT * FROM wallet_user WHERE id = %s LIMIT 1",
        [user_id],
    )


def get_user_by_email(email):
    return fetchone(
        "SELECT * FROM wallet_user WHERE LOWER(email) = LOWER(%s) LIMIT 1",
        [email],
    )


def get_user_by_phone(phone):
    return fetchone(
        "SELECT * FROM wallet_user WHERE phone = %s LIMIT 1",
        [phone],
    )


def list_bank_accounts(user_id):
    return fetchall(
        "SELECT * FROM wallet_bankaccount WHERE user_id = %s",
        [user_id],
    )


def get_bank_account_by_user_id(account_id, user_id):
    return fetchone(
        "SELECT * FROM wallet_bankaccount "
        "WHERE id = %s AND user_id = %s LIMIT 1",
        [account_id, user_id],
    )


def create_bank_account(fields):
    return execute(
        "INSERT INTO wallet_bankaccount "
        "(user_id, bank_name, account_number, created_at) VALUES (%s, %s, %s, %s)",
        [fields["user_id"], fields["bank_name"], fields["account_number"], fields["created_at"]],
    )[1]


def delete_bank_account(account_id):
    return execute("DELETE FROM wallet_bankaccount WHERE id = %s", [account_id])[0]


def get_kyc_by_user_id(user_id):
    return fetchone(
        "SELECT * FROM wallet_kyc WHERE user_id = %s LIMIT 1",
        [user_id],
    )


def get_kyc_by_id(kyc_id):
    return fetchone("SELECT * FROM wallet_kyc WHERE id = %s LIMIT 1", [kyc_id])


def create_kyc(fields):
    return execute(
        "INSERT INTO wallet_kyc "
        "(user_id, nid_number, passport_number, submission_date, verification_status, "
        "reviewed_by_id, reviewed_at, admin_remarks) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        [
            fields["user_id"], fields.get("nid_number"), fields.get("passport_number"),
            fields["submission_date"], fields["verification_status"],
            fields.get("reviewed_by_id"), fields.get("reviewed_at"),
            fields.get("admin_remarks"),
        ],
    )[1]


def update_kyc(kyc_id, fields):
    return execute(
        "UPDATE wallet_kyc SET nid_number = %s, passport_number = %s, "
        "verification_status = %s WHERE id = %s",
        [
            fields.get("nid_number"), fields.get("passport_number"),
            fields["verification_status"], kyc_id,
        ],
    )[0]


def list_wallets(user_id):
    return fetchall(
        "SELECT * FROM wallet_wallet WHERE user_id = %s",
        [user_id],
    )


def delete_wallet(wallet_id):
    return execute(
        "DELETE FROM wallet_wallet WHERE wallet_id = %s",
        [wallet_id],
    )[0]


def list_auto_save_goals(user_id):
    return fetchall(
        "SELECT * FROM wallet_savingsgoal "
        "WHERE user_id = %s AND is_active = 1 AND auto_save_percent > 0",
        [user_id],
    )


def list_login_sessions(user_id):
    return fetchall(
        "SELECT * FROM wallet_loginsession "
        "WHERE user_id = %s ORDER BY login_time DESC",
        [user_id],
    )


def list_notifications(user_id):
    return fetchall(
        "SELECT * FROM wallet_notification "
        "WHERE user_id = %s ORDER BY timestamp DESC",
        [user_id],
    )


def get_notification_for_user(notification_id, user_id):
    return fetchone(
        "SELECT * FROM wallet_notification "
        "WHERE id = %s AND user_id = %s LIMIT 1",
        [notification_id, user_id],
    )


def mark_notification_read(notification_id):
    return execute(
        "UPDATE wallet_notification SET read_status = %s WHERE id = %s",
        [True, notification_id],
    )[0]


def list_kyc(status_filter=None):
    if status_filter is None:
        return fetchall(
            "SELECT * FROM wallet_kyc ORDER BY submission_date"
        )
    return fetchall(
        "SELECT * FROM wallet_kyc "
        "WHERE verification_status = %s ORDER BY submission_date",
        [status_filter],
    )


def approve_kyc(kyc_id, reviewed_by_id, reviewed_at, admin_remarks):
    return execute(
        "UPDATE wallet_kyc SET verification_status = %s, reviewed_by_id = %s, "
        "reviewed_at = %s, admin_remarks = %s WHERE id = %s",
        ["APPROVED", reviewed_by_id, reviewed_at, admin_remarks, kyc_id],
    )[0]


def reject_kyc(kyc_id, reviewed_by_id, reviewed_at, admin_remarks):
    return execute(
        "UPDATE wallet_kyc SET verification_status = %s, reviewed_by_id = %s, "
        "reviewed_at = %s, admin_remarks = %s WHERE id = %s",
        ["REJECTED", reviewed_by_id, reviewed_at, admin_remarks, kyc_id],
    )[0]


def count_users():
    return scalar("SELECT COUNT(*) FROM wallet_user") or 0


def count_active_users():
    return scalar(
        "SELECT COUNT(*) FROM wallet_user WHERE status = %s",
        ["ACTIVE"],
    ) or 0


def count_flagged_users():
    return scalar(
        "SELECT COUNT(*) FROM wallet_user WHERE is_flagged = 1"
    ) or 0


def count_pending_kyc():
    return scalar(
        "SELECT COUNT(*) FROM wallet_kyc WHERE verification_status = %s",
        ["PENDING"],
    ) or 0


def count_transactions():
    return scalar("SELECT COUNT(*) FROM wallet_transaction") or 0


def count_wallets():
    return scalar("SELECT COUNT(*) FROM wallet_wallet") or 0


def transaction_volume_by_currency():
    return fetchall(
        "SELECT sw.currency_id AS currency, SUM(t.amount) AS total, "
        "COUNT(t.transaction_id) AS count "
        "FROM wallet_transaction t "
        "JOIN wallet_wallet sw ON sw.wallet_id = t.sender_wallet_id "
        "GROUP BY sw.currency_id ORDER BY total DESC"
    )


def transaction_volume_by_day(since):
    return fetchall(
        "SELECT DATE(date) AS day, COUNT(transaction_id) AS count, "
        "SUM(amount) AS volume FROM wallet_transaction "
        "WHERE date >= %s GROUP BY DATE(date) ORDER BY day",
        [since],
    )


def list_flagged_users():
    return fetchall(
        "SELECT * FROM wallet_user WHERE is_flagged = 1 "
        "ORDER BY flagged_at DESC"
    )


def list_scheduled_payments(user_id):
    return fetchall(
        "SELECT * FROM wallet_scheduledpayment "
        "WHERE owner_id = %s ORDER BY next_run_at",
        [user_id],
    )


def user_exists_by_phone(phone):
    return scalar(
        "SELECT COUNT(*) FROM wallet_user WHERE phone = %s",
        [phone],
    ) > 0


def create_scheduled_payment(fields):
    return execute(
        "INSERT INTO wallet_scheduledpayment "
        "(schedule_id, owner_id, sender_wallet_id, recipient_phone, recipient_wallet_id, "
        "amount, note, frequency, next_run_at, last_run_at, status, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
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
        "SELECT * FROM wallet_scheduledpayment "
        "WHERE schedule_id = %s AND owner_id = %s LIMIT 1",
        [schedule_id, owner_id],
    )


def update_scheduled_payment_status(schedule_id, status):
    return execute(
        "UPDATE wallet_scheduledpayment SET status = %s WHERE schedule_id = %s",
        [status, schedule_id],
    )[0]


def get_money_request(request_id, payer_id=None):
    if payer_id is None:
        return fetchone(
            "SELECT * FROM wallet_moneyrequest WHERE request_id = %s LIMIT 1",
            [request_id],
        )
    return fetchone(
        "SELECT * FROM wallet_moneyrequest "
        "WHERE request_id = %s AND payer_id = %s LIMIT 1",
        [request_id, payer_id],
    )


def list_money_requests(user_id):
    return fetchall(
        "SELECT * FROM wallet_moneyrequest "
        "WHERE requester_id = %s OR payer_id = %s ORDER BY created_at DESC",
        [user_id, user_id],
    )


def create_money_request(fields):
    return execute(
        "INSERT INTO wallet_moneyrequest "
        "(request_id, requester_id, requester_wallet_id, payer_id, amount, note, "
        "status, transaction_id, created_at, responded_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [
            fields["request_id"], fields["requester_id"], fields["requester_wallet_id"],
            fields["payer_id"], fields["amount"], fields.get("note", ""),
            fields["status"], fields.get("transaction_id"), fields["created_at"],
            fields.get("responded_at"),
        ],
    )[1]


def update_money_request(request_id, status, transaction_id=None, responded_at=None):
    return execute(
        "UPDATE wallet_moneyrequest SET status = %s, transaction_id = %s, "
        "responded_at = %s WHERE request_id = %s",
        [status, transaction_id, responded_at, request_id],
    )[0]


def get_group_payment(group_payment_id):
    return fetchone(
        "SELECT * FROM wallet_grouppayment WHERE group_payment_id = %s LIMIT 1",
        [group_payment_id],
    )


def list_group_payment_participants(group_payment_id):
    return fetchall(
        "SELECT * FROM wallet_grouppaymentparticipant "
        "WHERE group_payment_id = %s",
        [group_payment_id],
    )


def list_group_payments_for_user(user_id):
    return fetchall(
        "SELECT DISTINCT gp.group_payment_id FROM wallet_grouppayment gp "
        "LEFT JOIN wallet_grouppaymentparticipant p "
        "ON p.group_payment_id = gp.group_payment_id "
        "WHERE gp.organizer_id = %s OR p.user_id = %s "
        "ORDER BY gp.created_at DESC",
        [user_id, user_id],
    )


def create_group_payment(fields):
    return execute(
        "INSERT INTO wallet_grouppayment "
        "(group_payment_id, organizer_id, receiver_wallet_id, title, total_amount, "
        "status, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        [
            fields["group_payment_id"], fields["organizer_id"],
            fields["receiver_wallet_id"], fields["title"],
            fields["total_amount"], fields["status"], fields["created_at"],
        ],
    )[1]


def get_group_payment_participant(group_payment_id, user_id):
    return fetchone(
        "SELECT * FROM wallet_grouppaymentparticipant "
        "WHERE group_payment_id = %s AND user_id = %s LIMIT 1",
        [group_payment_id, user_id],
    )


def update_group_payment_participant(participant_id, fields):
    if set(fields) == {"share_amount"}:
        return execute(
            "UPDATE wallet_grouppaymentparticipant SET share_amount = %s WHERE id = %s",
            [fields["share_amount"], participant_id],
        )[0]
    return execute(
        "UPDATE wallet_grouppaymentparticipant SET status = %s, "
        "transaction_id = %s, paid_at = %s WHERE id = %s",
        [fields["status"], fields["transaction_id"], fields["paid_at"], participant_id],
    )[0]


def create_group_payment_participant(fields):
    return execute(
        "INSERT INTO wallet_grouppaymentparticipant "
        "(group_payment_id, user_id, share_amount, status, transaction_id, paid_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        [
            fields["group_payment_id"], fields["user_id"], fields["share_amount"],
            fields["status"], fields.get("transaction_id"), fields.get("paid_at"),
        ],
    )[1]


def update_group_payment(group_payment_id, fields):
    return execute(
        "UPDATE wallet_grouppayment SET status = %s WHERE group_payment_id = %s",
        [fields["status"], group_payment_id],
    )[0]


def get_savings_goal(goal_id, user_id=None):
    if user_id is None:
        return fetchone(
            "SELECT * FROM wallet_savingsgoal WHERE goal_id = %s LIMIT 1",
            [goal_id],
        )
    return fetchone(
        "SELECT * FROM wallet_savingsgoal "
        "WHERE goal_id = %s AND user_id = %s LIMIT 1",
        [goal_id, user_id],
    )


def list_savings_goals(user_id):
    return fetchall(
        "SELECT * FROM wallet_savingsgoal WHERE user_id = %s",
        [user_id],
    )


def create_savings_goal(fields):
    return execute(
        "INSERT INTO wallet_savingsgoal "
        "(goal_id, user_id, savings_wallet_id, name, target_amount, deadline, "
        "auto_save_percent, is_active, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [
            fields["goal_id"], fields["user_id"], fields["savings_wallet_id"],
            fields["name"], fields["target_amount"], fields.get("deadline"),
            fields.get("auto_save_percent", 0), fields["is_active"],
            fields["created_at"],
        ],
    )[1]


def update_savings_goal(goal_id, is_active):
    return execute(
        "UPDATE wallet_savingsgoal SET is_active = %s WHERE goal_id = %s",
        [is_active, goal_id],
    )[0]


def list_price_alerts(user_id):
    return fetchall(
        "SELECT * FROM wallet_pricealert WHERE user_id = %s",
        [user_id],
    )


def create_price_alert(fields):
    return execute(
        "INSERT INTO wallet_pricealert "
        "(alert_id, user_id, from_currency, to_currency, threshold_rate, "
        "is_active, triggered_at, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        [
            fields["alert_id"], fields["user_id"], fields["from_currency"],
            fields["to_currency"], fields["threshold_rate"], fields["is_active"],
            fields.get("triggered_at"), fields["created_at"],
        ],
    )[1]


def get_price_alert(alert_id):
    return fetchone(
        "SELECT * FROM wallet_pricealert WHERE alert_id = %s LIMIT 1",
        [alert_id],
    )


def delete_price_alert(alert_id):
    return execute(
        "DELETE FROM wallet_pricealert WHERE alert_id = %s",
        [alert_id],
    )[0]


def get_payment_link(link_id, active_only=False):
    if active_only:
        return fetchone(
            "SELECT * FROM wallet_paymentlink "
            "WHERE link_id = %s AND is_active = 1 LIMIT 1",
            [link_id],
        )
    return fetchone(
        "SELECT * FROM wallet_paymentlink WHERE link_id = %s LIMIT 1",
        [link_id],
    )


def list_payment_links(merchant_id):
    return fetchall(
        "SELECT * FROM wallet_paymentlink "
        "WHERE merchant_id = %s ORDER BY created_at DESC",
        [merchant_id],
    )


def create_payment_link(fields):
    return execute(
        "INSERT INTO wallet_paymentlink "
        "(link_id, merchant_id, receiving_wallet_id, title, amount, is_active, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        [
            fields["link_id"], fields["merchant_id"], fields["receiving_wallet_id"],
            fields["title"], fields.get("amount"), fields["is_active"],
            fields["created_at"],
        ],
    )[1]


def sent_transactions_since(user_id, since):
    return fetchall(
        "SELECT t.amount, w.currency_id FROM wallet_transaction t "
        "JOIN wallet_wallet w ON w.wallet_id = t.sender_wallet_id "
        "WHERE w.user_id = %s AND t.transaction_type = 'SEND' AND t.date >= %s",
        [user_id, since],
    )


def count_recent_sends(user_id, since):
    return scalar(
        "SELECT COUNT(*) FROM wallet_transaction "
        "WHERE sender_wallet_id IN "
        "(SELECT wallet_id FROM wallet_wallet WHERE user_id = %s) "
        "AND transaction_type IN ('SEND', 'SHIFT') AND date >= %s",
        [user_id, since],
    ) or 0


def list_transactions_for_user(user_id, currency=None):
    sql = (
        "SELECT t.*, "
        "sw.wallet_id AS sw_wallet_id, sw.name AS sw_name, "
        "sw.currency_id AS sw_currency_id, sw.user_id AS sw_user_id, su.phone AS su_phone, "
        "rw.wallet_id AS rw_wallet_id, rw.name AS rw_name, "
        "rw.currency_id AS rw_currency_id, rw.user_id AS rw_user_id, ru.phone AS ru_phone "
        "FROM wallet_transaction t "
        "LEFT JOIN wallet_wallet sw ON sw.wallet_id = t.sender_wallet_id "
        "LEFT JOIN wallet_user su ON su.id = sw.user_id "
        "LEFT JOIN wallet_wallet rw ON rw.wallet_id = t.receiver_wallet_id "
        "LEFT JOIN wallet_user ru ON ru.id = rw.user_id "
        "WHERE (sw.user_id = %s OR rw.user_id = %s)"
    )
    params = [user_id, user_id]
    if currency:
        sql += " AND (sw.currency_id = %s OR rw.currency_id = %s)"
        params.extend([currency, currency])
    sql += " ORDER BY t.date DESC"
    return fetchall(sql, params)


def deactivate_wallets_for_user(user_id):
    return execute(
        "UPDATE wallet_wallet SET wallet_status = %s WHERE user_id = %s",
        ["FROZEN", user_id],
    )[0]
