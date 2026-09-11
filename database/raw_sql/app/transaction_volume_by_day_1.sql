SELECT DATE(date) AS day, COUNT(transaction_id) AS count, SUM(amount) AS volume
FROM wallet_transaction
WHERE date >= %s
GROUP BY DATE(date)
ORDER BY day
