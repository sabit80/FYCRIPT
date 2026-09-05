"""
Refreshes ExchangeRate rows from a live public rates API instead of
the static seed_data values.

    python manage.py sync_live_rates

Wire this into cron / Celery beat (e.g. every 5-15 minutes) to keep
rates moving. Uses:
  - exchangerate.host (or any similar free FX API) for fiat/fiat pairs
  - CoinGecko's public /simple/price endpoint for crypto -> USD, then
    derives crypto -> every seeded fiat via the USD bridge already
    used elsewhere in this codebase (see get_rate() in wallet/views.py)

NOTE: this sandbox's own network egress allow-list does not include
api.coingecko.com / exchangerate.host, so this command could not be
executed end-to-end while writing it — the request/response handling
below follows each API's documented shape, but double-check field
names against their current docs before relying on it in production,
and wrap the whole command in your own monitoring/alerting so a
silently-failing external API doesn't leave rates stale.
"""

from decimal import Decimal

import requests
from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction
from django.utils import timezone

from wallet import db as rawsql
from wallet.models import Currency, ExchangeRate

COINGECKO_IDS = {
    'BTC': 'bitcoin',
    'ETH': 'ethereum',
    'USDT': 'tether',
}

# CoinGecko's vs_currencies param understands these lowercase codes
# directly, so crypto->fiat rates can be fetched in one call each,
# without needing the USD bridge for currencies it supports.
FIAT_VS_CURRENCIES = ['usd', 'bdt', 'eur', 'gbp']


class Command(BaseCommand):
    help = "Refresh ExchangeRate rows from live public rate APIs (crypto + fiat)."

    def handle(self, *args, **options):

        updated = 0
        updated += self._sync_crypto_rates()
        updated += self._sync_fiat_rates()

        self.stdout.write(self.style.SUCCESS(f"Updated {updated} exchange rate rows."))

    def _sync_crypto_rates(self):

        ids = ','.join(COINGECKO_IDS.values())
        vs = ','.join(FIAT_VS_CURRENCIES)
        url = (
            f"https://api.coingecko.com/api/v3/simple/price"
            f"?ids={ids}&vs_currencies={vs}"
        )

        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            self.stderr.write(self.style.WARNING(f"CoinGecko request failed: {exc}"))
            return 0

        count = 0
        with db_transaction.atomic():
            for symbol, cg_id in COINGECKO_IDS.items():
                prices = data.get(cg_id, {})
                for fiat, price in prices.items():
                    fiat_code = fiat.upper()
                    if not rawsql.exists_where(Currency, "currency_name = %s", [fiat_code]):
                        continue
                    rate = Decimal(str(price))
                    rawsql.upsert(
                        ExchangeRate, "from_curr_id = %s AND to_curr_id = %s", [symbol, fiat_code],
                        {'rate': rate, 'last_updated': timezone.now()},
                    )
                    if rate != 0:
                        rawsql.upsert(
                            ExchangeRate, "from_curr_id = %s AND to_curr_id = %s", [fiat_code, symbol],
                            {'rate': Decimal("1") / rate, 'last_updated': timezone.now()},
                        )
                    count += 2

        return count

    def _sync_fiat_rates(self):

        url = "https://api.exchangerate.host/latest?base=USD"

        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            self.stderr.write(self.style.WARNING(f"exchangerate.host request failed: {exc}"))
            return 0

        rates = data.get('rates', {})
        count = 0

        with db_transaction.atomic():
            for code, rate in rates.items():
                if not rawsql.exists_where(Currency, "currency_name = %s AND type = 'FIAT'", [code]):
                    continue
                if code == 'USD':
                    continue
                rate = Decimal(str(rate))
                rawsql.upsert(
                    ExchangeRate, "from_curr_id = %s AND to_curr_id = %s", ['USD', code],
                    {'rate': rate, 'last_updated': timezone.now()},
                )
                if rate != 0:
                    rawsql.upsert(
                        ExchangeRate, "from_curr_id = %s AND to_curr_id = %s", [code, 'USD'],
                        {'rate': Decimal("1") / rate, 'last_updated': timezone.now()},
                    )
                count += 2

        return count
