-- =====================================================
-- CryptoWallet — MySQL schema
--
-- This mirrors the tables Django's `makemigrations` /
-- `migrate` will generate from wallet/models.py. You do NOT
-- need to run this file if you're using Django migrations
-- (see backend/README.md) — it's provided as a plain-SQL
-- reference matching the ER diagram 1:1, and for anyone who
-- wants to stand the schema up without Django.
--
-- Requires MySQL 8.0.16+ (for CHECK constraint support).
-- =====================================================

SET NAMES utf8mb4;

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
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS role (
    role_id     BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    role_name   VARCHAR(50) UNIQUE NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS user_role (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id     BIGINT UNSIGNED NOT NULL,
    role_id     BIGINT UNSIGNED NOT NULL,
    assigned_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE (user_id, role_id),
    CONSTRAINT fk_user_role_user FOREIGN KEY (user_id) REFERENCES `user`(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_user_role_role FOREIGN KEY (role_id) REFERENCES role(role_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS kyc (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id             BIGINT UNSIGNED UNIQUE NOT NULL,
    nid_number          VARCHAR(50),
    passport_number     VARCHAR(50),
    submission_date     DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    verification_status VARCHAR(10) NOT NULL DEFAULT 'PENDING'
                         CHECK (verification_status IN ('PENDING','APPROVED','REJECTED')),
    CONSTRAINT fk_kyc_user FOREIGN KEY (user_id) REFERENCES `user`(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bank_account (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT UNSIGNED NOT NULL,
    bank_name       VARCHAR(100) NOT NULL,
    account_number  VARCHAR(50) NOT NULL,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE (user_id, account_number),
    CONSTRAINT fk_bank_account_user FOREIGN KEY (user_id) REFERENCES `user`(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS currency (
    currency_name   VARCHAR(10) PRIMARY KEY,
    type            VARCHAR(10) NOT NULL CHECK (type IN ('FIAT','CRYPTO')),
    symbol          VARCHAR(5) DEFAULT ''
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS wallet (
    wallet_id           VARCHAR(40) PRIMARY KEY,
    user_id             BIGINT UNSIGNED NOT NULL,
    currency_name       VARCHAR(10) NOT NULL,
    name                VARCHAR(100) NOT NULL,
    balance             DECIMAL(24,8) NOT NULL DEFAULT 0,
    wallet_status       VARCHAR(10) NOT NULL DEFAULT 'ACTIVE'
                         CHECK (wallet_status IN ('ACTIVE','FROZEN','CLOSED')),
    is_default_receive  BOOLEAN NOT NULL DEFAULT FALSE,
    default_receive_user_id BIGINT
        GENERATED ALWAYS AS (
            CASE WHEN is_default_receive = TRUE THEN user_id ELSE NULL END
        ) STORED,
    created_at          DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_wallet_user FOREIGN KEY (user_id) REFERENCES `user`(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_wallet_currency FOREIGN KEY (currency_name) REFERENCES currency(currency_name)
) ENGINE=InnoDB;
CREATE UNIQUE INDEX uq_wallet_one_default_receive
    ON wallet(default_receive_user_id);

-- MySQL has no partial/conditional unique index (no "WHERE" clause on
-- CREATE INDEX like PostgreSQL), so "exactly one default receive wallet
-- per user" can't be expressed as a single index here. It's enforced at
-- the application layer instead (see Wallet.save() in wallet/models.py,
-- which unsets any previous default before saving a new one).

CREATE TABLE IF NOT EXISTS crypto_address (
    address_id      VARCHAR(40) PRIMARY KEY,
    wallet_id       VARCHAR(40) NOT NULL,
    blockchain      VARCHAR(50) NOT NULL,
    public_address  VARCHAR(120) UNIQUE NOT NULL,
    CONSTRAINT fk_crypto_address_wallet FOREIGN KEY (wallet_id) REFERENCES wallet(wallet_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS exchange_rate (
    rate_id         BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    from_curr       VARCHAR(10) NOT NULL,
    to_curr         VARCHAR(10) NOT NULL,
    rate            DECIMAL(24,8) NOT NULL,
    last_updated    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE (from_curr, to_curr),
    CONSTRAINT fk_exchange_rate_from FOREIGN KEY (from_curr) REFERENCES currency(currency_name),
    CONSTRAINT fk_exchange_rate_to FOREIGN KEY (to_curr) REFERENCES currency(currency_name)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS transaction (
    transaction_id      VARCHAR(40) PRIMARY KEY,
    sender_wallet_id     VARCHAR(40),
    receiver_wallet_id   VARCHAR(40),
    transaction_type     VARCHAR(10) NOT NULL
                          CHECK (transaction_type IN ('SEND','RECEIVE','SHIFT','EXCHANGE','DEPOSIT')),
    amount               DECIMAL(24,8) NOT NULL,
    received_amount       DECIMAL(24,8),
    fee                  DECIMAL(24,8) NOT NULL DEFAULT 0,
    exchange_rate         DECIMAL(24,8),
    status               VARCHAR(10) NOT NULL DEFAULT 'COMPLETED'
                          CHECK (status IN ('PENDING','COMPLETED','FAILED')),
    date                 DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_txn_sender FOREIGN KEY (sender_wallet_id) REFERENCES wallet(wallet_id) ON DELETE SET NULL,
    CONSTRAINT fk_txn_receiver FOREIGN KEY (receiver_wallet_id) REFERENCES wallet(wallet_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS notification (
    notification_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id          BIGINT UNSIGNED NOT NULL,
    message          VARCHAR(255) NOT NULL,
    type             VARCHAR(15) NOT NULL DEFAULT 'INFO'
                     CHECK (type IN ('INFO','TRANSACTION','SECURITY')),
    read_status      BOOLEAN NOT NULL DEFAULT FALSE,
    timestamp        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_notification_user FOREIGN KEY (user_id) REFERENCES `user`(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS audit_log (
    log_id      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id     BIGINT UNSIGNED,
    action      VARCHAR(100) NOT NULL,
    remarks     VARCHAR(255),
    ip_address  VARCHAR(45),
    timestamp   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_auditlog_user FOREIGN KEY (user_id) REFERENCES `user`(user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS admin_audit_event (
    event_id CHAR(36) PRIMARY KEY, actor_id BIGINT UNSIGNED,
    action VARCHAR(100) NOT NULL, resource_type VARCHAR(60) NOT NULL,
    resource_id VARCHAR(100) NOT NULL DEFAULT '', metadata JSON NOT NULL,
    ip_address VARCHAR(45), created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    previous_hash CHAR(64) NOT NULL DEFAULT '', event_hash CHAR(64) NOT NULL UNIQUE,
    CONSTRAINT fk_admin_audit_actor FOREIGN KEY (actor_id) REFERENCES `user`(user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS dispute (
    dispute_id VARCHAR(40) PRIMARY KEY, transaction_id VARCHAR(40) NOT NULL,
    claimant_id BIGINT UNSIGNED NOT NULL, reason VARCHAR(255) NOT NULL,
    amount DECIMAL(24,8) NOT NULL, currency VARCHAR(10) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN', resolution TEXT NOT NULL,
    resolved_by_id BIGINT UNSIGNED, created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), resolved_at DATETIME(6),
    CONSTRAINT fk_dispute_transaction FOREIGN KEY (transaction_id) REFERENCES transaction(transaction_id) ON DELETE RESTRICT,
    CONSTRAINT fk_dispute_claimant FOREIGN KEY (claimant_id) REFERENCES `user`(user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_dispute_resolver FOREIGN KEY (resolved_by_id) REFERENCES `user`(user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS fee_limit_config (
    config_key VARCHAR(80) PRIMARY KEY, scope VARCHAR(30) NOT NULL DEFAULT 'GLOBAL',
    fee_percent DECIMAL(8,4) NOT NULL DEFAULT 0, fixed_fee DECIMAL(24,8) NOT NULL DEFAULT 0,
    daily_limit DECIMAL(24,8), monthly_limit DECIMAL(24,8), max_transaction DECIMAL(24,8),
    is_active BOOLEAN NOT NULL DEFAULT TRUE, updated_by_id BIGINT UNSIGNED,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_fee_limit_actor FOREIGN KEY (updated_by_id) REFERENCES `user`(user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS wallet_reserve_snapshot (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, currency VARCHAR(10) NOT NULL,
    total_customer_balance DECIMAL(30,8) NOT NULL DEFAULT 0,
    reserve_balance DECIMAL(30,8) NOT NULL DEFAULT 0,
    available_liquidity DECIMAL(30,8) NOT NULL DEFAULT 0,
    captured_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    captured_by_id BIGINT UNSIGNED,
    CONSTRAINT fk_reserve_actor FOREIGN KEY (captured_by_id) REFERENCES `user`(user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

DELIMITER //
CREATE TRIGGER trg_admin_audit_no_update
BEFORE UPDATE ON admin_audit_event
FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'admin audit events are immutable';
END //
CREATE TRIGGER trg_admin_audit_no_delete
BEFORE DELETE ON admin_audit_event
FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'admin audit events are immutable';
END //
DELIMITER ;

CREATE TABLE IF NOT EXISTS login_session (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id     BIGINT UNSIGNED NOT NULL,
    ip_address  VARCHAR(45),
    device_info VARCHAR(255),
    login_time  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_login_session_user FOREIGN KEY (user_id) REFERENCES `user`(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE INDEX idx_wallet_user ON wallet(user_id);
CREATE INDEX idx_transaction_sender ON transaction(sender_wallet_id);
CREATE INDEX idx_transaction_receiver ON transaction(receiver_wallet_id);
CREATE INDEX idx_notification_user ON notification(user_id);
CREATE INDEX idx_auditlog_user ON audit_log(user_id);


-- =====================================================
-- Seed reference data
-- =====================================================

INSERT IGNORE INTO currency (currency_name, type, symbol) VALUES
    ('USD','FIAT','$'), ('BDT','FIAT','৳'), ('EUR','FIAT','€'), ('GBP','FIAT','£'),
    ('BTC','CRYPTO','₿'), ('ETH','CRYPTO','Ξ'), ('USDT','CRYPTO','₮');

INSERT IGNORE INTO role (role_name) VALUES
    ('USER'), ('ADMIN'), ('OPERATIONS'), ('SUPPORT'), ('COMPLIANCE'), ('FINANCE');
