-- =====================================================
-- CryptoWallet — MySQL schema (Advanced SQL / PL version)
-- Requires MySQL 8.0.16+
-- =====================================================

SET NAMES utf8mb4;

-- =====================================================
-- 1. TABLES
-- =====================================================

CREATE TABLE IF NOT EXISTS `user` (
    user_id             BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name                VARCHAR(150) NOT NULL,
    email               VARCHAR(254) UNIQUE NOT NULL,
    phone               VARCHAR(20) UNIQUE NOT NULL,
    hashed_password     VARCHAR(255) NOT NULL,
    status              VARCHAR(10) NOT NULL DEFAULT 'ACTIVE'
                         CHECK (status IN ('ACTIVE','SUSPENDED','CLOSED')),
    registration_date   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    is_staff            BOOLEAN NOT NULL DEFAULT FALSE,
    is_superuser        BOOLEAN NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS role (
    role_id     BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    role_name   VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS user_role (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id     BIGINT UNSIGNED NOT NULL,
    role_id     BIGINT UNSIGNED NOT NULL,
    assigned_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE (user_id, role_id),
    CONSTRAINT fk_user_role_user FOREIGN KEY (user_id) REFERENCES `user`(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_user_role_role FOREIGN KEY (role_id) REFERENCES role(role_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS kyc (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id             BIGINT UNSIGNED UNIQUE NOT NULL,
    nid_number          VARCHAR(50),
    passport_number     VARCHAR(50),
    submission_date     DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    verification_status VARCHAR(10) NOT NULL DEFAULT 'PENDING'
                         CHECK (verification_status IN ('PENDING','APPROVED','REJECTED')),
    CONSTRAINT fk_kyc_user FOREIGN KEY (user_id) REFERENCES `user`(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bank_account (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT UNSIGNED NOT NULL,
    bank_name       VARCHAR(100) NOT NULL,
    account_number  VARCHAR(50) NOT NULL,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE (user_id, account_number),
    CONSTRAINT fk_bank_account_user FOREIGN KEY (user_id) REFERENCES `user`(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS currency (
    currency_name   VARCHAR(10) PRIMARY KEY,
    type            VARCHAR(10) NOT NULL CHECK (type IN ('FIAT','CRYPTO')),
    symbol          VARCHAR(5) DEFAULT ''
);

CREATE TABLE IF NOT EXISTS wallet (
    wallet_id           VARCHAR(40) PRIMARY KEY,
    user_id             BIGINT UNSIGNED NOT NULL,
    currency_name       VARCHAR(10) NOT NULL,
    name                VARCHAR(100) NOT NULL,
    balance             DECIMAL(24,8) NOT NULL DEFAULT 0,
    wallet_status       VARCHAR(10) NOT NULL DEFAULT 'ACTIVE'
                         CHECK (wallet_status IN ('ACTIVE','FROZEN','CLOSED')),
    is_default_receive  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_wallet_user FOREIGN KEY (user_id) REFERENCES `user`(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_wallet_currency FOREIGN KEY (currency_name) REFERENCES currency(currency_name)
);

CREATE TABLE IF NOT EXISTS crypto_address (
    address_id      VARCHAR(40) PRIMARY KEY,
    wallet_id       VARCHAR(40) NOT NULL,
    blockchain      VARCHAR(50) NOT NULL,
    public_address  VARCHAR(120) UNIQUE NOT NULL,
    CONSTRAINT fk_crypto_address_wallet FOREIGN KEY (wallet_id) REFERENCES wallet(wallet_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exchange_rate (
    rate_id         BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    from_curr       VARCHAR(10) NOT NULL,
    to_curr         VARCHAR(10) NOT NULL,
    rate            DECIMAL(24,8) NOT NULL,
    last_updated    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE (from_curr, to_curr),
    CONSTRAINT fk_exchange_rate_from FOREIGN KEY (from_curr) REFERENCES currency(currency_name),
    CONSTRAINT fk_exchange_rate_to FOREIGN KEY (to_curr) REFERENCES currency(currency_name)
);

CREATE TABLE IF NOT EXISTS transaction (
    transaction_id       VARCHAR(40) PRIMARY KEY,
    sender_wallet_id     VARCHAR(40),
    receiver_wallet_id   VARCHAR(40),
    transaction_type     VARCHAR(10) NOT NULL
                          CHECK (transaction_type IN ('SEND','RECEIVE','SHIFT','EXCHANGE','DEPOSIT')),
    amount               DECIMAL(24,8) NOT NULL,
    received_amount      DECIMAL(24,8),
    fee                  DECIMAL(24,8) NOT NULL DEFAULT 0,
    exchange_rate        DECIMAL(24,8),
    status               VARCHAR(10) NOT NULL DEFAULT 'COMPLETED'
                          CHECK (status IN ('PENDING','COMPLETED','FAILED')),
    date                 DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_txn_sender FOREIGN KEY (sender_wallet_id) REFERENCES wallet(wallet_id) ON DELETE SET NULL,
    CONSTRAINT fk_txn_receiver FOREIGN KEY (receiver_wallet_id) REFERENCES wallet(wallet_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS notification (
    notification_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id          BIGINT UNSIGNED NOT NULL,
    message          VARCHAR(255) NOT NULL,
    type             VARCHAR(15) NOT NULL DEFAULT 'INFO'
                     CHECK (type IN ('INFO','TRANSACTION','SECURITY')),
    read_status      BOOLEAN NOT NULL DEFAULT FALSE,
    timestamp        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_notification_user FOREIGN KEY (user_id) REFERENCES `user`(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id     BIGINT UNSIGNED,
    action      VARCHAR(100) NOT NULL,
    remarks     VARCHAR(255),
    ip_address  VARCHAR(45),
    timestamp   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_auditlog_user FOREIGN KEY (user_id) REFERENCES `user`(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS login_session (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id     BIGINT UNSIGNED NOT NULL,
    ip_address  VARCHAR(45),
    device_info VARCHAR(255),
    login_time  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_login_session_user FOREIGN KEY (user_id) REFERENCES `user`(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_wallet_user ON wallet(user_id);
CREATE INDEX idx_transaction_sender ON transaction(sender_wallet_id);
CREATE INDEX idx_transaction_receiver ON transaction(receiver_wallet_id);
CREATE INDEX idx_notification_user ON notification(user_id);
CREATE INDEX idx_auditlog_user ON audit_log(user_id);

-- =====================================================
-- 2. SEED REFERENCE DATA
-- =====================================================

INSERT IGNORE INTO currency (currency_name, type, symbol) VALUES
    ('USD','FIAT','$'), ('BDT','FIAT','৳'), ('EUR','FIAT','€'), ('GBP','FIAT','£'),
    ('BTC','CRYPTO','₿'), ('ETH','CRYPTO','Ξ'), ('USDT','CRYPTO','₮');

INSERT IGNORE INTO role (role_name) VALUES ('USER'), ('ADMIN');

-- =====================================================
-- 3. TRIGGERS  -- intentionally NOT included
-- =====================================================
-- An earlier version of this file had three triggers here:
--   - trg_wallet_single_default_insert / _update
--   - trg_wallet_balance_audit
--   - trg_transaction_notify
--
-- All three duplicated logic that already lives in the Django app:
--   - "one default-receive wallet per user" is already enforced in
--     Wallet.save() (wallet/models.py, line ~228).
--   - AuditLog / Notification rows are already created explicitly in
--     FundWalletView, SendView and ExchangeView (wallet/views.py).
--
-- Running those triggers alongside the existing Django code would
-- create duplicate notification/audit rows for every transaction.
-- They are left out here on purpose so this file is safe to run
-- against the project's real database without changing its behavior.
-- The procedures, function, views and event below are additive only:
-- Django never calls them automatically, so they can't create
-- duplicates or side effects on their own.

-- =====================================================
-- 4. STORED PROCEDURES
-- =====================================================

-- 4a. Atomic SEND: moves funds between two wallets of the same currency.
DELIMITER //
CREATE PROCEDURE sp_send_funds(
    IN  p_sender_wallet   VARCHAR(40),
    IN  p_receiver_wallet VARCHAR(40),
    IN  p_amount          DECIMAL(24,8),
    IN  p_fee             DECIMAL(24,8),
    OUT p_transaction_id  VARCHAR(40)
)
proc_body: BEGIN
    DECLARE v_sender_balance DECIMAL(24,8);
    DECLARE v_sender_currency VARCHAR(10);
    DECLARE v_receiver_currency VARCHAR(10);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    SET p_transaction_id = UUID();

    START TRANSACTION;

    -- Lock the sender row so two simultaneous sends can't both pass the
    -- balance check (classic race condition in wallet systems).
    SELECT balance, currency_name INTO v_sender_balance, v_sender_currency
    FROM wallet WHERE wallet_id = p_sender_wallet FOR UPDATE;

    SELECT currency_name INTO v_receiver_currency
    FROM wallet WHERE wallet_id = p_receiver_wallet FOR UPDATE;

    IF v_sender_currency <> v_receiver_currency THEN
        ROLLBACK;
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Currency mismatch between wallets';
        LEAVE proc_body;
    END IF;

    IF v_sender_balance < (p_amount + p_fee) THEN
        ROLLBACK;
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Insufficient balance';
        LEAVE proc_body;
    END IF;

    UPDATE wallet SET balance = balance - (p_amount + p_fee) WHERE wallet_id = p_sender_wallet;
    UPDATE wallet SET balance = balance + p_amount WHERE wallet_id = p_receiver_wallet;

    INSERT INTO transaction (
        transaction_id, sender_wallet_id, receiver_wallet_id,
        transaction_type, amount, received_amount, fee, status
    ) VALUES (
        p_transaction_id, p_sender_wallet, p_receiver_wallet,
        'SEND', p_amount, p_amount, p_fee, 'COMPLETED'
    );

    COMMIT;
END //
DELIMITER ;

-- 4b. Atomic EXCHANGE: locks both wallet rows, checks balance, moves funds,
--     and inserts the transaction row -- all in one atomic unit.
--
--     The rate and transaction_id are passed IN (not looked up/generated
--     inside the procedure), because Django's get_rate() in views.py
--     already has richer rate-resolution logic than a plain table lookup
--     (direct row -> inverse row -> USD-bridge fallback). This procedure
--     is called FROM ExchangeView.post() in wallet/views.py: Python
--     resolves the rate and builds the transaction_id exactly as
--     Transaction.save() would, then this procedure does the locked,
--     atomic write.
DELIMITER //
CREATE PROCEDURE sp_exchange_funds(
    IN p_from_wallet    VARCHAR(40),
    IN p_to_wallet      VARCHAR(40),
    IN p_amount         DECIMAL(24,8),
    IN p_rate           DECIMAL(24,8),
    IN p_transaction_id VARCHAR(40)
)
proc_body: BEGIN
    DECLARE v_from_balance DECIMAL(24,8);
    DECLARE v_to_balance DECIMAL(24,8);
    DECLARE v_converted DECIMAL(24,8);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT balance INTO v_from_balance
    FROM wallet WHERE wallet_id = p_from_wallet FOR UPDATE;

    -- Lock the receiving wallet row too, so a concurrent exchange/send
    -- touching the same wallet can't interleave with this one.
    SELECT balance INTO v_to_balance
    FROM wallet WHERE wallet_id = p_to_wallet FOR UPDATE;

    IF v_from_balance < p_amount THEN
        ROLLBACK;
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Insufficient balance';
        LEAVE proc_body;
    END IF;

    SET v_converted = p_amount * p_rate;

    UPDATE wallet SET balance = balance - p_amount WHERE wallet_id = p_from_wallet;
    UPDATE wallet SET balance = balance + v_converted WHERE wallet_id = p_to_wallet;

    INSERT INTO transaction (
        transaction_id, sender_wallet_id, receiver_wallet_id,
        transaction_type, amount, received_amount, exchange_rate, status
    ) VALUES (
        p_transaction_id, p_from_wallet, p_to_wallet,
        'EXCHANGE', p_amount, v_converted, p_rate, 'COMPLETED'
    );

    COMMIT;
END //
DELIMITER ;

-- =====================================================
-- 5. FUNCTION
-- =====================================================

-- Convert an arbitrary amount between two currencies using the latest rate.
-- Returns NULL if no rate row exists for that pair.
DELIMITER //
CREATE FUNCTION fn_convert_amount(
    p_amount    DECIMAL(24,8),
    p_from_curr VARCHAR(10),
    p_to_curr   VARCHAR(10)
) RETURNS DECIMAL(24,8)
DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_rate DECIMAL(24,8);

    IF p_from_curr = p_to_curr THEN
        RETURN p_amount;
    END IF;

    SELECT rate INTO v_rate
    FROM exchange_rate
    WHERE from_curr = p_from_curr AND to_curr = p_to_curr
    LIMIT 1;

    RETURN p_amount * v_rate;
END //
DELIMITER ;

-- =====================================================
-- 6. VIEWS
-- =====================================================

-- 6a. Flattened wallet summary per user (used for dashboard-style reads).
CREATE OR REPLACE VIEW vw_user_wallet_summary AS
SELECT
    u.user_id,
    u.name,
    w.wallet_id,
    w.name        AS wallet_name,
    w.currency_name,
    c.type        AS currency_type,
    w.balance,
    w.wallet_status,
    w.is_default_receive
FROM `user` u
JOIN wallet w   ON w.user_id = u.user_id
JOIN currency c ON c.currency_name = w.currency_name
WHERE w.wallet_status = 'ACTIVE';

-- 6b. Transaction history with a running balance per wallet, using a
--     window function (SUM ... OVER) instead of a client-side loop.
CREATE OR REPLACE VIEW vw_wallet_transaction_history AS
SELECT
    t.transaction_id,
    t.sender_wallet_id,
    t.receiver_wallet_id,
    t.transaction_type,
    t.amount,
    t.fee,
    t.status,
    t.date,
    SUM(CASE
            WHEN t.sender_wallet_id = w.wallet_id THEN -(t.amount + t.fee)
            WHEN t.receiver_wallet_id = w.wallet_id THEN t.received_amount
            ELSE 0
        END) OVER (PARTITION BY w.wallet_id ORDER BY t.date
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_balance,
    w.wallet_id
FROM wallet w
JOIN transaction t
  ON w.wallet_id IN (t.sender_wallet_id, t.receiver_wallet_id);

-- 6c. Per-user monthly transaction volume, ranked with RANK() — another
--     window-function example, useful for an admin "top senders" report.
CREATE OR REPLACE VIEW vw_monthly_top_senders AS
SELECT
    u.user_id,
    u.name,
    DATE_FORMAT(t.date, '%Y-%m') AS month,
    SUM(t.amount) AS total_sent,
    RANK() OVER (PARTITION BY DATE_FORMAT(t.date, '%Y-%m')
                 ORDER BY SUM(t.amount) DESC) AS rank_in_month
FROM transaction t
JOIN wallet w  ON w.wallet_id = t.sender_wallet_id
JOIN `user` u  ON u.user_id = w.user_id
WHERE t.transaction_type = 'SEND'
GROUP BY u.user_id, u.name, DATE_FORMAT(t.date, '%Y-%m');

-- =====================================================
-- 7. EVENT (scheduled task)
-- =====================================================

SET GLOBAL event_scheduler = ON;

-- Nightly housekeeping: flag stale exchange rates so the app knows to
-- refresh them, instead of silently trading on day-old prices.
DELIMITER //
CREATE EVENT IF NOT EXISTS ev_flag_stale_rates
ON SCHEDULE EVERY 1 DAY
STARTS (CURRENT_DATE + INTERVAL 1 DAY)
DO
BEGIN
    INSERT INTO audit_log (action, remarks)
    SELECT 'STALE_RATE', CONCAT(from_curr, '->', to_curr, ' not updated in 24h')
    FROM exchange_rate
    WHERE last_updated < NOW() - INTERVAL 1 DAY;
END //
DELIMITER ;
