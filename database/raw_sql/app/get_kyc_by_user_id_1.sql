SELECT id, user_id, nid_number, passport_number, submission_date, verification_status, reviewed_by_id, reviewed_at, admin_remarks
FROM wallet_kyc
WHERE user_id = %s
LIMIT 1
