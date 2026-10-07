"""Database fixtures.

DB tests need a Postgres with PostGIS. Point TEST_DATABASE_URL at an admin connection, e.g.
    TEST_DATABASE_URL=postgresql://postgres:dev@localhost:54329/postgres
Each session creates its own throwaway database and drops it afterwards, so tests can never
touch existing data. Without the variable, DB tests are skipped.
"""

import os
import uuid
from contextlib import contextmanager

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from biodiv.workers.migrate import migrate

ADMIN_URL = os.environ.get("TEST_DATABASE_URL")


@contextmanager
def temp_database():
    if not ADMIN_URL:
        pytest.skip("TEST_DATABASE_URL not set (needs Postgres with PostGIS)")
    name = f"biodiv_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')
    try:
        yield make_conninfo(ADMIN_URL, dbname=name)
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'drop database "{name}" with (force)')


@pytest.fixture(scope="session")
def db_url():
    """A fully migrated and seeded database, shared by the session."""
    with temp_database() as url:
        migrate(url, seed=True)
        yield url


@pytest.fixture
def empty_db_url():
    """A brand-new database with nothing applied."""
    with temp_database() as url:
        yield url


@pytest.fixture
def conn(db_url):
    """A connection whose work is rolled back after each test."""
    with psycopg.connect(db_url) as c:
        yield c
        c.rollback()


@pytest.fixture
def ingest_db_url():
    """A private, migrated and seeded database, for tests that write real data."""
    with temp_database() as url:
        migrate(url, seed=True)
        yield url
