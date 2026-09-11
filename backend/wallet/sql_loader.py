"""Load parameterised SQL statements from the project-level SQL directory."""

from functools import lru_cache
from pathlib import Path


# ``sql_loader.py`` lives at ``backend/wallet``; keeping SQL at the project
# root prevents application code from carrying database statements with it.
SQL_ROOT = Path(__file__).resolve().parents[2] / "database" / "raw_sql"


@lru_cache(maxsize=None)
def load_sql(query_name):
    """Return a named SQL statement stored in a .sql file.

    Query names use POSIX-style paths (for example, ``auth/is_blacklisted``)
    and are resolved relative to the project-level database/raw_sql directory.
    """
    if not query_name or query_name.startswith(("/", "\\")) or ".." in Path(query_name).parts:
        raise ValueError(f"Invalid SQL query name: {query_name!r}")

    query_path = (SQL_ROOT / f"{query_name}.sql").resolve()
    if SQL_ROOT.resolve() not in query_path.parents:
        raise ValueError(f"SQL query is outside the SQL directory: {query_name!r}")

    try:
        return query_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"SQL query file does not exist: database/raw_sql/{query_name}.sql"
        ) from exc
