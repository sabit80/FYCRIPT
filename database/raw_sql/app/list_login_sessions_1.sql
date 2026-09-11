SELECT id, user_id, ip_address, device_info, login_time
FROM wallet_loginsession
WHERE user_id = %s
ORDER BY login_time DESC
