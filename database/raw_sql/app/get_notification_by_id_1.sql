SELECT id, user_id, message, type, read_status, timestamp
FROM wallet_notification
WHERE id = %s
LIMIT 1
