SELECT id, group_payment_id, user_id, share_amount, status, transaction_id, paid_at
FROM wallet_grouppaymentparticipant
WHERE group_payment_id = %s AND user_id = %s
LIMIT 1
