UPDATE wallet_user
SET is_flagged = %s, flagged_reason = %s, flagged_at = %s
WHERE id = %s
