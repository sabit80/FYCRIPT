SELECT link_id, merchant_id, receiving_wallet_id, title, amount, is_active, created_at
FROM wallet_paymentlink
WHERE merchant_id = %s
ORDER BY created_at DESC
