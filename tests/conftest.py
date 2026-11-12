import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.main import app


@pytest.fixture(scope="session")
def engine():
    url = os.getenv(
        "DATABASE_URL",
        "postgresql://fulfillops_user:secret_password@localhost:5433/fulfillops_db",
    )
    return create_engine(url, pool_pre_ping=True)


@pytest.fixture(autouse=True)
def clean_orders(engine):
    """Empty orders/jobs before each test (products are kept)."""
    with engine.begin() as c:
        c.execute(text("DELETE FROM outbox_jobs"))
        c.execute(text("DELETE FROM order_items"))
        c.execute(text("DELETE FROM orders"))
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sku(engine):
    """A seeded product reset to exactly 5 units of stock."""
    with engine.begin() as c:
        row = c.execute(
            text(
                "UPDATE products SET available = 5 "
                "WHERE sku = (SELECT min(sku) FROM products) RETURNING sku"
            )
        ).one()
    return row[0]
