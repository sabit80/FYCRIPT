SELECT goal_id, user_id, savings_wallet_id, name, target_amount, deadline, auto_save_percent, is_active, created_at
FROM wallet_savingsgoal
WHERE user_id = %s AND is_active = 1 AND auto_save_percent > 0
