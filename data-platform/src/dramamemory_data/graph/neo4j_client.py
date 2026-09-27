"""Thin Neo4j driver wrapper. Imported inside tasks only (keeps DAG parsing driver-free)."""

from __future__ import annotations

import os
from typing import Any


def connect():
    from neo4j import GraphDatabase

    uri = os.environ["DRAMAMEMORY_NEO4J_URI"]
    user = os.environ.get("DRAMAMEMORY_NEO4J_USER", "neo4j")
    password = os.environ["DRAMAMEMORY_NEO4J_PASSWORD"]
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver


def run_write(driver, statements: list[tuple[str, dict[str, Any]]]) -> None:
    """All statements in one write transaction (an aggregate is all-or-nothing)."""

    def work(tx):
        for cypher, params in statements:
            tx.run(cypher, **params)

    with driver.session() as session:
        session.execute_write(work)


def run_single(driver, cypher: str, **params) -> Any:
    with driver.session() as session:
        record = session.run(cypher, **params).single()
        return record[0] if record else None


def run_rows(driver, cypher: str, **params) -> list[dict[str, Any]]:
    with driver.session() as session:
        return [r.data() for r in session.run(cypher, **params)]
