import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0010_wallet_default_database_rules'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdminAuditEvent',
            fields=[
                ('event_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('action', models.CharField(max_length=100)),
                ('resource_type', models.CharField(max_length=60)),
                ('resource_id', models.CharField(blank=True, default='', max_length=100)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('previous_hash', models.CharField(blank=True, default='', max_length=64)),
                ('event_hash', models.CharField(max_length=64, unique=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='admin_audit_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Dispute',
            fields=[
                ('dispute_id', models.CharField(editable=False, max_length=40, primary_key=True, serialize=False)),
                ('reason', models.CharField(max_length=255)),
                ('amount', models.DecimalField(decimal_places=8, max_digits=24)),
                ('currency', models.CharField(max_length=10)),
                ('status', models.CharField(choices=[('OPEN', 'Open'), ('UNDER_REVIEW', 'Under review'), ('RESOLVED', 'Resolved'), ('REJECTED', 'Rejected'), ('CHARGEBACK', 'Chargeback')], default='OPEN', max_length=20)),
                ('resolution', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('claimant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='disputes', to=settings.AUTH_USER_MODEL)),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='resolved_disputes', to=settings.AUTH_USER_MODEL)),
                ('transaction', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='disputes', to='wallet.transaction')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='FeeLimitConfig',
            fields=[
                ('config_key', models.CharField(max_length=80, primary_key=True, serialize=False)),
                ('scope', models.CharField(default='GLOBAL', max_length=30)),
                ('fee_percent', models.DecimalField(decimal_places=4, default=0, max_digits=8)),
                ('fixed_fee', models.DecimalField(decimal_places=8, default=0, max_digits=24)),
                ('daily_limit', models.DecimalField(blank=True, decimal_places=8, max_digits=24, null=True)),
                ('monthly_limit', models.DecimalField(blank=True, decimal_places=8, max_digits=24, null=True)),
                ('max_transaction', models.DecimalField(blank=True, decimal_places=8, max_digits=24, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='updated_fee_limit_configs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['scope', 'config_key'],
            },
        ),
        migrations.CreateModel(
            name='WalletReserveSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('currency', models.CharField(max_length=10)),
                ('total_customer_balance', models.DecimalField(decimal_places=8, default=0, max_digits=30)),
                ('reserve_balance', models.DecimalField(decimal_places=8, default=0, max_digits=30)),
                ('available_liquidity', models.DecimalField(decimal_places=8, default=0, max_digits=30)),
                ('captured_at', models.DateTimeField(auto_now_add=True)),
                ('captured_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='liquidity_snapshots', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-captured_at'],
                'indexes': [models.Index(fields=['currency', '-captured_at'], name='wallet_wall_currenc_636ca7_idx')],
            },
        ),
    ]
