import os
import uuid
import hashlib
import json
from typing import List
from fastapi import FastAPI, Header, Request, HTTPException, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, conlist, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import time

from .models import Base, Product, Order, OrderItem, OutboxJob

# --- Setup & Database ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fulfillops_user:secret_password@localhost:5433/fulfillops_db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI(title="FulfillOps API")

# --- Metrics ---
HTTP_REQUESTS = Counter("fulfillops_http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
ORDERS_CREATED = Counter("fulfillops_orders_created_total", "Total orders accepted")
ORDERS_FAILED = Counter("fulfillops_orders_failed_total", "Total order failures (API rejections)")
REQUEST_LATENCY = Histogram("fulfillops_http_request_duration_seconds", "HTTP request latency", ["endpoint"])

WORKER_RETRIES = Counter("fulfillops_worker_retries_total", "Total worker retries")


class ItemRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0, le=20)

class OrderRequest(BaseModel):
    customer_id: str = Field(..., min_length=1, max_length=64)
    items: conlist(ItemRequest, min_length=1, max_length=10)

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def json_error(code: str, message: str, status_code: int):
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Return our {"error": {...}} shape instead of FastAPI's default {"detail": [...]}."""
    errors = exc.errors()
    if any(err.get("loc", ())[-1:] == ("quantity",) for err in errors):
        code, message = "INVALID_QUANTITY", "Each item quantity must be between 1 and 20"
    else:
        code, message = "INVALID_REQUEST", "Request body failed validation"
    return json_error(code, message, 422)

@app.middleware("http")
async def process_request(request: Request, call_next):
    start_time = time.time()

    content_length = request.headers.get('content-length')
    if content_length and int(content_length) > 16384:
        return json_error("INVALID_REQUEST", "Request body exceeds 16 KiB limit", 400)
        
    response = await call_next(request)
    
    duration = time.time() - start_time
    route_path = request.url.path
    HTTP_REQUESTS.labels(method=request.method, endpoint=route_path, status=response.status_code).inc()
    REQUEST_LATENCY.labels(endpoint=route_path).observe(duration)
    
    return response


@app.get("/health/live")
def live():
    return {"status": "ok"}

@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})

@app.get("/api/v1/catalog")
def get_catalog():
    return {"products": [
        {"sku": "KIT-100", "unit_price_cents": 1299},
        {"sku": "PART-200", "unit_price_cents": 599},
        {"sku": "PACK-300", "unit_price_cents": 249}
    ]}

@app.get("/api/v1/inventory/{sku}")
def get_inventory(sku: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.sku == sku).first()
    if not product:
        return json_error("SKU_NOT_FOUND", "Product not found", 404)
    return {"sku": product.sku, "available": product.available}

@app.post("/api/v1/orders")
async def create_order(
    request: Request,
    order_req: OrderRequest, 
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db)
):
    if not idempotency_key or not (8 <= len(idempotency_key) <= 128):
        ORDERS_FAILED.inc()
        return json_error("IDEMPOTENCY_REQUIRED", "Valid Idempotency-Key header is required", 400)

    raw_body = await request.body()
    try:
        parsed_json = json.loads(raw_body)
        normalized_payload = json.dumps(parsed_json, sort_keys=True)
    except json.JSONDecodeError:
        ORDERS_FAILED.inc()
        return json_error("INVALID_JSON", "Invalid JSON body", 400)

    payload_hash = hashlib.sha256(normalized_payload.encode('utf-8')).hexdigest()

    existing_order = db.query(Order).filter(Order.idempotency_key == idempotency_key).first()
    if existing_order:
        if existing_order.payload_hash == payload_hash:
            return JSONResponse(status_code=202, content={"order_id": str(existing_order.id), "status": "queued"})
        ORDERS_FAILED.inc()
        return json_error("IDEMPOTENCY_CONFLICT", "Idempotency key used with different payload", 409)

    aggregated_items = {}
    for item in order_req.items:
        aggregated_items[item.sku] = aggregated_items.get(item.sku, 0) + item.quantity

    try:
        products = db.query(Product).filter(Product.sku.in_(aggregated_items.keys())).with_for_update().all()
        product_map = {p.sku: p for p in products}

        total_cents = 0

        for sku, qty in aggregated_items.items():
            if sku not in product_map:
                db.rollback()
                ORDERS_FAILED.inc()
                return json_error("INVALID_SKU", f"SKU not found: {sku}", 422)
            if product_map[sku].available < qty:
                db.rollback()
                ORDERS_FAILED.inc()
                return json_error("OUT_OF_STOCK", f"Not enough stock for {sku}", 409)

            product_map[sku].available -= qty
            total_cents += product_map[sku].unit_price_cents * qty

        new_order = Order(
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            customer_id=order_req.customer_id,
            total_cents=total_cents
        )
        db.add(new_order)
        db.flush() 

        for sku, qty in aggregated_items.items():
            db.add(OrderItem(order_id=new_order.id, sku=sku, quantity=qty))

        db.add(OutboxJob(order_id=new_order.id))

        db.commit()
        ORDERS_CREATED.inc()
        return JSONResponse(status_code=202, content={"order_id": str(new_order.id), "status": "queued"})

    except IntegrityError:
        db.rollback()
        ORDERS_FAILED.inc()
        return json_error("IDEMPOTENCY_CONFLICT", "Simultaneous idempotency conflict", 409)
    except Exception as e:
        db.rollback()
        ORDERS_FAILED.inc()
        return json_error("INVALID_REQUEST", str(e), 400)

@app.get("/api/v1/orders/{order_id}")
def get_order(order_id: str, db: Session = Depends(get_db)):
    # Order ids are UUIDs: anything else can't exist, and passing it to
    # PostgreSQL would raise a type error (HTTP 500) instead of a clean 404.
    try:
        order_uuid = uuid.UUID(order_id)
    except ValueError:
        return json_error("ORDER_NOT_FOUND", "Order not found", 404)
    order = db.query(Order).filter(Order.id == order_uuid).first()
    if not order:
        return json_error("ORDER_NOT_FOUND", "Order not found", 404)
    return {"order_id": str(order.id), "status": order.status, "total_cents": order.total_cents}

@app.get("/metrics")
def get_metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

from sqlalchemy import text