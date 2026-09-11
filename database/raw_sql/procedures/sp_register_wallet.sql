CREATE PROCEDURE sp_register_wallet(
    IN p_wallet_id VARCHAR(40), IN p_user_id BIGINT, IN p_currency_id VARCHAR(10),
    IN p_name VARCHAR(100), IN p_address_id VARCHAR(40),
    IN p_blockchain VARCHAR(50), IN p_public_address VARCHAR(120),
    IN p_is_default BOOLEAN
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
    START TRANSACTION;
    IF p_is_default THEN
      UPDATE wallet_wallet SET is_default_receive=0
        WHERE user_id=p_user_id AND is_default_receive=1;
    END IF;
    INSERT INTO wallet_wallet(wallet_id,user_id,currency_id,balance,is_default_receive,
      wallet_status,name,created_at)
    VALUES(p_wallet_id,p_user_id,p_currency_id,0,p_is_default,'ACTIVE',p_name,NOW(6));
    IF p_blockchain <> '' THEN
      INSERT INTO wallet_cryptoaddress(address_id,wallet_id,blockchain,public_address)
      VALUES(p_address_id,p_wallet_id,p_blockchain,p_public_address);
    END IF;
    COMMIT;
END
