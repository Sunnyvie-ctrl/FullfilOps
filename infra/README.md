# FulfillOps — Kubernetes & GitOps runbook (WP6)

Local `kind` cluster, 2 API + 2 worker replicas, deployed by Argo CD from `infra/k8s`.
Commands are PowerShell (Windows); they are the same on Linux/macOS.

## Layout

| File | What it is |
|---|---|
| `k8s/kustomization.yaml` | List of manifests + namespace `fulfillops` |
| `k8s/configmap.yaml` | Non-secret settings |
| `k8s/postgres.yaml` | PostgreSQL 16 StatefulSet + Service (sync-wave 0) |
| `k8s/migrate-job.yaml` | `alembic upgrade head` as an Argo CD Sync hook (wave 1) |
| `k8s/api.yaml` | API Deployment (2 replicas, probes, zero-downtime strategy) + Service (wave 2) |
| `k8s/worker.yaml` | Worker Deployment (2 replicas, heartbeat liveness probe) (wave 2) |
| `k8s/api-nodeport.yaml` | NodePort 30080 for the API (load-balanced across ready pods) |
| `k8s/prometheus.yaml` | Prometheus scraping annotated API pods (namespace-scoped RBAC) |
| `kind/kind-config.yaml` | kind cluster with host port mappings 8080/9090 |
| `argocd/application.yaml` | Argo CD Application pointing at `infra/k8s` on `main` |

The Secret `fulfillops-db` is **not** in Git; it is created by hand (step 3).

## 1. Create the cluster

```powershell
kind create cluster --name fulfillops --config infra/kind/kind-config.yaml
kubectl cluster-info --context kind-fulfillops
```

The config maps `localhost:8080` → API (NodePort 30080) and `localhost:9090` → Prometheus (NodePort 30090).

## 2. Build the images and load them into kind

kind cannot see images on your laptop's Docker, so they are copied in:

```powershell
docker compose build
kind load docker-image fulfillops-api:local fulfillops-worker:local --name fulfillops
```

## 3. Namespace + Secret (never committed)

```powershell
kubectl create namespace fulfillops
kubectl -n fulfillops create secret generic fulfillops-db `
  --from-literal=POSTGRES_USER=fulfillops_user `
  --from-literal=POSTGRES_PASSWORD=<choose-a-password>
```

## 4a. Quick test without Argo CD

```powershell
kubectl apply -k infra/k8s
kubectl -n fulfillops get pods -w      # Ctrl+C when api/worker are 1/1 Running
```

## 4b. GitOps with Argo CD

```powershell
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts `
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd rollout status deploy/argocd-server
kubectl apply -n argocd -f infra/argocd/application.yaml
```

Argo CD UI: `kubectl -n argocd port-forward svc/argocd-server 8443:443` then https://localhost:8443
(user `admin`, password:
`kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}"` then base64-decode it).

## 5. Reach the API and seed test data

No port-forward needed: `localhost:8080` reaches the API through the NodePort.

```powershell
kubectl -n fulfillops exec deploy/fulfillops-api -- python scripts/reset-test-data.py
curl.exe http://localhost:8080/health/ready
```

## Design notes

- **Zero downtime:** `maxUnavailable: 0` + `maxSurge: 1` keep 2 ready API pods during a rollout; the
  readiness probe (`/health/ready`) only lets traffic in once the DB is reachable; `preStop: sleep 5`
  gives the Service time to stop routing to a terminating pod.
- **Liveness vs readiness:** API liveness uses `/health/live` (no DB) so a DB outage does not cause a
  restart storm. The worker has no HTTP port, so it writes a heartbeat file every loop; liveness fails
  if it is older than 60 s (stuck loop).
- **Ordering:** sync-waves: postgres (0) → migrate Job (1) → api/worker (2).
- **Security:** all app pods run as UID 10001, `runAsNonRoot`, read-only root filesystem, no privilege
  escalation, all Linux capabilities dropped, `RuntimeDefault` seccomp. Postgres runs as UID 70.

## 6. Observability & zero-downtime drill (WP7)

See `docs/wp7-observability-drill.md`.
