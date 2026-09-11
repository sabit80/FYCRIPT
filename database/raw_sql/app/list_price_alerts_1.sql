SELECT alert_id, user_id, from_currency, to_currency, threshold_rate, is_active, triggered_at, created_at
FROM wallet_pricealert
WHERE user_id = %s
