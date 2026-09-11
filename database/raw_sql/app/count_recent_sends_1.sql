SELECT COUNT(*)
FROM wallet_transaction
WHERE sender_wallet_id IN (SELECT wallet_id
FROM wallet_wallet
WHERE user_id = %s) AND transaction_type IN ('SEND', 'SHIFT') AND date >= %s
