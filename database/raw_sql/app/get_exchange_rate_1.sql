SELECT rate_id, from_curr_id, to_curr_id, rate, last_updated
FROM wallet_exchangerate
WHERE from_curr_id = %s AND to_curr_id = %s
LIMIT 1
