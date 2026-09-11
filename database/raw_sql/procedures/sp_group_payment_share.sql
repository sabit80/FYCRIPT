CREATE PROCEDURE sp_group_payment_share(
    IN p_participant_id BIGINT, IN p_group_payment_id VARCHAR(40),
    IN p_payer_wallet_id VARCHAR(40), IN p_receiver_wallet_id VARCHAR(40),
    IN p_amount DECIMAL(24,8), IN p_received_amount DECIMAL(24,8),
    IN p_rate DECIMAL(24,8), IN p_fee DECIMAL(24,8), IN p_transaction_id VARCHAR(40)
)
BEGIN
    DECLARE v_balance DECIMAL(24,8);
    DECLARE v_status VARCHAR(10);
    DECLARE v_paid VARCHAR(10);
    DECLARE v_receiver_status VARCHAR(10);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
    START TRANSACTION;
    SELECT status INTO v_paid FROM wallet_grouppaymentparticipant
      WHERE id=p_participant_id AND group_payment_id=p_group_payment_id FOR UPDATE;
    SELECT balance,wallet_status INTO v_balance,v_status FROM wallet_wallet
      WHERE wallet_id=p_payer_wallet_id FOR UPDATE;
    SELECT wallet_status INTO v_receiver_status FROM wallet_wallet
      WHERE wallet_id=p_receiver_wallet_id FOR UPDATE;
    IF v_paid <> 'PENDING' OR v_status <> 'ACTIVE' OR v_receiver_status <> 'ACTIVE' OR p_amount <= 0
       OR v_balance < p_amount+p_fee THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Share already paid or insufficient balance';
    END IF;
    UPDATE wallet_wallet SET balance=balance-p_amount-p_fee WHERE wallet_id=p_payer_wallet_id;
    UPDATE wallet_wallet SET balance=balance+p_received_amount WHERE wallet_id=p_receiver_wallet_id;
    INSERT INTO wallet_transaction
      (transaction_id,sender_wallet_id,receiver_wallet_id,transaction_type,amount,
       received_amount,exchange_rate,fee,status,category,date)
    VALUES (p_transaction_id,p_payer_wallet_id,p_receiver_wallet_id,'SEND',p_amount,
      p_received_amount,p_rate,p_fee,'COMPLETED','Group Payment',NOW(6));
    UPDATE wallet_grouppaymentparticipant SET status='PAID',transaction_id=p_transaction_id,
      paid_at=NOW(6) WHERE id=p_participant_id;
    UPDATE wallet_grouppayment SET status='COMPLETED'
      WHERE group_payment_id=p_group_payment_id
        AND NOT EXISTS (SELECT 1 FROM wallet_grouppaymentparticipant
                        WHERE group_payment_id=p_group_payment_id AND status<>'PAID');
    COMMIT;
END
