# CryptoWallet Raw SQL Database Guide

The application database layer now uses simple, feature-specific functions with Django's `connection.cursor()`.

Example:

```python
def delete_wallet(wallet_id):
    with connection.cursor() as cursor:
        cursor.execute("""
            DELETE FROM wallet_wallet
            WHERE wallet_id = %s
        """, [wallet_id])
        return cursor.rowcount
```

## Rules used in this version

- No Django ORM query methods such as `Model.objects.filter()`, `get()`, `create()`, `update()`, or `delete()` are used by the API data-access layer.
- No generic CRUD functions such as `insert()`, `find_one()`, `find_all()`, `update_by_pk()`, `delete_by_pk()`, `upsert()`, or `get_row()` remain.
- SQL table and column names are written for the specific feature/table.
- User-controlled values are passed with `%s` parameters rather than concatenated into SQL.
- Django model classes remain in `models.py` because Django migrations, serializers, and model metadata need them. They are not used as a generic ORM data-access layer by the API.
- The virtual environment and `.env` file are intentionally excluded from the distributable ZIP.

## Main database functions

`wallet/db.py` contains explicit functions for users, roles, currencies, exchange rates, wallets, bank accounts, transactions, notifications, audit logs, sessions, KYC, scheduled payments, money requests, group payments, savings goals, price alerts, payment links, and admin/report queries.
