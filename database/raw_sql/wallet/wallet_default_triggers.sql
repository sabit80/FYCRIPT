CREATE TRIGGER trg_wallet_default_insert
BEFORE INSERT ON wallet_wallet
FOR EACH ROW
BEGIN
    IF NEW.is_default_receive = TRUE AND NEW.wallet_status <> 'ACTIVE' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only an active wallet can be default';
    END IF;
END
;
CREATE TRIGGER trg_wallet_default_update
BEFORE UPDATE ON wallet_wallet
FOR EACH ROW
BEGIN
    IF NEW.is_default_receive = TRUE AND NEW.wallet_status <> 'ACTIVE' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only an active wallet can be default';
    END IF;
END
;
