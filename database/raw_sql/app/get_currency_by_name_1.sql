SELECT currency_name, type, symbol
FROM wallet_currency
WHERE currency_name = %s
LIMIT 1
