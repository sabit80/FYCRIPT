SELECT id, user_id, bank_name, account_number, created_at
FROM wallet_bankaccount
WHERE user_id = %s
