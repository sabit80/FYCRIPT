SELECT group_payment_id, organizer_id, receiver_wallet_id, title, total_amount, status, created_at
FROM wallet_grouppayment
WHERE group_payment_id = %s
LIMIT 1
