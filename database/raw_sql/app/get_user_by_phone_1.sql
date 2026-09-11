SELECT id, password, last_login, is_superuser, first_name, last_name, is_staff, is_active, date_joined, email, name, phone, status, registration_date, transaction_pin_hash, two_factor_enabled, two_factor_secret, recovery_codes_hash, is_flagged, flagged_reason, flagged_at, referral_code, referred_by_id, account_type, business_name
FROM wallet_user
WHERE phone = %s
LIMIT 1
