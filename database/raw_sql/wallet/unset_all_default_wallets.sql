UPDATE wallet_wallet
SET is_default_receive = %s
WHERE user_id = %s
  AND is_default_receive = 1
