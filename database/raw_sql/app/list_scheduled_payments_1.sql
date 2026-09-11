SELECT schedule_id, owner_id, sender_wallet_id, recipient_phone, recipient_wallet_id, amount, note, frequency, next_run_at, last_run_at, status, created_at
FROM wallet_scheduledpayment
WHERE owner_id = %s
ORDER BY next_run_at
