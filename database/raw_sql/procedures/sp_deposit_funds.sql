CREATE PROCEDURE sp_deposit_funds(
    IN p_wallet_id VARCHAR(40), IN p_amount DECIMAL(24,8),
    IN p_transaction_id VARCHAR(40), IN p_category VARCHAR(255)
)
BEGIN
    DECLARE v_status VARCHAR(10);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
    START TRANSACTION;
    SELECT wallet_status INTO v_status FROM wallet_wallet
      WHERE wallet_id = p_wallet_id FOR UPDATE;
    IF p_amount <= 0 OR v_status IS NULL OR v_status <> 'ACTIVE' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid wallet or amount';
    END IF;
    UPDATE wallet_wallet SET balance = balance + p_amount WHERE wallet_id = p_wallet_id;
    INSERT INTO wallet_transaction
      (transaction_id, receiver_wallet_id, transaction_type, amount, received_amount,
       fee, status, category, date)
    VALUES (p_transaction_id, p_wallet_id, 'DEPOSIT', p_amount, p_amount, 0,
            'COMPLETED', p_category, NOW(6));
    COMMIT;
END
