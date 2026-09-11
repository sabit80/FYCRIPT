CREATE PROCEDURE sp_execute_scheduled_payment(
    IN p_schedule_id VARCHAR(40), IN p_sender_wallet_id VARCHAR(40),
    IN p_receiver_wallet_id VARCHAR(40), IN p_amount DECIMAL(24,8),
    IN p_received_amount DECIMAL(24,8), IN p_rate DECIMAL(24,8),
    IN p_fee DECIMAL(24,8), IN p_transaction_id VARCHAR(40),
    IN p_next_run_at DATETIME(6), IN p_new_status VARCHAR(10)
)
BEGIN
    DECLARE v_balance DECIMAL(24,8);
    DECLARE v_status VARCHAR(10);
    DECLARE v_schedule_status VARCHAR(10);
    DECLARE v_receiver_status VARCHAR(10);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
    START TRANSACTION;
    SELECT status INTO v_schedule_status FROM wallet_scheduledpayment
      WHERE schedule_id=p_schedule_id FOR UPDATE;
    SELECT balance,wallet_status INTO v_balance,v_status FROM wallet_wallet
      WHERE wallet_id=p_sender_wallet_id FOR UPDATE;
    SELECT wallet_status INTO v_receiver_status FROM wallet_wallet
      WHERE wallet_id=p_receiver_wallet_id FOR UPDATE;
    IF v_schedule_status <> 'ACTIVE' OR v_status <> 'ACTIVE' OR v_receiver_status <> 'ACTIVE'
       OR p_amount <= 0 OR v_balance < p_amount+p_fee THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Schedule is inactive or balance is insufficient';
    END IF;
    UPDATE wallet_wallet SET balance=balance-p_amount-p_fee WHERE wallet_id=p_sender_wallet_id;
    UPDATE wallet_wallet SET balance=balance+p_received_amount WHERE wallet_id=p_receiver_wallet_id;
    INSERT INTO wallet_transaction
      (transaction_id,sender_wallet_id,receiver_wallet_id,transaction_type,amount,
       received_amount,exchange_rate,fee,status,category,date)
    VALUES (p_transaction_id,p_sender_wallet_id,p_receiver_wallet_id,
      IF(p_fee > 0,'SEND','SHIFT'),p_amount,p_received_amount,p_rate,p_fee,
      'COMPLETED','Scheduled Payment',NOW(6));
    UPDATE wallet_scheduledpayment SET last_run_at=NOW(6),next_run_at=p_next_run_at,
      status=p_new_status WHERE schedule_id=p_schedule_id;
    COMMIT;
END
