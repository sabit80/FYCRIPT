CREATE PROCEDURE sp_set_default_wallet(
    IN p_user_id BIGINT,
    IN p_wallet_id VARCHAR(40)
)
proc_body: BEGIN
    DECLARE v_wallet_user_id BIGINT;
    DECLARE v_wallet_status VARCHAR(10);
    DECLARE v_default_count INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT user_id, wallet_status INTO v_wallet_user_id, v_wallet_status
    FROM wallet_wallet
    WHERE wallet_id = p_wallet_id
    FOR UPDATE;

    IF v_wallet_user_id IS NULL OR v_wallet_user_id <> p_user_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Wallet does not belong to this user';
    END IF;

    IF v_wallet_status <> 'ACTIVE' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only an active wallet can be default';
    END IF;

    SELECT COUNT(*) INTO v_default_count
    FROM wallet_wallet
    WHERE user_id = p_user_id AND is_default_receive = TRUE
    FOR UPDATE;

    UPDATE wallet_wallet
    SET is_default_receive = FALSE
    WHERE user_id = p_user_id
      AND is_default_receive = TRUE
      AND wallet_id <> p_wallet_id;

    UPDATE wallet_wallet
    SET is_default_receive = TRUE
    WHERE wallet_id = p_wallet_id;

    COMMIT;
END
