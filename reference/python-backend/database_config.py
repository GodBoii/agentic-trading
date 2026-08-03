# python-backend/database_config.py

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import config


def get_database_url() -> str:
    """
    Prefer a Postgres pooler URL when configured.

    Supabase exposes direct Postgres and pooler connection strings. With several
    Gunicorn workers and agent-created DB objects, the pooler keeps backend
    connection counts stable.
    """
    return config.DATABASE_POOLER_URL or config.DATABASE_URL


def get_sqlalchemy_database_url() -> str:
    """
    Return a SQLAlchemy psycopg2 URL for Agno's PostgresDb.
    """
    db_url = get_database_url()
    if not db_url:
        raise ValueError("DATABASE_URL or DATABASE_POOLER_URL must be set.")

    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)

    return _with_default_query_params(
        db_url,
        {
            "sslmode": "require",
            "connect_timeout": "10",
            "keepalives": "1",
            "keepalives_idle": "30",
            "keepalives_interval": "10",
            "keepalives_count": "5",
        },
    )


def _with_default_query_params(url: str, defaults: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in defaults.items():
        query.setdefault(key, value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
