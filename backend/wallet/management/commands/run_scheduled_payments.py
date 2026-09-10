"""
Executes any ScheduledPayment rows whose next_run_at has passed.

Run this on a schedule — e.g. an hourly cron entry or a Celery beat
task — since nothing inside the Django app itself triggers it:

    */15 * * * * cd /path/to/backend && venv/bin/python manage.py run_scheduled_payments

Each due, ACTIVE schedule performs the same balance-moving logic as
SendView (fee + limit checks included), then advances next_run_at
per its frequency (or marks itself CANCELLED if it was ONCE-only).
Wrapped one schedule at a time in its own db transaction, so one
failing schedule (e.g. insufficient balance) doesn't block the rest.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction
from django.utils import timezone

from wallet import db as rawsql
from wallet.models import ScheduledPayment, User, Wallet
from wallet.views import (
    get_rate, calculate_send_fee, check_send_limit, check_fraud_velocity,
    create_audit_log, create_notification, create_transaction,
    save_wallet_fields, get_wallet_or_404, hydrate_user, lock_wallets,
)


class Command(BaseCommand):
    help = "Execute any due ScheduledPayment rows (recurring / future-dated transfers)."

    def handle(self, *args, **options):

        due_rows = rawsql.get_due_scheduled_payments(timezone.now())

        executed, failed = 0, 0

        for row in due_rows:
            owner = hydrate_user(rawsql.get_user_by_id(row['owner_id']))
            sender_wallet = get_wallet_or_404(row['sender_wallet_id'])
            try:
                self._execute_one(row, owner, sender_wallet)
                executed += 1
            except Exception as exc:  # noqa: BLE001 — log & continue, one bad row shouldn't block others
                failed += 1
                self.stderr.write(
                    self.style.WARNING(
                        f"Schedule {row['schedule_id']} failed: {exc}"
                    )
                )
                create_notification(
                    owner, type='TRANSACTION',
                    message=(
                        f"Your scheduled payment of {row['amount']} from "
                        f"{sender_wallet.name} failed: {exc}"
                    ),
                )

        self.stdout.write(
            self.style.SUCCESS(f"Executed {executed}, failed {failed}.")
        )

    def _execute_one(self, row, owner, sender_wallet):

        with db_transaction.atomic():

            if sender_wallet.wallet_status != 'ACTIVE':
                raise ValueError("sender wallet isn't active")

            # Resolve receiver wallet the same way SendView does.
            if row['recipient_wallet_id']:
                receiver_wallet = get_wallet_or_404(row['recipient_wallet_id'])
                txn_type = 'SHIFT'
            else:
                recipient_row = rawsql.get_user_by_phone(row['recipient_phone'])
                if recipient_row is None:
                    raise ValueError("recipient account no longer exists")
                recipient = hydrate_user(recipient_row)

                default_row = rawsql.get_default_receive_wallet(recipient.id)
                if not default_row:
                    raise ValueError("recipient has no receive wallet")
                receiver_wallet = get_wallet_or_404(default_row['wallet_id'])
                txn_type = 'SEND'
                check_send_limit(owner, sender_wallet, row['amount'])
                check_fraud_velocity(owner, _FakeRequest())

            rate = get_rate(sender_wallet.currency_id, receiver_wallet.currency_id)
            receive_amount = row['amount'] * rate
            fee = calculate_send_fee(row['amount']) if txn_type == 'SEND' else Decimal("0")

            # Re-lock and re-read both balances now, inside this schedule's
            # own atomic() block, in case another request (a manual Send,
            # another due schedule, etc.) touched either wallet between the
            # SELECT in handle() and this point.
            lock_wallets(sender_wallet, receiver_wallet)

            if row['amount'] + fee > sender_wallet.balance:
                raise ValueError("insufficient balance")

            save_wallet_fields(sender_wallet, balance=sender_wallet.balance - (row['amount'] + fee))
            save_wallet_fields(receiver_wallet, balance=receiver_wallet.balance + receive_amount)

            txn = create_transaction(
                sender_wallet_id=sender_wallet.wallet_id,
                receiver_wallet_id=receiver_wallet.wallet_id,
                transaction_type=txn_type,
                amount=row['amount'],
                received_amount=receive_amount,
                exchange_rate=rate,
                fee=fee,
            )

            create_audit_log(owner, f"SCHEDULED_{txn_type}", remarks=row['schedule_id'])
            create_notification(
                owner, type='TRANSACTION',
                message=(
                    f"Scheduled payment sent: {row['amount']} "
                    f"{sender_wallet.currency_id} ({row['note'] or txn.transaction_id})."
                ),
            )

            # Same advance()-then-save logic as ScheduledPayment.advance(),
            # done here as a raw UPDATE instead of hydrating + .save().
            from datetime import timedelta
            next_run_at = row['next_run_at']
            new_status = row['status']
            if row['frequency'] == 'DAILY':
                next_run_at += timedelta(days=1)
            elif row['frequency'] == 'WEEKLY':
                next_run_at += timedelta(weeks=1)
            elif row['frequency'] == 'MONTHLY':
                next_run_at += timedelta(days=30)
            else:  # ONCE
                new_status = 'CANCELLED'

            rawsql.update_scheduled_payment(row['schedule_id'], {
                'last_run_at': timezone.now(), 'next_run_at': next_run_at, 'status': new_status,
            })


class _FakeRequest:
    """check_fraud_velocity() only reads request.META for an IP/UA
    when it needs to log an AuditLog entry; give it something inert
    for the cron/management-command context where there's no real
    HTTP request."""
    META = {}
