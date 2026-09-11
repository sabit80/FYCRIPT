SELECT request_id, requester_id, requester_wallet_id, payer_id, amount, note, status, transaction_id, created_at, responded_at
FROM wallet_moneyrequest
WHERE request_id = %s AND payer_id = %s
LIMIT 1
