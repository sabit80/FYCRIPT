SELECT id, user_id, message, type, read_status, timestamp
FROM wallet_notification
WHERE user_id = %s
ORDER BY timestamp DESC
