"""
Checks every active PriceAlert against the current ExchangeRate table
and fires a Notification (once) for any that have crossed their
threshold.

    python manage.py check_price_alerts

Run this on a schedule (e.g. every 5-15 minutes via cron / Celery
beat), ideally right after sync_live_rates so alerts fire against
fresh rates rather than stale seed data.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from wallet import db as rawsql
from wallet.views import create_notification, hydrate_user


class Command(BaseCommand):
    help = "Fire a notification for any active PriceAlert whose threshold has been crossed."

    def handle(self, *args, **options):

        alerts = rawsql.get_active_price_alerts()
        fired = 0

        for alert in alerts:

            rate_row = rawsql.get_price_alert_rate(alert['from_currency'], alert['to_currency'])
            if rate_row is None:
                continue
            current_rate = rate_row['rate']

            if current_rate >= alert['threshold_rate']:

                rawsql.update_price_alert(alert['alert_id'], {'triggered_at': timezone.now(), 'is_active': False})

                user = hydrate_user(rawsql.get_user_by_id(alert['user_id']))
                create_notification(
                    user, type='INFO',
                    message=(
                        f"Price alert: 1 {alert['from_currency']} is now "
                        f"{current_rate} {alert['to_currency']} "
                        f"(your threshold was {alert['threshold_rate']})."
                    ),
                )
                fired += 1

        self.stdout.write(self.style.SUCCESS(f"Checked alerts, fired {fired}."))
