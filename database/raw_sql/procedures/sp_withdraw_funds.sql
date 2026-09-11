CREATE PROCEDURE sp_withdraw_funds(
    IN p_wallet_id VARCHAR(40), IN p_amount DECIMAL(24,8),
    IN p_transaction_id VARCHAR(40), IN p_category VARCHAR(255)
)
BEGIN
    DECLARE v_balance DECIMAL(24,8);
    DECLARE v_status VARCHAR(10);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
    START TRANSACTION;
    SELECT balance, wallet_status INTO v_balance, v_status FROM wallet_wallet
      WHERE wallet_id = p_wallet_id FOR UPDATE;
    IF v_status IS NULL OR v_status <> 'ACTIVE' OR p_amount <= 0
       OR v_balance < p_amount THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Insufficient balance or inactive wallet';
    END IF;
    UPDATE wallet_wallet SET balance = balance - p_amount WHERE wallet_id = p_wallet_id;
    INSERT INTO wallet_transaction
      (transaction_id, sender_wallet_id, transaction_type, amount, received_amount,
       fee, status, category, date)
    VALUES (p_transaction_id, p_wallet_id, 'WITHDRAW', p_amount, p_amount, 0,
            'COMPLETED', p_category, NOW(6));
    COMMIT;
END
