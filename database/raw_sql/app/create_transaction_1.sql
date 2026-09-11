INSERT INTO wallet_transaction (transaction_id, sender_wallet_id, receiver_wallet_id, transaction_type, amount, received_amount, exchange_rate, fee, status, category, date)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
