# FulfillOps: The Resilient Order-Processing Platform

**Final DevOps Capstone Project**  
**Institution:** EPITA | **Course:** DevOps | **Academic Year:** 2026–2027  
**Team:** Yah  
* **BUI Minh Nhat** (WP1 - Architecture & Core API)  
* **Manda Adithya Reddy** (WP2, WP3, WP4 - Background Workers, Testing & CI/CD)  
* **Hassan Raza** (WP5, WP6, WP7 - Containers, Kubernetes/GitOps & Observability)  

---

## 1. Project Overview
**FulfillOps** is a resilient, event-driven order-processing platform designed for electronics fulfillment. The system guarantees atomic inventory reservations, cross-replica idempotency, and durable asynchronous task execution even under network partitions, concurrent request spikes, and infrastructure restarts.

### Key Technical Features
* **Strict API Contract:** Fully compliant with `API_CONTRACT_EN.md` using FastAPI and PostgreSQL 16.
* **Concurrency Control & Idempotency:** PostgreSQL row-level locking with `SELECT ... FOR UPDATE SKIP LOCKED` and unique idempotency keys preventing double-booking and negative stock.
* **Asynchronous Outbox Workers:** Durable background processing with exponential backoff retries and dead-letter queue (DLQ) handling.
* **Container Security:** Multi-stage, non-root Docker builds (`runAsNonRoot: true`, user `10001`) with dropped Linux capabilities.
* **Kubernetes & GitOps:** Automated cluster management via `kind` and continuous reconciliation through Argo CD (`selfHeal: true`).
* **Supply-Chain Integrity & CI/CD:** GitHub Actions workflows enforcing linting, pytest, Syft SBOM generation, and Trivy vulnerability scanning.
* **Observability:** Prometheus metrics exposition (`/metrics`) and Kubernetes liveness/readiness probes.

---

## 2. Installation and Launching Guide

### 2.1 Prerequisites
Ensure you have the following tools installed on your local machine:
* Git
* Docker Desktop / Docker Engine
* Python 3.11+ and pip
* `kubectl` and `kind` (if running the Kubernetes deployment)

---

### 2.2 Clone the Repository
```bash
git clone https://github.com/Sunnyvie-ctrl/FullfilOps.git
cd FullfilOps
```

---

### 2.3 Option A: Running Locally via Docker Compose (Fastest)
*Use this method to run the API, workers, and PostgreSQL locally using Docker containers.*

1. **Build and start the containers:**
   ```bash
   docker compose up -d --build
   ```
2. **Verify container health:**
   ```bash
   docker compose ps
   ```
3. **Shut down the stack** (without destroying database persistent volumes):
   ```bash
   docker compose down
   ```

---

### 2.4 Option B: Running via Kubernetes (`kind`) & Argo CD GitOps
*Use this method to test the production-grade Kubernetes manifests and GitOps reconciliation loop locally.*

1. **Create a local `kind` cluster:**
   ```bash
   kind create cluster --name fulfillops
   ```
2. **Build your local Docker images and load them into `kind`:**
   ```bash
   docker build -t fulfillops-api:local -f api/Dockerfile .
   docker build -t fulfillops-worker:local -f worker/Dockerfile .
   
   kind load docker-image fulfillops-api:local --name fulfillops
   kind load docker-image fulfillops-worker:local --name fulfillops
   ```
3. **Deploy the Argo CD application manifest:**
   ```bash
   kubectl apply -n argocd -f infra/argocd/application.yaml
   ```
4. **Verify pod health:**
   ```bash
   kubectl get pods -n fulfillops
   ```

### 2.4 (Supplement) Handling Kubernetes Secrets in GitOps
Because production secrets (`secret.yaml`) contain sensitive credentials, they are excluded from version control via `.gitignore`. 

If you are deploying via Kubernetes and Argo CD:
1. **Copy the example template to create your local secret:**
   ```bash
   cp infra/k8s/secret.example.yaml infra/k8s/secret.yaml
   ```
2. **Edit `infra/k8s/secret.yaml`** and replace the placeholder values with your actual database passwords and credentials.
3. **Apply the secret directly to your cluster** BEFORE Argo CD syncs the application (since `secret.yaml` is git-ignored and excluded from `kustomization.yaml`):
   ```bash
   kubectl apply -f infra/k8s/secret.yaml
   ```
4. **Ensure `secret.yaml` is NOT listed in `infra/k8s/kustomization.yaml`** under `resources:`, preventing Argo CD from throwing a manifest generation error.

---

### 2.5 Database Migrations and Test Seeding
Set up your Python virtual environment to run database migrations and populate the required test SKUs (`KIT-100`, `PART-200`, `PACK-300`):

```bash
# Create and activate virtual environment
python -m venv .venv
# On Windows PowerShell:
.venv\Scripts\Activate
# On Mac/Linux:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations and seed test data
python scripts/reset-test-data.py
```

---

### 2.6 Running Tests and Public Verification
Execute the automated test suite and validate system correctness against the official public checker:

1. **Run the unit and integration test suite:**
   ```bash
   python -m pytest -v
   ```
2. **Run the public test checker** (ensures all 15 assertions pass under concurrency and stress):
   ```bash
   python fulfillops_public_checker.py --base-url http://localhost:8080 --concurrency --stress
   ```

---

### 2.7 Accessing Argo CD and Prometheus UIs (Kubernetes Mode)
If you deployed the application via Kubernetes (`kind`), you can port-forward the management dashboards locally to inspect reconciliation health and metrics:

#### 1. Argo CD Dashboard (GitOps Controller)
* **Port-forward the Argo CD server:**
  ```bash
  kubectl port-forward svc/argocd-server -n argocd 8081:443
  ```
* Open your browser and navigate to: `https://localhost:8081`
* **Default Username:** `admin`
* **Retrieve the Initial Admin Password:**
  ```bash
  kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath="{.data.password}" | base64 -d
  ```

#### 2. Prometheus Observability Dashboard
* **Port-forward the Prometheus service:**
  ```bash
  kubectl port-forward svc/prometheus -n fulfillops 9090:9090
  ```
  *(Note: If your service name differs, you can port-forward directly to the pod: `kubectl port-forward pod/<prometheus-pod-name> -n fulfillops 9090:9090`)*
* Open your browser and navigate to: `http://localhost:9090` to inspect scraped metrics and alert rules.

---

## 3. Project Documentation
Detailed engineering documentation is available under the `/docs` directory:
* [System Architecture (`architecture.md`)](docs/architecture.md)
* [Architecture Decision Record (`ADR-001.md`)](docs/ADR-001.md)
* [Threat Model (`threat-model.md`)](docs/threat-model.md)
* [Assistance & Development Log (`assistance-log.md`)](docs/assistance-log.md)