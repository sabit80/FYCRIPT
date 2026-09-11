SELECT DISTINCT gp.group_payment_id
FROM wallet_grouppayment gp
LEFT JOIN wallet_grouppaymentparticipant p ON p.group_payment_id = gp.group_payment_id
WHERE gp.organizer_id = %s OR p.user_id = %s
ORDER BY gp.created_at DESC
