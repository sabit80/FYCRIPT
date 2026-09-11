UPDATE wallet_moneyrequest
SET status = %s, transaction_id = %s, responded_at = %s
WHERE request_id = %s
