from decimal import Decimal
from itertools import permutations

from django.core.management.base import BaseCommand
from django.utils import timezone

from wallet import db as rawsql
from wallet.models import Currency, Role, ExchangeRate


CURRENCIES = [
    ("USD", "FIAT", "$"),
    ("BDT", "FIAT", "৳"),
    ("EUR", "FIAT", "€"),
    ("GBP", "FIAT", "£"),
    ("BTC", "CRYPTO", "₿"),
    ("ETH", "CRYPTO", "Ξ"),
    ("USDT", "CRYPTO", "₮"),
]

# Rate = how many units of "to" you get for 1 unit of "from".
RATES_TO_USD = {
    "USD": Decimal("1"),
    "BDT": Decimal("0.0083"),      # 1 BDT = 0.0083 USD
    "EUR": Decimal("1.0870"),      # 1 EUR = 1.087 USD
    "GBP": Decimal("1.2650"),
    "BTC": Decimal("65000"),
    "ETH": Decimal("3400"),
    "USDT": Decimal("1"),
}

ROLES = ["USER", "ADMIN"]


class Command(BaseCommand):
    help = (
        "Seeds Currency, Role and ExchangeRate reference data. "
        "Safe to run multiple times."
    )

    def handle(self, *args, **options):

        for name, ctype, symbol in CURRENCIES:
            rawsql.upsert(
                Currency, "currency_name = %s", [name],
                {"type": ctype, "symbol": symbol},
            )
        self.stdout.write(self.style.SUCCESS(
            f"Currencies ready ({len(CURRENCIES)})."
        ))

        for role_name in ROLES:
            rawsql.get_or_create_simple(Role, role_name=role_name)
        self.stdout.write(self.style.SUCCESS(
            f"Roles ready ({len(ROLES)})."
        ))

        count = 0
        for from_code, to_code in permutations(RATES_TO_USD.keys(), 2):
            rate = RATES_TO_USD[from_code] / RATES_TO_USD[to_code]
            rawsql.upsert(
                ExchangeRate, "from_curr_id = %s AND to_curr_id = %s", [from_code, to_code],
                {"rate": rate, "last_updated": timezone.now()},
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(
            f"Exchange rates ready ({count} pairs)."
        ))

        self.stdout.write(self.style.SUCCESS("Seed complete."))
