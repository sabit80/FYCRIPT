SELECT r.role_name
FROM wallet_userrole ur
JOIN wallet_role r ON r.id = ur.role_id
WHERE ur.user_id = %s
