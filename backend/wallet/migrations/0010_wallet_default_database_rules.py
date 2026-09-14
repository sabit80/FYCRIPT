from pathlib import Path

from django.db import migrations


ROOT = Path(__file__).resolve().parents[3] / 'database' / 'raw_sql' / 'wallet'
PROCEDURE_PATH = (
    Path(__file__).resolve().parents[3]
    / 'database' / 'raw_sql' / 'procedures' / 'sp_set_default_wallet.sql'
)


def install_wallet_default_rules(apps, schema_editor):
    # The production deployment uses MySQL for generated columns and
    # procedures. SQLite is used by Django's test runner and cannot parse
    # those MySQL-only constructs.
    if schema_editor.connection.vendor == 'sqlite':
        return
    with schema_editor.connection.cursor() as cursor:
        # Remove duplicate defaults before adding the database-level key.
        cursor.execute(
            """
            CREATE TEMPORARY TABLE wallet_default_keep AS
            SELECT user_id, MIN(wallet_id) AS keep_wallet_id
            FROM wallet_wallet
            WHERE is_default_receive = TRUE
            GROUP BY user_id
            """
        )
        cursor.execute(
            """
            UPDATE wallet_wallet w
            JOIN wallet_default_keep kept ON kept.user_id = w.user_id
            SET w.is_default_receive = FALSE
            WHERE w.is_default_receive = TRUE
              AND w.wallet_id <> kept.keep_wallet_id
            """
        )
        cursor.execute('DROP TEMPORARY TABLE wallet_default_keep')
        cursor.execute(
            """
            ALTER TABLE wallet_wallet
            ADD COLUMN default_receive_user_id BIGINT
            GENERATED ALWAYS AS (
                CASE
                    WHEN is_default_receive = TRUE THEN user_id
                    ELSE NULL
                END
            ) STORED,
            ADD UNIQUE INDEX uq_wallet_one_default_receive
                (default_receive_user_id)
            """
        )

        cursor.execute('DROP TRIGGER IF EXISTS trg_wallet_default_insert')
        cursor.execute('DROP TRIGGER IF EXISTS trg_wallet_default_update')
        trigger_sql = (ROOT / 'wallet_default_triggers.sql').read_text(
            encoding='utf-8'
        )
        insert_sql, update_sql = trigger_sql.split('\nCREATE TRIGGER ', 1)
        cursor.execute(insert_sql.strip().rstrip(';'))
        cursor.execute(('CREATE TRIGGER ' + update_sql).strip().rstrip(';'))
        cursor.execute('DROP PROCEDURE IF EXISTS sp_set_default_wallet')
        cursor.execute(PROCEDURE_PATH.read_text(encoding='utf-8'))


def uninstall_wallet_default_rules(apps, schema_editor):
    if schema_editor.connection.vendor == 'sqlite':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP TRIGGER IF EXISTS trg_wallet_default_insert')
        cursor.execute('DROP TRIGGER IF EXISTS trg_wallet_default_update')
        cursor.execute('DROP PROCEDURE IF EXISTS sp_set_default_wallet')
        cursor.execute(
            'ALTER TABLE wallet_wallet '
            'DROP INDEX uq_wallet_one_default_receive, '
            'DROP COLUMN default_receive_user_id'
        )


class Migration(migrations.Migration):
    dependencies = [('wallet', '0009_critical_wallet_procedures')]
    operations = [
        migrations.RunPython(
            install_wallet_default_rules,
            reverse_code=uninstall_wallet_default_rules,
        ),
    ]
