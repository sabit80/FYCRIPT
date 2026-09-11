UPDATE every row matching a raw
WHERE clause (caller supplies
    the clause + its params, e.g. 'user_id = %s AND is_default_receive = 1').
