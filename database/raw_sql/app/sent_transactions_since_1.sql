SELECT t.amount, w.currency_id
FROM wallet_transaction t
JOIN wallet_wallet w ON w.wallet_id = t.sender_wallet_id
WHERE w.user_id = %s AND t.transaction_type = 'SEND' AND t.date >= %s
