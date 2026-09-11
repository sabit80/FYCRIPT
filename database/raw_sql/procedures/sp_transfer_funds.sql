CREATE PROCEDURE sp_transfer_funds(
    IN p_sender_wallet_id   VARCHAR(40),
    IN p_receiver_wallet_id VARCHAR(40),
    IN p_amount             DECIMAL(24,8),
    IN p_received_amount    DECIMAL(24,8),
    IN p_exchange_rate      DECIMAL(24,8),
    IN p_fee                DECIMAL(24,8),
    IN p_transaction_type   VARCHAR(10),
    IN p_category           VARCHAR(255),
    IN p_transaction_id     VARCHAR(40)
)
proc_body: BEGIN
    DECLARE v_sender_balance DECIMAL(24,8);
    DECLARE v_sender_status VARCHAR(10);
    DECLARE v_receiver_status VARCHAR(10);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    IF p_sender_wallet_id = p_receiver_wallet_id THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Sender and receiver wallets must differ';
    END IF;

    START TRANSACTION;

    SELECT balance, wallet_status
    INTO v_sender_balance, v_sender_status
    FROM wallet_wallet
    WHERE wallet_id = p_sender_wallet_id
    FOR UPDATE;

    SELECT wallet_status
    INTO v_receiver_status
    FROM wallet_wallet
    WHERE wallet_id = p_receiver_wallet_id
    FOR UPDATE;

    IF v_sender_status IS NULL OR v_receiver_status IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Wallet not found';
    END IF;

    IF v_sender_status <> 'ACTIVE' OR v_receiver_status <> 'ACTIVE' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Both wallets must be active';
    END IF;

    IF p_amount <= 0 OR p_fee < 0 OR v_sender_balance < p_amount + p_fee THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Insufficient balance';
    END IF;

    UPDATE wallet_wallet
    SET balance = balance - p_amount - p_fee
    WHERE wallet_id = p_sender_wallet_id;

    UPDATE wallet_wallet
    SET balance = balance + p_received_amount
    WHERE wallet_id = p_receiver_wallet_id;

    INSERT INTO wallet_transaction (
        transaction_id, sender_wallet_id, receiver_wallet_id,
        transaction_type, amount, received_amount, exchange_rate,
        fee, status, category, date
    )
    VALUES (
        p_transaction_id, p_sender_wallet_id, p_receiver_wallet_id,
        p_transaction_type, p_amount, p_received_amount, p_exchange_rate,
        p_fee, 'COMPLETED', p_category, NOW(6)
    );

    COMMIT;
END
