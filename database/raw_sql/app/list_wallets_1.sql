SELECT wallet_id, user_id, currency_id, name, balance, wallet_status, is_default_receive, created_at
FROM wallet_wallet
WHERE user_id = %s
