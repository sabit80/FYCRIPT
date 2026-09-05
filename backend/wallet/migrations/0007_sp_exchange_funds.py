from django.db import migrations


PROCEDURE_SQL = """
CREATE PROCEDURE sp_exchange_funds(
    IN p_from_wallet    VARCHAR(40),
    IN p_to_wallet      VARCHAR(40),
    IN p_amount         DECIMAL(24,8),
    IN p_rate           DECIMAL(24,8),
    IN p_transaction_id VARCHAR(40)
)
proc_body: BEGIN
    DECLARE v_from_balance DECIMAL(24,8);
    DECLARE v_to_balance DECIMAL(24,8);
    DECLARE v_converted DECIMAL(24,8);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT balance INTO v_from_balance
    FROM wallet_wallet WHERE wallet_id = p_from_wallet FOR UPDATE;

    SELECT balance INTO v_to_balance
    FROM wallet_wallet WHERE wallet_id = p_to_wallet FOR UPDATE;

    IF v_from_balance < p_amount THEN
        ROLLBACK;
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Insufficient balance';
        LEAVE proc_body;
    END IF;

    SET v_converted = p_amount * p_rate;

    UPDATE wallet_wallet SET balance = balance - p_amount WHERE wallet_id = p_from_wallet;
    UPDATE wallet_wallet SET balance = balance + v_converted WHERE wallet_id = p_to_wallet;

    INSERT INTO wallet_transaction (
        transaction_id, sender_wallet_id, receiver_wallet_id,
        transaction_type, amount, received_amount, exchange_rate,
        fee, status, category, date
    ) VALUES (
        p_transaction_id, p_from_wallet, p_to_wallet,
        'EXCHANGE', p_amount, v_converted, p_rate,
        0, 'COMPLETED', '', NOW(6)
    );

    COMMIT;
END
"""


class Migration(migrations.Migration):
    """
    database/schema.sql's sp_exchange_funds was written against that
    file's own non-prefixed table names (`wallet`, `transaction`) and
    was never actually created against THIS project's real,
    Django-migrated tables (`wallet_wallet`, `wallet_transaction`) —
    ExchangeView's cursor.callproc('sp_exchange_funds', ...) would
    fail with "PROCEDURE ... does not exist" on a fresh `manage.py
    migrate`. This migration installs the same procedure, pointed at
    the actual table names, so ExchangeView works. See
    MIGRATION_NOTES.md.
    """

    dependencies = [
        ('wallet', '0006_blacklisted_token'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "DROP PROCEDURE IF EXISTS sp_exchange_funds;",
                PROCEDURE_SQL,
            ],
            reverse_sql="DROP PROCEDURE IF EXISTS sp_exchange_funds;",
        ),
    ]
