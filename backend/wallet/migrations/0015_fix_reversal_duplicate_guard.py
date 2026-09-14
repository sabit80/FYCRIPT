from pathlib import Path

from django.db import migrations


PROCEDURE_PATH = (
    Path(__file__).resolve().parents[3]
    / 'database' / 'raw_sql' / 'procedures' / 'sp_reverse_transaction.sql'
)


def reinstall_procedure(apps, schema_editor):
    if schema_editor.connection.vendor == 'sqlite':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP PROCEDURE IF EXISTS sp_reverse_transaction')
        cursor.execute(PROCEDURE_PATH.read_text(encoding='utf-8'))


class Migration(migrations.Migration):
    dependencies = [('wallet', '0014_transaction_reversal')]

    operations = [
        migrations.RunPython(reinstall_procedure, reverse_code=migrations.RunPython.noop),
    ]
