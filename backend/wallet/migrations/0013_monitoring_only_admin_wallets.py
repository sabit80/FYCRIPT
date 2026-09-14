from django.db import migrations


def close_administrative_wallets(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE wallet_wallet
            SET wallet_status = 'CLOSED',
                is_default_receive = FALSE
            WHERE user_id IN (
                SELECT id
                FROM wallet_user
                WHERE is_staff = TRUE OR is_superuser = TRUE
            )
            """
        )


def install_admin_wallet_guards(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER IF EXISTS trg_wallet_admin_insert")
        cursor.execute("DROP TRIGGER IF EXISTS trg_wallet_admin_update")
        cursor.execute("DROP TRIGGER IF EXISTS trg_user_admin_promotion")

        if schema_editor.connection.vendor == 'sqlite':
            cursor.execute(
                """
                CREATE TRIGGER trg_wallet_admin_insert
                BEFORE INSERT ON wallet_wallet
                WHEN EXISTS (
                    SELECT 1
                    FROM wallet_user
                    WHERE id = NEW.user_id
                      AND (is_staff = 1 OR is_superuser = 1)
                )
                BEGIN
                    SELECT RAISE(ABORT, 'administrative accounts cannot own wallets');
                END
                """
            )
            cursor.execute(
                """
                CREATE TRIGGER trg_wallet_admin_update
                BEFORE UPDATE ON wallet_wallet
                WHEN EXISTS (
                    SELECT 1
                    FROM wallet_user
                    WHERE id = NEW.user_id
                      AND (is_staff = 1 OR is_superuser = 1)
                )
                BEGIN
                    SELECT RAISE(ABORT, 'administrative accounts cannot own wallets');
                END
                """
            )
            cursor.execute(
                """
                CREATE TRIGGER trg_user_admin_promotion
                AFTER UPDATE OF is_staff, is_superuser ON wallet_user
                WHEN (NEW.is_staff = 1 OR NEW.is_superuser = 1)
                BEGIN
                    UPDATE wallet_wallet
                    SET wallet_status = 'CLOSED',
                        is_default_receive = 0
                    WHERE user_id = NEW.id;
                END
                """
            )
            return

        cursor.execute(
            """
            CREATE TRIGGER trg_wallet_admin_insert
            BEFORE INSERT ON wallet_wallet
            FOR EACH ROW
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM wallet_user
                    WHERE id = NEW.user_id
                      AND (is_staff = 1 OR is_superuser = 1)
                ) THEN
                    SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'administrative accounts cannot own wallets';
                END IF;
            END
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER trg_wallet_admin_update
            BEFORE UPDATE ON wallet_wallet
            FOR EACH ROW
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM wallet_user
                    WHERE id = NEW.user_id
                      AND (is_staff = 1 OR is_superuser = 1)
                ) THEN
                    SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'administrative accounts cannot own wallets';
                END IF;
            END
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER trg_user_admin_promotion
            AFTER UPDATE ON wallet_user
            FOR EACH ROW
            BEGIN
                IF (NEW.is_staff = 1 OR NEW.is_superuser = 1)
                   AND (OLD.is_staff = 0 AND OLD.is_superuser = 0) THEN
                    UPDATE wallet_wallet
                    SET wallet_status = 'CLOSED',
                        is_default_receive = 0
                    WHERE user_id = NEW.id;
                END IF;
            END
            """
        )


def uninstall_admin_wallet_guards(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER IF EXISTS trg_wallet_admin_insert")
        cursor.execute("DROP TRIGGER IF EXISTS trg_wallet_admin_update")
        cursor.execute("DROP TRIGGER IF EXISTS trg_user_admin_promotion")


class Migration(migrations.Migration):
    dependencies = [
        ('wallet', '0012_immutable_admin_audit'),
    ]

    operations = [
        migrations.RunPython(
            close_administrative_wallets,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            install_admin_wallet_guards,
            reverse_code=uninstall_admin_wallet_guards,
        ),
    ]
