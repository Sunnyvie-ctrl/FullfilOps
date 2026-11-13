# WP7 — Observability & zero-downtime GitOps rollout drill

Owner: Hassan (Platform & Ops). Goal: prove that an Argo CD rolling update of the API
causes **zero failed requests**, measured with the instructor's `fulfillops_rollout_probe.py`,
and that Prometheus scrapes `/metrics` from every API replica.

## How zero downtime is achieved

| Mechanism | Where | Effect |
|---|---|---|
| `maxSurge: 1`, `maxUnavailable: 0` | `infra/k8s/api.yaml` | A new pod is added before an old one is removed: never fewer than 2 ready pods. |
| Readiness probe `/health/ready` | `api.yaml` | A new pod gets traffic only after it can reach the DB. |
| `preStop: sleep 5` | `api.yaml` | A terminating pod keeps serving while the Service stops routing to it. |
| uvicorn graceful shutdown on SIGTERM | image `CMD` | In-flight requests finish before exit. |
| NodePort `30080` → `localhost:8080` | `api-nodeport.yaml`, `infra/kind/kind-config.yaml` | The probe goes through the Service (all ready pods), not a single-pod `port-forward`. |

> Why not `kubectl port-forward`? It pins **one** pod. When the rollout deletes that pod the
> tunnel breaks and the probe reports failures that have nothing to do with the application.

## 0. Cluster with the port mappings (once)

```powershell
kind delete cluster --name fulfillops
kind create cluster --name fulfillops --config infra/kind/kind-config.yaml
docker compose build
kind load docker-image fulfillops-api:local fulfillops-worker:local --name fulfillops
kubectl create namespace fulfillops
kubectl -n fulfillops create secret generic fulfillops-db `
  --from-literal=POSTGRES_USER=fulfillops_user --from-literal=POSTGRES_PASSWORD=<choose-one>
```

## 1. Install Argo CD and hand the app over to GitOps

```powershell
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts `
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd rollout status deploy/argocd-server --timeout=300s
kubectl -n argocd rollout status statefulset/argocd-application-controller --timeout=300s
kubectl apply -n argocd -f infra/argocd/application.yaml
kubectl -n argocd get application fulfillops -w     # wait for Synced + Healthy, then Ctrl+C
kubectl -n fulfillops get pods
```

Argo CD UI (optional, for screenshots):

```powershell
kubectl -n argocd port-forward svc/argocd-server 8443:443
# user: admin — password:
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}")))
```

## 2. Functional check through the NodePort (no port-forward)

```powershell
kubectl -n fulfillops exec deploy/fulfillops-api -- python scripts/reset-test-data.py
curl.exe http://localhost:8080/health/ready
python fulfillops_public_checker.py
```

## 3. Prometheus

Open http://localhost:9090 → **Status → Targets**: job `fulfillops-api` must show **2/2 UP**
(one per API pod). Useful query during the drill:

```promql
sum by (pod) (rate(fulfillops_http_requests_total[1m]))
```

## 4. The drill: GitOps rollout under continuous probing

1. On a branch, change `fulfillops.io/release: "v1"` to `"v2"` in `infra/k8s/api.yaml`
   (pod template annotation → Kubernetes treats it as a new version). Push, open the PR, **wait for CI to be green**. Don't merge yet.
2. **Terminal A**: start the probe (300 s = the maximum the script allows):
   ```powershell
   python fulfillops_rollout_probe.py --base-url http://localhost:8080 --duration 300 --interval 0.25 --output docs/evidence/rollout_probe.csv
   ```
3. Within ~30 s: **merge the PR** on GitHub, then tell Argo CD to look at Git now
   (otherwise it polls every ~3 min):
   ```powershell
   kubectl -n argocd annotate application fulfillops argocd.argoproj.io/refresh=normal --overwrite
   kubectl -n fulfillops rollout status deployment/fulfillops-api
   kubectl -n fulfillops get pods
   ```
4. Wait for the probe to finish. Expected last line:
   `PROBE duration=300.0s total=… success=… failures=0 file=docs/evidence/rollout_probe.csv`
   (exit code 0). Any failure prints `FIRST_FAILURE …` and exit code 1.

## 5. Evidence to keep (for the report / defense)

- `docs/evidence/rollout_probe.csv` and the probe summary line
- `kubectl -n fulfillops get pods` during the rollout (old + new ReplicaSet side by side)
- `kubectl -n fulfillops rollout history deployment/fulfillops-api`
- Argo CD UI: app **Synced / Healthy** at the new Git revision
- Prometheus **Targets** page (2/2 UP) and the request-rate graph across the rollout

## Results

| Date (UTC) | Git revision | Probe total | Failures | Notes |
|---|---|---|---|---|
| _fill in_ | _commit SHA_ | | | |
