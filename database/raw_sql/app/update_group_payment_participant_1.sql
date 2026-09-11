UPDATE wallet_grouppaymentparticipant
SET status = %s, transaction_id = %s, paid_at = %s
WHERE id = %s
