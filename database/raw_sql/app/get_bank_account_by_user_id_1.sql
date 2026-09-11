SELECT id, user_id, bank_name, account_number, created_at
FROM wallet_bankaccount
WHERE id = %s AND user_id = %s
LIMIT 1
