UPDATE wallet_kyc
SET verification_status = %s, reviewed_by_id = %s, reviewed_at = %s, admin_remarks = %s
WHERE id = %s
