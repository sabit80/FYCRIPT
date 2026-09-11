SELECT link_id, merchant_id, receiving_wallet_id, title, amount, is_active, created_at
FROM wallet_paymentlink
WHERE link_id = %s AND is_active = 1
LIMIT 1
