from django.db import migrations


def install_triggers(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        if schema_editor.connection.vendor == 'sqlite':
            cursor.execute(
                """CREATE TRIGGER wallet_admin_audit_no_update
                   BEFORE UPDATE ON wallet_adminauditevent
                   BEGIN SELECT RAISE(ABORT, 'admin audit events are immutable'); END"""
            )
            cursor.execute(
                """CREATE TRIGGER wallet_admin_audit_no_delete
                   BEFORE DELETE ON wallet_adminauditevent
                   BEGIN SELECT RAISE(ABORT, 'admin audit events are immutable'); END"""
            )
        else:
            cursor.execute("DROP TRIGGER IF EXISTS wallet_admin_audit_no_update")
            cursor.execute("DROP TRIGGER IF EXISTS wallet_admin_audit_no_delete")
            cursor.execute(
                """CREATE TRIGGER wallet_admin_audit_no_update
                   BEFORE UPDATE ON wallet_adminauditevent FOR EACH ROW
                   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT =
                   'admin audit events are immutable'"""
            )
            cursor.execute(
                """CREATE TRIGGER wallet_admin_audit_no_delete
                   BEFORE DELETE ON wallet_adminauditevent FOR EACH ROW
                   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT =
                   'admin audit events are immutable'"""
            )


def uninstall_triggers(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER IF EXISTS wallet_admin_audit_no_update")
        cursor.execute("DROP TRIGGER IF EXISTS wallet_admin_audit_no_delete")


class Migration(migrations.Migration):
    dependencies = [('wallet', '0011_adminauditevent_dispute_feelimitconfig_and_more')]
    operations = [
        migrations.RunPython(install_triggers, reverse_code=uninstall_triggers),
    ]
