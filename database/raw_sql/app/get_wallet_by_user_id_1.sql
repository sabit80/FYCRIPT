SELECT wallet_id, user_id, currency_id, name, balance, wallet_status, is_default_receive, created_at
FROM wallet_wallet
WHERE wallet_id = %s AND user_id = %s
LIMIT 1
