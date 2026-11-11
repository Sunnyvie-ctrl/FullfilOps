import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy import text

from api.main import app

ORDERS = "/api/v1/orders"


def body(sku, qty=1):
    return {"customer_id": "cust-1", "items": [{"sku": sku, "quantity": qty}]}


def hdr(key=None):
    return {"Idempotency-Key": key or str(uuid.uuid4())}


def stock(engine, sku):
    with engine.connect() as c:
        return c.execute(
            text("SELECT available FROM products WHERE sku=:s"), {"s": sku}
        ).scalar()


def order_count(engine):
    with engine.connect() as c:
        return c.execute(text("SELECT count(*) FROM orders")).scalar()


def test_health(client):
    assert client.get("/health/live").status_code == 200


def test_catalog_lists_products(client):
    r = client.get("/api/v1/catalog")
    assert r.status_code == 200


def test_create_order_returns_202(client, sku):
    r = client.post(ORDERS, json=body(sku), headers=hdr())
    assert r.status_code == 202
    assert r.json()["status"] == "queued"


def test_order_creates_outbox_job(client, sku, engine):
    client.post(ORDERS, json=body(sku), headers=hdr())
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM outbox_jobs")).scalar() == 1


def test_missing_idempotency_key_is_400(client, sku):
    assert client.post(ORDERS, json=body(sku)).status_code == 400


def test_short_idempotency_key_is_400(client, sku):
    assert client.post(ORDERS, json=body(sku), headers=hdr("short")).status_code == 400


def test_unknown_sku_is_422(client):
    r = client.post(ORDERS, json=body("NOPE-SKU"), headers=hdr())
    assert r.status_code == 422


def test_oversized_payload_rejected(client, sku):
    big = body(sku)
    big["note"] = "x" * 20_000
    r = client.post(ORDERS, json=big, headers=hdr())
    assert r.status_code in (400, 413, 422)


def test_same_key_same_payload_replays(client, sku, engine):
    key = str(uuid.uuid4())
    r1 = client.post(ORDERS, json=body(sku), headers=hdr(key))
    r2 = client.post(ORDERS, json=body(sku), headers=hdr(key))
    assert r1.status_code == r2.status_code == 202
    assert r1.json()["order_id"] == r2.json()["order_id"]
    assert order_count(engine) == 1
    assert stock(engine, sku) == 4  # stock taken only once


def test_same_key_different_payload_is_409(client, sku):
    key = str(uuid.uuid4())
    client.post(ORDERS, json=body(sku, 1), headers=hdr(key))
    r = client.post(ORDERS, json=body(sku, 2), headers=hdr(key))
    assert r.status_code == 409


def test_out_of_stock_is_409(client, sku, engine):
    r = client.post(ORDERS, json=body(sku, 6), headers=hdr())
    assert r.status_code == 409
    assert stock(engine, sku) == 5


def test_get_order(client, sku):
    oid = client.post(ORDERS, json=body(sku), headers=hdr()).json()["order_id"]
    r = client.get(f"{ORDERS}/{oid}")
    assert r.status_code == 200 and r.json()["order_id"] == oid


def test_get_unknown_order_is_404(client):
    assert client.get(f"{ORDERS}/{uuid.uuid4()}").status_code == 404


def test_race_identical_idempotency_key(sku, engine):
    """10 simultaneous requests, SAME key -> exactly one order, stock taken once."""
    n, key = 10, str(uuid.uuid4())
    barrier = Barrier(n)

    def fire(_):
        with TestClient(app) as c:
            barrier.wait()
            return c.post(ORDERS, json=body(sku), headers=hdr(key)).status_code

    with ThreadPoolExecutor(max_workers=n) as pool:
        codes = list(pool.map(fire, range(n)))

    assert all(c in (202, 409) for c in codes), codes  # never a 5xx
    assert 202 in codes
    assert order_count(engine) == 1
    assert stock(engine, sku) == 4


def test_race_no_overselling_with_distinct_keys(sku, engine):
    """20 simultaneous orders (different keys) for 5 units -> exactly 5 succeed."""
    n = 20
    barrier = Barrier(n)

    def fire(_):
        with TestClient(app) as c:
            barrier.wait()
            return c.post(ORDERS, json=body(sku), headers=hdr()).status_code

    with ThreadPoolExecutor(max_workers=n) as pool:
        codes = list(pool.map(fire, range(n)))

    assert codes.count(202) == 5, codes
    assert stock(engine, sku) == 0
