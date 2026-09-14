from pathlib import Path

from django.db import migrations


PROCEDURE_PATH = (
    Path(__file__).resolve().parents[3]
    / 'database' / 'raw_sql' / 'procedures' / 'sp_reverse_transaction.sql'
)


def install_procedure(apps, schema_editor):
    if schema_editor.connection.vendor == 'sqlite':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP PROCEDURE IF EXISTS sp_reverse_transaction')
        cursor.execute(PROCEDURE_PATH.read_text(encoding='utf-8'))


def uninstall_procedure(apps, schema_editor):
    if schema_editor.connection.vendor == 'sqlite':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP PROCEDURE IF EXISTS sp_reverse_transaction')


class Migration(migrations.Migration):
    dependencies = [('wallet', '0013_monitoring_only_admin_wallets')]

    operations = [
        migrations.RunPython(install_procedure, reverse_code=uninstall_procedure),
    ]
