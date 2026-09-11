from pathlib import Path

from django.db import migrations


PROCEDURES = (
    'sp_deposit_funds', 'sp_withdraw_funds', 'sp_accept_money_request',
    'sp_group_payment_share', 'sp_register_wallet',
    'sp_execute_scheduled_payment',
)
ROOT = Path(__file__).resolve().parents[3] / 'database' / 'raw_sql' / 'procedures'


def install(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for name in PROCEDURES:
            cursor.execute(f'DROP PROCEDURE IF EXISTS {name}')
            cursor.execute((ROOT / f'{name}.sql').read_text(encoding='utf-8'))


def uninstall(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for name in PROCEDURES:
            cursor.execute(f'DROP PROCEDURE IF EXISTS {name}')


class Migration(migrations.Migration):
    dependencies = [('wallet', '0008_transfer_funds_procedure')]
    operations = [migrations.RunPython(install, reverse_code=uninstall)]
