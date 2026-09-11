SELECT transaction_id, sender_wallet_id, receiver_wallet_id, transaction_type, amount, received_amount, fee, exchange_rate, status, category, date
FROM wallet_transaction
WHERE transaction_id = %s
LIMIT 1
