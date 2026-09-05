from django.db import migrations


class Migration(migrations.Migration):
    """
    Creates wallet_blacklisted_token with plain RunSQL (not a Model +
    makemigrations) since this table is only ever touched via raw SQL
    (see wallet/auth_backends.py and LogoutView in views.py) — CSE216
    60% milestone: "Using ORM is strictly prohibited".
    """

    dependencies = [
        ('wallet', '0005_alter_transaction_transaction_type_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS wallet_blacklisted_token (
                    jti VARCHAR(255) NOT NULL PRIMARY KEY,
                    expires_at DATETIME(6) NOT NULL,
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    INDEX idx_blacklist_expires (expires_at)
                );
            """,
            reverse_sql="DROP TABLE IF EXISTS wallet_blacklisted_token;",
        ),
    ]
