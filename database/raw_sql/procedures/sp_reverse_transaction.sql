CREATE PROCEDURE sp_reverse_transaction(
    IN p_original_id VARCHAR(40),
    IN p_reversal_id VARCHAR(40),
    IN p_reason VARCHAR(255)
)
BEGIN
    DECLARE v_sender_id VARCHAR(40);
    DECLARE v_receiver_id VARCHAR(40);
    DECLARE v_type VARCHAR(10);
    DECLARE v_amount DECIMAL(24,8);
    DECLARE v_received DECIMAL(24,8);
    DECLARE v_fee DECIMAL(24,8);
    DECLARE v_rate DECIMAL(24,8);
    DECLARE v_category VARCHAR(40);
    DECLARE v_date DATETIME(6);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT sender_wallet_id, receiver_wallet_id, transaction_type,
           amount, received_amount, fee, exchange_rate, category, date
      INTO v_sender_id, v_receiver_id, v_type, v_amount, v_received,
           v_fee, v_rate, v_category, v_date
      FROM wallet_transaction
     WHERE transaction_id = p_original_id
     FOR UPDATE;

    IF v_type IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'transaction not found';
    END IF;

    IF (SELECT status FROM wallet_transaction
         WHERE transaction_id = p_original_id) <> 'COMPLETED' THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'only completed transactions can be reversed';
    END IF;

    IF EXISTS (
        SELECT 1 FROM wallet_transaction
         WHERE transaction_type = 'REVERSAL'
           AND category LIKE CONCAT('REVERSAL_OF:', p_original_id, '|%')
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'transaction already reversed';
    END IF;

    IF v_receiver_id IS NOT NULL THEN
        UPDATE wallet_wallet
           SET balance = balance - COALESCE(v_received, v_amount)
         WHERE wallet_id = v_receiver_id
           AND balance >= COALESCE(v_received, v_amount);
        IF ROW_COUNT() = 0 THEN
            SIGNAL SQLSTATE '45000'
              SET MESSAGE_TEXT = 'receiver wallet no longer has sufficient funds';
        END IF;
    END IF;

    IF v_sender_id IS NOT NULL THEN
        UPDATE wallet_wallet
           SET balance = balance + v_amount + COALESCE(v_fee, 0)
         WHERE wallet_id = v_sender_id;
        IF ROW_COUNT() = 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'sender wallet not found';
        END IF;
    END IF;

    UPDATE wallet_transaction
       SET status = 'REVERSED'
     WHERE transaction_id = p_original_id;

    INSERT INTO wallet_transaction (
        transaction_id, sender_wallet_id, receiver_wallet_id,
        transaction_type, amount, received_amount, fee, exchange_rate,
        status, category, date
    )
    VALUES (
        p_reversal_id, v_receiver_id, v_sender_id, 'REVERSAL',
        COALESCE(v_received, v_amount), v_amount, 0, v_rate,
        'COMPLETED', CONCAT('REVERSAL_OF:', p_original_id, '|', p_reason), NOW(6)
    );

    COMMIT;
END
