"""Direct pyTigerGraph connection for ETL/setup scripts (not used by the agent)."""

import os

from pyTigerGraph import TigerGraphConnection

from config.settings import TG_GRAPHNAME, TG_HOST


def connect() -> TigerGraphConnection:
    if not TG_HOST:
        raise RuntimeError("TG_HOST is not set; fill in .env")
    secret = os.getenv("TG_SECRET", "")
    conn = TigerGraphConnection(
        host=TG_HOST,
        graphname=TG_GRAPHNAME,
        gsqlSecret=secret,
        username=os.getenv("TG_USERNAME", "tigergraph"),
        password=os.getenv("TG_PASSWORD", "tigergraph"),
        tgCloud=os.getenv("TG_TGCLOUD", "false").lower() == "true",
        restppPort=os.getenv("TG_RESTPP_PORT") or None,
        gsPort=os.getenv("TG_GS_PORT") or None,
        apiToken=os.getenv("TG_API_TOKEN", ""),
    )
    if secret and not os.getenv("TG_API_TOKEN"):
        conn.getToken(secret)
    return conn


def gsql_file(conn: TigerGraphConnection, path) -> str:
    text = open(path).read().replace("{GRAPH}", TG_GRAPHNAME)
    return conn.gsql(text)
