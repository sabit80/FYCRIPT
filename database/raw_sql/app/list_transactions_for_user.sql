SELECT t.*,
       sw.wallet_id AS sw_wallet_id, sw.name AS sw_name,
       sw.currency_id AS sw_currency_id, sw.user_id AS sw_user_id,
       su.phone AS su_phone,
       rw.wallet_id AS rw_wallet_id, rw.name AS rw_name,
       rw.currency_id AS rw_currency_id, rw.user_id AS rw_user_id,
       ru.phone AS ru_phone
FROM wallet_transaction t
LEFT JOIN wallet_wallet sw ON sw.wallet_id = t.sender_wallet_id
LEFT JOIN wallet_user su ON su.id = sw.user_id
LEFT JOIN wallet_wallet rw ON rw.wallet_id = t.receiver_wallet_id
LEFT JOIN wallet_user ru ON ru.id = rw.user_id
WHERE (sw.user_id = %s OR rw.user_id = %s)
ORDER BY t.date DESC
