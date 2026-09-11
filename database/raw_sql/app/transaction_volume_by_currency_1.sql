SELECT sw.currency_id AS currency, SUM(t.amount) AS total, COUNT(t.transaction_id) AS count
FROM wallet_transaction t
JOIN wallet_wallet sw ON sw.wallet_id = t.sender_wallet_id
GROUP BY sw.currency_id
ORDER BY total DESC
