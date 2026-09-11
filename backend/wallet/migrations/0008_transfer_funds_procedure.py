from pathlib import Path

from django.db import migrations


PROCEDURE_SQL_PATH = (
    Path(__file__).resolve().parents[3]
    / 'database'
    / 'raw_sql'
    / 'procedures'
    / 'sp_transfer_funds.sql'
)


def install_transfer_procedure(apps, schema_editor):
    with PROCEDURE_SQL_PATH.open(encoding='utf-8') as sql_file:
        procedure_sql = sql_file.read()

    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP PROCEDURE IF EXISTS sp_transfer_funds')
        cursor.execute(procedure_sql)


def remove_transfer_procedure(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP PROCEDURE IF EXISTS sp_transfer_funds')


class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0007_sp_exchange_funds'),
    ]

    operations = [
        migrations.RunPython(
            install_transfer_procedure,
            reverse_code=remove_transfer_procedure,
        ),
    ]
