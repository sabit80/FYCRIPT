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
    with connection.cursor() as cursor:
        if except_wallet_id:
            cursor.execute(
                "UPDATE wallet_wallet SET is_default_receive = 0 "
                "WHERE user_id = %s AND is_default_receive = 1 AND wallet_id != %s",
                [user_id, except_wallet_id],
            )
        else:
            cursor.execute(
                "UPDATE wallet_wallet SET is_default_receive = 0 "
                "WHERE user_id = %s AND is_default_receive = 1",
                [user_id],
            )
        return cursor.rowcount


def create_crypto_address(address_id, wallet_id, blockchain, public_address):
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_cryptoaddress "
            "(address_id, wallet_id, blockchain, public_address) VALUES (%s, %s, %s, %s)",
            [address_id, wallet_id, blockchain, public_address],
        )
        return address_id


# =====================================================
# BANK ACCOUNTS
# =====================================================

def get_bank_accounts(user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_bankaccount WHERE user_id = %s", [user_id])
        return _many(cursor)


def get_bank_account(bank_account_id, user_id=None):
    with connection.cursor() as cursor:
        if user_id is None:
            cursor.execute("SELECT * FROM wallet_bankaccount WHERE id = %s LIMIT 1", [bank_account_id])
        else:
            cursor.execute(
                "SELECT * FROM wallet_bankaccount WHERE id = %s AND user_id = %s LIMIT 1",
                [bank_account_id, user_id],
            )
        return _one(cursor)


def create_bank_account(user_id, fields):
    fields = dict(fields)
    fields['user_id'] = user_id
    columns = list(fields.keys())
    placeholders = ', '.join(['%s'] * len(columns))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_bankaccount (" + ", ".join(columns) + ") VALUES (" + placeholders + ")",
            [fields[column] for column in columns],
        )
        return cursor.lastrowid


def delete_bank_account(bank_account_id):
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM wallet_bankaccount WHERE id = %s", [bank_account_id])
        return cursor.rowcount


# =====================================================
# TRANSACTIONS
# =====================================================

def create_transaction(fields):
    columns = list(fields.keys())
    placeholders = ', '.join(['%s'] * len(columns))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_transaction (" + ", ".join(columns) + ") VALUES (" + placeholders + ")",
            [fields[column] for column in columns],
        )
        return fields.get('transaction_id') or cursor.lastrowid


def get_transaction(transaction_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_transaction WHERE transaction_id = %s LIMIT 1",
            [transaction_id],
        )
        return _one(cursor)


def get_user_transactions(user_id, currency=None):
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
        params += [currency, currency]
    sql += " ORDER BY t.date DESC"
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return _many(cursor)


def get_send_totals(user_id, start_time):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT t.amount, w.currency_id FROM wallet_transaction t "
            "JOIN wallet_wallet w ON w.wallet_id = t.sender_wallet_id "
            "WHERE w.user_id = %s AND t.transaction_type = 'SEND' AND t.date >= %s",
            [user_id, start_time],
        )
        return _many(cursor)


def count_recent_sends(user_id, start_time):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM wallet_transaction "
            "WHERE sender_wallet_id IN (SELECT wallet_id FROM wallet_wallet WHERE user_id = %s) "
            "AND transaction_type IN ('SEND', 'SHIFT') AND date >= %s",
            [user_id, start_time],
        )
        return cursor.fetchone()[0]


# =====================================================
# NOTIFICATIONS / AUDIT / SESSIONS
# =====================================================

def create_notification(user_id, message, notification_type, timestamp):
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_notification "
            "(user_id, message, type, read_status, timestamp) VALUES (%s, %s, %s, 0, %s)",
            [user_id, message, notification_type, timestamp],
        )
        return cursor.lastrowid


def get_notification(notification_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_notification WHERE id = %s LIMIT 1", [notification_id])
        return _one(cursor)


def create_audit_log(user_id, action, remarks, ip_address, timestamp):
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_auditlog (user_id, action, remarks, ip_address, timestamp) "
            "VALUES (%s, %s, %s, %s, %s)",
            [user_id, action, remarks, ip_address, timestamp],
        )
        return cursor.lastrowid


def create_login_session(user_id, ip_address, device_info, login_time):
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_loginsession (user_id, ip_address, device_info, login_time) "
            "VALUES (%s, %s, %s, %s)",
            [user_id, ip_address, device_info, login_time],
        )
        return cursor.lastrowid


def get_login_sessions(user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_loginsession WHERE user_id = %s", [user_id])
        return _many(cursor)


def get_notifications(user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_notification WHERE user_id = %s ORDER BY timestamp DESC",
            [user_id],
        )
        return _many(cursor)


def mark_notification_read(notification_id, user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE wallet_notification SET read_status = 1 WHERE id = %s AND user_id = %s",
            [notification_id, user_id],
        )
        return cursor.rowcount


def is_blacklisted_token(jti):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM wallet_blacklisted_token WHERE jti = %s", [jti])
        return cursor.fetchone()[0] > 0


# =====================================================
# KYC
# =====================================================

def get_kyc_by_user(user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_kyc WHERE user_id = %s LIMIT 1", [user_id])
        return _one(cursor)


def get_all_kyc():
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_kyc ORDER BY submission_date DESC")
        return _many(cursor)


def get_kyc_by_id(kyc_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_kyc WHERE id = %s LIMIT 1", [kyc_id])
        return _one(cursor)


def update_kyc(kyc_id, fields):
    columns = list(fields.keys())
    set_sql = ", ".join(column + " = %s" for column in columns)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE wallet_kyc SET " + set_sql + " WHERE id = %s",
            [fields[column] for column in columns] + [kyc_id],
        )
        return cursor.rowcount


# =====================================================
# SCHEDULED PAYMENTS
# =====================================================

def get_due_scheduled_payments(now):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_scheduledpayment WHERE status = 'ACTIVE' AND next_run_at <= %s",
            [now],
        )
        return _many(cursor)


def get_scheduled_payment(schedule_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_scheduledpayment WHERE schedule_id = %s LIMIT 1", [schedule_id]
        )
        return _one(cursor)


def update_scheduled_payment(schedule_id, fields):
    columns = list(fields.keys())
    set_sql = ", ".join(column + " = %s" for column in columns)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE wallet_scheduledpayment SET " + set_sql + " WHERE schedule_id = %s",
            [fields[column] for column in columns] + [schedule_id],
        )
        return cursor.rowcount


def get_active_auto_save_goals(user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_savingsgoal "
            "WHERE user_id = %s AND is_active = 1 AND auto_save_percent > 0",
            [user_id],
        )
        return _many(cursor)


# =====================================================
# MONEY REQUESTS
# =====================================================

def get_money_request(request_id, payer_id=None):
    with connection.cursor() as cursor:
        if payer_id is None:
            cursor.execute("SELECT * FROM wallet_moneyrequest WHERE request_id = %s LIMIT 1", [request_id])
        else:
            cursor.execute(
                "SELECT * FROM wallet_moneyrequest WHERE request_id = %s AND payer_id = %s LIMIT 1",
                [request_id, payer_id],
            )
        return _one(cursor)


def get_money_requests_for_user(user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_moneyrequest "
            "WHERE requester_id = %s OR payer_id = %s ORDER BY created_at DESC",
            [user_id, user_id],
        )
        return _many(cursor)


def create_money_request(fields):
    columns = list(fields.keys())
    placeholders = ', '.join(['%s'] * len(columns))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_moneyrequest (" + ", ".join(columns) + ") VALUES (" + placeholders + ")",
            [fields[column] for column in columns],
        )
        return fields.get('request_id') or cursor.lastrowid


def update_money_request(request_id, fields):
    columns = list(fields.keys())
    set_sql = ", ".join(column + " = %s" for column in columns)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE wallet_moneyrequest SET " + set_sql + " WHERE request_id = %s",
            [fields[column] for column in columns] + [request_id],
        )
        return cursor.rowcount


# =====================================================
# GROUP PAYMENTS
# =====================================================

def get_group_payment(group_payment_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_grouppayment WHERE group_payment_id = %s LIMIT 1",
            [group_payment_id],
        )
        return _one(cursor)


def get_group_payment_participants(group_payment_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_grouppaymentparticipant WHERE group_payment_id = %s",
            [group_payment_id],
        )
        return _many(cursor)


def get_group_payment_participant(group_payment_id, user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_grouppaymentparticipant "
            "WHERE group_payment_id = %s AND user_id = %s LIMIT 1",
            [group_payment_id, user_id],
        )
        return _one(cursor)


def create_group_payment(fields):
    columns = list(fields.keys())
    placeholders = ', '.join(['%s'] * len(columns))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_grouppayment (" + ", ".join(columns) + ") VALUES (" + placeholders + ")",
            [fields[column] for column in columns],
        )
        return fields.get('group_payment_id') or cursor.lastrowid


def update_group_payment(group_payment_id, fields):
    columns = list(fields.keys())
    set_sql = ", ".join(column + " = %s" for column in columns)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE wallet_grouppayment SET " + set_sql + " WHERE group_payment_id = %s",
            [fields[column] for column in columns] + [group_payment_id],
        )
        return cursor.rowcount


def update_group_payment_participant(participant_id, fields):
    columns = list(fields.keys())
    set_sql = ", ".join(column + " = %s" for column in columns)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE wallet_grouppaymentparticipant SET " + set_sql + " WHERE id = %s",
            [fields[column] for column in columns] + [participant_id],
        )
        return cursor.rowcount


def group_payment_has_unpaid_participants(group_payment_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM wallet_grouppaymentparticipant "
            "WHERE group_payment_id = %s AND status != 'PAID'",
            [group_payment_id],
        )
        return cursor.fetchone()[0] > 0


def create_group_payment_participant(fields):
    columns = list(fields.keys())
    placeholders = ', '.join(['%s'] * len(columns))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_grouppaymentparticipant (" + ", ".join(columns) + ") VALUES (" + placeholders + ")",
            [fields[column] for column in columns],
        )
        return cursor.lastrowid


# =====================================================
# SAVINGS / PRICE ALERTS / PAYMENT LINKS
# =====================================================

def get_savings_goal(goal_id, user_id=None):
    with connection.cursor() as cursor:
        if user_id is None:
            cursor.execute("SELECT * FROM wallet_savingsgoal WHERE goal_id = %s LIMIT 1", [goal_id])
        else:
            cursor.execute(
                "SELECT * FROM wallet_savingsgoal WHERE goal_id = %s AND user_id = %s LIMIT 1",
                [goal_id, user_id],
            )
        return _one(cursor)


def get_savings_goals(user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_savingsgoal WHERE user_id = %s", [user_id])
        return _many(cursor)


def create_savings_goal(fields):
    columns = list(fields.keys())
    placeholders = ', '.join(['%s'] * len(columns))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_savingsgoal (" + ", ".join(columns) + ") VALUES (" + placeholders + ")",
            [fields[column] for column in columns],
        )
        return fields.get('goal_id') or cursor.lastrowid


def update_savings_goal(goal_id, fields):
    columns = list(fields.keys())
    set_sql = ", ".join(column + " = %s" for column in columns)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE wallet_savingsgoal SET " + set_sql + " WHERE goal_id = %s",
            [fields[column] for column in columns] + [goal_id],
        )
        return cursor.rowcount


def get_price_alerts(user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_pricealert WHERE user_id = %s", [user_id])
        return _many(cursor)


def get_price_alert(alert_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_pricealert WHERE alert_id = %s LIMIT 1", [alert_id])
        return _one(cursor)


def create_price_alert(fields):
    columns = list(fields.keys())
    placeholders = ', '.join(['%s'] * len(columns))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_pricealert (" + ", ".join(columns) + ") VALUES (" + placeholders + ")",
            [fields[column] for column in columns],
        )
        return fields.get('alert_id') or cursor.lastrowid


def update_price_alert(alert_id, fields):
    columns = list(fields.keys())
    set_sql = ", ".join(column + " = %s" for column in columns)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE wallet_pricealert SET " + set_sql + " WHERE alert_id = %s",
            [fields[column] for column in columns] + [alert_id],
        )
        return cursor.rowcount


def delete_price_alert(alert_id):
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM wallet_pricealert WHERE alert_id = %s", [alert_id])
        return cursor.rowcount


def get_active_price_alerts():
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_pricealert WHERE is_active = 1 AND triggered_at IS NULL")
        return _many(cursor)


def get_payment_link(link_id, active_only=False):
    with connection.cursor() as cursor:
        if active_only:
            cursor.execute(
                "SELECT * FROM wallet_paymentlink WHERE link_id = %s AND is_active = 1 LIMIT 1",
                [link_id],
            )
        else:
            cursor.execute("SELECT * FROM wallet_paymentlink WHERE link_id = %s LIMIT 1", [link_id])
        return _one(cursor)


def get_payment_links_for_merchant(user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_paymentlink WHERE merchant_id = %s ORDER BY created_at DESC",
            [user_id],
        )
        return _many(cursor)


def create_payment_link(fields):
    columns = list(fields.keys())
    placeholders = ', '.join(['%s'] * len(columns))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_paymentlink (" + ", ".join(columns) + ") VALUES (" + placeholders + ")",
            [fields[column] for column in columns],
        )
        return fields.get('link_id') or cursor.lastrowid


# =====================================================
# REPORTS / ADMIN QUERIES
# =====================================================

def get_transaction_report_rows():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT sw.currency_id AS currency, SUM(t.amount) AS total, "
            "COUNT(t.transaction_id) AS count "
            "FROM wallet_transaction t "
            "JOIN wallet_wallet sw ON sw.wallet_id = t.sender_wallet_id "
            "GROUP BY sw.currency_id ORDER BY total DESC"
        )
        return _many(cursor)


def get_daily_transaction_report(since):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DATE(date) AS day, COUNT(transaction_id) AS count, "
            "SUM(amount) AS volume FROM wallet_transaction "
            "WHERE date >= %s GROUP BY DATE(date) ORDER BY day",
            [since],
        )
        return _many(cursor)


def count_users():
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM wallet_user")
        return cursor.fetchone()[0]


def count_active_users():
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM wallet_user WHERE status = %s", ['ACTIVE'])
        return cursor.fetchone()[0]


def count_flagged_users():
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM wallet_user WHERE is_flagged = 1")
        return cursor.fetchone()[0]


def count_pending_kyc():
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM wallet_kyc WHERE verification_status = %s", ['PENDING'])
        return cursor.fetchone()[0]


def count_transactions():
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM wallet_transaction")
        return cursor.fetchone()[0]


def count_wallets():
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM wallet_wallet")
        return cursor.fetchone()[0]


def get_flagged_users():
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_user WHERE is_flagged = 1 ORDER BY flagged_at DESC")
        return _many(cursor)


def get_kyc_list(order_by_submission=True):
    with connection.cursor() as cursor:
        sql = "SELECT * FROM wallet_kyc"
        if order_by_submission:
            sql += " ORDER BY submission_date"
        cursor.execute(sql)
        return _many(cursor)


def get_group_payment_ids_for_user(user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT gp.group_payment_id FROM wallet_grouppayment gp "
            "LEFT JOIN wallet_grouppaymentparticipant p ON p.group_payment_id = gp.group_payment_id "
            "WHERE gp.organizer_id = %s OR p.user_id = %s ORDER BY gp.created_at DESC",
            [user_id, user_id],
        )
        return _many(cursor)


def update_flagged_user(user_id, fields):
    columns = list(fields.keys())
    set_sql = ", ".join(column + " = %s" for column in columns)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE wallet_user SET " + set_sql + " WHERE id = %s",
            [fields[column] for column in columns] + [user_id],
        )
        return cursor.rowcount


def get_user_by_id_with_uid(user_id):
    return get_user_by_id(user_id)


# =====================================================
# EXPLICIT UPDATE/CREATE FUNCTIONS FOR FEATURE TABLES
# =====================================================

def create_scheduled_payment(fields):
    columns = list(fields.keys())
    placeholders = ', '.join(['%s'] * len(columns))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_scheduledpayment (" + ", ".join(columns) + ") VALUES (" + placeholders + ")",
            [fields[column] for column in columns],
        )
        return fields.get('schedule_id') or cursor.lastrowid


def get_scheduled_payment_for_owner(schedule_id, owner_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_scheduledpayment WHERE schedule_id = %s AND owner_id = %s LIMIT 1",
            [schedule_id, owner_id],
        )
        return _one(cursor)


def get_scheduled_payments_for_owner(owner_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM wallet_scheduledpayment WHERE owner_id = %s ORDER BY next_run_at",
            [owner_id],
        )
        return _many(cursor)


def create_kyc(fields):
    columns = list(fields.keys())
    placeholders = ', '.join(['%s'] * len(columns))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO wallet_kyc (" + ", ".join(columns) + ") VALUES (" + placeholders + ")",
            [fields[column] for column in columns],
        )
        return cursor.lastrowid


# Additional explicit functions used by the remaining API features.

def get_exchange_rates_for_display():
    return get_exchange_rates()

def get_bank_account_for_user(bank_account_id, user_id):
    return get_bank_account(bank_account_id, user_id)

def get_kyc_list_for_admin():
    return get_kyc_list(True)

def get_notification_for_user(notification_id, user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM wallet_notification WHERE id = %s AND user_id = %s LIMIT 1", [notification_id, user_id])
        return _one(cursor)

def get_wallets_for_user_simple(user_id):
    return get_wallets_for_user(user_id)

def get_savings_goal_for_user(goal_id, user_id):
    return get_savings_goal(goal_id, user_id)

def get_payment_link_active(link_id):
    return get_payment_link(link_id, True)

def update_money_request_fields(request_id, fields):
    # The MoneyRequest fields used by the application are fixed here.
    allowed = {
        'status', 'transaction_id', 'responded_at', 'amount', 'note'
    }
    values = {k: v for k, v in fields.items() if k in allowed}
    if not values:
        return 0
    if set(values) == {'status', 'transaction_id', 'responded_at'}:
        sql = "UPDATE wallet_moneyrequest SET status = %s, transaction_id = %s, responded_at = %s WHERE request_id = %s"
        params = [values['status'], values['transaction_id'], values['responded_at'], request_id]
    elif set(values) == {'status'}:
        sql = "UPDATE wallet_moneyrequest SET status = %s WHERE request_id = %s"
        params = [values['status'], request_id]
    else:
        columns = list(values.keys())
        sql = "UPDATE wallet_moneyrequest SET " + ', '.join(column + " = %s" for column in columns) + " WHERE request_id = %s"
        params = [values[column] for column in columns] + [request_id]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.rowcount

def get_kyc_list_by_status(status_filter):
    with connection.cursor() as cursor:
        if status_filter == 'ALL':
            cursor.execute("SELECT * FROM wallet_kyc ORDER BY submission_date")
        else:
            cursor.execute(
                "SELECT * FROM wallet_kyc WHERE verification_status = %s ORDER BY submission_date",
                [status_filter],
            )
        return _many(cursor)

def get_price_alert_rate(from_currency, to_currency):
    return get_exchange_rate(from_currency, to_currency)

def create_user_role(user_id, role_id, assigned_at):
    return assign_user_role(user_id, role_id, assigned_at)
