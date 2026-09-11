SELECT id, role_name
FROM wallet_role
WHERE role_name = %s
LIMIT 1
