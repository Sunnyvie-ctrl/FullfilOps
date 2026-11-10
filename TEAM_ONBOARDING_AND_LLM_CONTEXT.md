# FulfillOps - Team Onboarding & AI Context Guide

**Attention Teammates:** If you are using an AI assistant to help you with your assigned tasks, copy and paste this **entire document** into your first prompt. It gives the AI complete context of our architecture, current progress, and the strict capstone grading constraints.

---

## 🤖 SYSTEM PROMPT FOR AI ASSISTANT
If you are an AI reading this, your user is a student working on a 3-person team for a 9.5/10 difficulty University DevOps Capstone called **"FulfillOps"**. 
* **The Goal:** Build a highly resilient e-commerce API and asynchronous background worker that can survive high traffic, process crashes, and bad deployments without losing data or overselling inventory.
* **Tech Stack Locked:** Python 3.11+, FastAPI, PostgreSQL 16 (running locally on port 5433), SQLAlchemy 2.0, Alembic, Pytest.
* **Architecture Locked:** We are using the **Transactional Outbox Pattern** (a PostgreSQL `outbox_jobs` table) for our background queue. **DO NOT** suggest or implement Redis, RabbitMQ, Kafka, or Node.js.
* **Strict Constraints:** 
  1. No overselling (strict inventory `available >= 0` DB constraint).
  2. Cross-replica idempotency (`Idempotency-Key` unique DB constraint).
  3. At-least-once durable job processing (Worker must claim jobs safely, handle retries, and dead-letter queues).
  4. GitOps deployments via Argo CD on a local `kind` cluster.
  5. Security: No root Docker containers, no secrets in Git, no `.venv` in Git.

---

## 🏗️ 1. Project Current State (Person 1's Foundation)

Person 1 (Data & API Lead) has laid the foundation:
1. **Database Schema & Migrations:** Created `api/models.py` with `Product`, `Order`, `OrderItem`, and `OutboxJob`. Configured Alembic to manage database migrations.
2. **API Baseline:** Created `api/main.py` with FastAPI. It handles payload validation (max 16 KiB limit), idempotency checks via payload hashing, and atomic transaction locks (`SELECT ... FOR UPDATE`) to prevent overselling. 
3. **Local DB Infrastructure:** `compose.yaml` spins up PostgreSQL 16 on **port 5433** (changed from 5432 to prevent local conflicts).
4. **Seed Script:** `scripts/reset-test-data.py` safely wipes the DB and injects the 3 mandatory products required by the instructor's grading checker.

---

## 💻 2. Local Setup Instructions (For all team members)

To get your local development environment running, execute these steps in your terminal (Linux, macOS, or Windows WSL2):

```bash
# 1. Clone the repo and enter it
git clone <your-repo-url>
cd fulfillops

# 2. Create and activate a Python virtual environment (DO NOT commit this!)
python3 -m venv .venv
source .venv/bin/activate  # (On Windows WSL/Linux/macOS)

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the database (Exposed on port 5433)
docker compose up -d

# 5. Apply migrations and seed the database
alembic upgrade head
python scripts/reset-test-data.py

# 6. Run the API locally (to test)
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload