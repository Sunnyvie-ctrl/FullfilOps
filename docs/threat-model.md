# FulfillOps - System Threat Model & Security Architecture

This document outlines the STRIDE-aligned threat model for the FulfillOps e-commerce fulfillment and background worker pipeline. It identifies 5 critical threat vectors inherent to distributed job processing and details the defensive engineering controls implemented to mitigate them.

---

## 1. Threat Matrix Summary

| ID | Threat Vector | STRIDE Category | Severity | Primary Mitigation Control |
| :--- | :--- | :--- | :--- | :--- |
| **T-01** | Inventory Overselling via Concurrent Orders | Tampering / Race Condition | High | PostgreSQL Row-Level Locking (`SELECT ... FOR UPDATE`) |
| **T-02** | Idempotency Key Collisions / Payload Tampering | Spoofing / Tampering | Medium | SHA-256 Payload Hashing + Unique DB Constraint + HTTP 409 Conflict |
| **T-03** | Poison Jobs & Worker Crash Loops | Denial of Service | High | Outbox Pattern + Exponential Backoff + Dead-Letter Queue (`MAX_ATTEMPTS = 5`) |
| **T-04** | Container Escape & Privilege Escalation | Elevation of Privilege | High | Non-root execution (`UID 10001`), read-only root filesystem, dropped capabilities |
| **T-05** | Database Credential & Secret Leakage in Git | Information Disclosure | Critical | Environment variables (`.env`), Kubernetes Secrets, strict `.gitignore` & `.dockerignore` |

---

## 2. Detailed Threat Analysis & Mitigations

### T-01: Inventory Overselling via Concurrent Race Conditions
* **Description:** Multiple concurrent HTTP clients attempt to purchase the exact last remaining unit of an SKU simultaneously. Without synchronization, both read `available = 1`, resulting in overselling (`available = -1`).
* **STRIDE:** Tampering
* **Risk Level:** High
* **Mitigation:** 
  * The API executes stock verification and decrement inside an atomic PostgreSQL transaction using SQLAlchemy's `.with_for_update()`. 
  * Concurrent transactions attempting to modify the same `Product` row block sequentially, ensuring stock never drops below zero (enforced by database constraints).

### T-02: Idempotency Key Replay with Altered Payloads
* **Description:** A client re-uses an existing `Idempotency-Key` header but modifies the order body (e.g., changing quantities or SKUs) to exploit cached responses or bypass inventory checks.
* **STRIDE:** Spoofing / Tampering
* **Risk Level:** Medium
* **Mitigation:**
  * When an `Idempotency-Key` is received, the API computes a SHA-256 hash of the normalized JSON payload (`payload_hash`).
  * If the key exists but hashes do not match, the request is immediately rejected with **HTTP 409 Conflict (`IDEMPOTENCY_CONFLICT`)**, preventing tampering.

### T-03: Poison Jobs & Worker Crash Loops (Denial of Service)
* **Description:** A background job fails repeatedly due to downstream errors or malformed payload references, causing workers to loop infinitely or crash the background processing queue.
* **STRIDE:** Denial of Service (DoS)
* **Risk Level:** High
* **Mitigation:**
  * The **Transactional Outbox Pattern** ensures jobs are durably queued in PostgreSQL (`outbox_jobs`).
  * Workers claim jobs atomically using `SELECT ... FOR UPDATE SKIP LOCKED`.
  * Failed jobs enter an exponential backoff state (`BACKOFF_BASE = 2.0s`, capped at `300s`).
  * Upon reaching `MAX_ATTEMPTS = 5`, the job is transitioned to `"dead"` (dead-letter queue) and the corresponding `Order` status is explicitly marked as `"failed"`, protecting the queue from starvation.

### T-04: Container Escape & Privilege Escalation
* **Description:** An attacker discovers a remote code execution vulnerability in the FastAPI application and attempts to break out of the container namespace to compromise the host Kubernetes worker node.
* **STRIDE:** Elevation of Privilege
* **Risk Level:** High
* **Mitigation:**
  * **Non-Root Execution:** Both API and Worker Dockerfiles create and run under unprivileged user/group **`UID 10001`**. Kubernetes manifests explicitly set `runAsNonRoot: true`.
  * **Hardened Security Context:** Containers run with a read-only root filesystem (`readOnlyRootFilesystem: true`), dropped Linux capabilities (`capabilities: drop: ["ALL"]`), and `allowPrivilegeEscalation: false`.

### T-05: Database Credential & Secret Leakage in Git
* **Description:** Plaintext database passwords or API secrets are accidentally committed to version control, exposing the data store to unauthorized public access.
* **STRIDE:** Information Disclosure
* **Risk Level:** Critical
* **Mitigation:**
  * Zero hardcoded credentials: `compose.yaml` and Kubernetes manifests rely exclusively on environment variables and Kubernetes Secret objects (`fulfillops-db`).
  * `.gitignore` and `.dockerignore` strictly exclude `.env`, `.venv/`, and local credentials.
  * CI pipeline runs automated Trivy container scans failing on any HIGH/CRITICAL vulnerability or misconfiguration.

---