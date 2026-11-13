# FulfillOps - System Architecture and Design Document

## 1. System Overview
FulfillOps is a high-throughput, highly resilient e-commerce order intake and asynchronous fulfillment engine. Designed to withstand network partitions, process crashes, and high-concurrency traffic spikes without data loss or inventory overselling, the system is architected around Python 3.11, FastAPI, SQLAlchemy 2.0, PostgreSQL 16, and Kubernetes GitOps via Argo CD.

---

## 2. High-Level Component Flow Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant API as FastAPI (API Replica)
    participant DB as PostgreSQL 16
    participant Worker as Background Worker

    Client->>API: POST /api/v1/orders (Idempotency-Key, Payload)
    Note over API,DB: 1. Idempotency Check & Hash Validation
    API->>DB: Check idempotency_key uniqueness
    alt Duplicate Key & Identical Payload
        DB-->>API: Return existing order
        API-->>Client: HTTP 202 Accepted (queued)
    else Duplicate Key & Different Payload
        API-->>Client: HTTP 409 Conflict
    else New Valid Order
        Note over API,DB: 2. Atomic Transaction Block
        API->>DB: BEGIN TRANSACTION
        API->>DB: SELECT available FROM products WHERE sku IN (...) FOR UPDATE
        Note over DB: Locks product rows to prevent overselling
        API->>DB: Decrement product inventory (available >= 0)
        API->>DB: INSERT INTO orders (status = 'queued')
        API->>DB: INSERT INTO order_items (...)
        API->>DB: INSERT INTO outbox_jobs (status = 'pending')
        API->>DB: COMMIT TRANSACTION
        API-->>Client: HTTP 202 Accepted {"order_id": "...", "status": "queued"}
    end

    Note over Worker,DB: 3. Asynchronous Polling & Worker Loop
    Worker->>DB: SELECT ... FROM outbox_jobs WHERE status='pending' FOR UPDATE SKIP LOCKED
    DB-->>Worker: Claim batch of pending jobs (status = 'processing')
    Worker->>DB: UPDATE orders SET status = 'processing'
    Note over Worker: Execute business fulfillment logic
    alt Fulfillment Success
        Worker->>DB: UPDATE orders SET status = 'completed', outbox_jobs SET status = 'done'
        Worker->>DB: COMMIT
    else Fulfillment Failure (Exception)
        Worker->>DB: ROLLBACK & apply exponential backoff (pending)
        Note over Worker: If attempts >= MAX_ATTEMPTS (5): status = 'dead', order status = 'failed'
    end
```
---

## 3. Core Architectural Patterns

### A. The Transactional Outbox Pattern
To guarantee at-least-once durable background processing without introducing external message brokers like Redis, RabbitMQ, or Kafka, FulfillOps implements the Transactional Outbox Pattern. Writing to a database and publishing an event to a queue in two separate steps introduces classic distributed systems failure modes, such as a successful database commit followed by a dropped network connection before queue publication. 

Our solution writes the order, order items, inventory decrement, and an outbox job record into a single atomic PostgreSQL transaction. If any part fails, the entire transaction rolls back. A background worker periodically polls the outbox table to drive asynchronous completion.

### B. Concurrency Control and Row-Level Locking
To prevent race conditions where multiple concurrent clients purchase the last remaining items simultaneously, the API acquires an explicit row-level lock using SQLAlchemy's with_for_update method on the products table. Transactions queue sequentially, guaranteeing that available stock never drops below zero, enforced by database constraints.

With multiple worker replicas polling simultaneously, duplication must be prevented. Workers utilize SELECT ... FOR UPDATE SKIP LOCKED. When Worker 1 claims a batch of pending jobs, PostgreSQL immediately locks those rows and instructs Worker 2 to skip them and look for other available work, eliminating race conditions and double-processing.

### C. Cross-Replica Idempotency
Clients retrying failed network requests can bombard the API with duplicate orders. Every request requires a valid Idempotency-Key header between 8 and 128 characters. The API computes a SHA-256 hash of the normalized JSON payload. If a request arrives with an existing key and matching hash, it safely replays the original 202 Accepted response without re-deducting inventory. If the key matches but the payload differs, it rejects the request with HTTP 409 Conflict.

---

## 4. Deployment and Infrastructure Topology

FulfillOps runs inside a localized Kubernetes cluster managed via GitOps:
- PostgreSQL 16 StatefulSet: Provides a persistent volume and a reliable database endpoint.
- Alembic Migration Job: An Argo CD synchronization hook that runs database migrations before application code starts.
- API and Worker Deployments: Two replicas each, configured with a zero-downtime rolling update strategy, liveness probes, and readiness probes verifying database connectivity.
- Security Hardening: All application containers run as unprivileged user and group UID 10001, with read-only root filesystems, dropped Linux capabilities, and no privilege escalation.

