INSERT one row. Returns the AUTO_INCREMENT id (lastrowid) for
    tables with an integer PK; for tables with an app-assigned string
    PK (wallet_id, transaction_id, ...) the caller already put that
    value in `fields`, so the return value can just be ignored.
