# k8s manifests — `vps_stats` on k3d

Single-service deployment of the `vps_stats` Go microservice to a local
k3d cluster. The other services stay on docker-compose for now — this is
a learning exercise, not a full migration.

## Quick start (on your laptop, not the VPS)

```bash
# 1. Install k3d + kubectl (one-time)
#    macOS:  brew install k3d kubectl
#    Linux:  see https://k3d.io/
#    Win:    choco install k3d kubernetes-cli
#            or the official installer from https://kubernetes.io/releases/download/

# 2. Create a local cluster (30 seconds)
k3d cluster create aiops-lab --api-port 6550 -p "8090:80@loadbalancer"

# 3. Build the vps_stats image and load it into the cluster
cd services/vps_stats
docker build -t vps_stats:local .
k3d image import vps_stats:local -c aiops-lab

# 4. Create the token secret
kubectl create namespace aiops --dry-run=client -o yaml | kubectl apply -f -
kubectl -n aiops create secret generic vps-stats-secret \
  --from-literal=VPS_STATS_TOKEN="$(openssl rand -hex 32)"

# 5. Apply everything
cd ../../deploy/k8s
kubectl apply -k .

# 6. Watch it come up
kubectl -n aiops get pods -w
# Ctrl-C once you see vps-stats-xxxx in Running / 1/1 Ready

# 7. Smoke-test it
kubectl -n aiops port-forward svc/vps-stats 8091:8090 &
TOKEN=$(kubectl -n aiops get secret vps-stats-secret -o jsonpath='{.data.VPS_STATS_TOKEN}' | base64 -d)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8091/stats
```

## Files

| File | What it is |
|---|---|
| `namespace.yaml` | Creates the `aiops` namespace |
| `vps-stats-configmap.yaml` | Non-secret env vars (disk path, addr) |
| `vps-stats-secret.yaml.example` | Template for the auth token (real one stays out of git) |
| `vps-stats-daemonset.yaml` | One pod per node, mounts host /proc and /sys |
| `vps-stats-service.yaml` | ClusterIP exposing port 8090 |
| `kustomization.yaml` | Glues everything for `kubectl apply -k .` |

## Why DaemonSet, not Deployment?

A Deployment gives you N replicas *somewhere* in the cluster. But this
service's job is "report this node's metrics." We want **one pod per
node** with *that* node's `/proc` mounted. DaemonSet is exactly that
pattern — prometheus node-exporter uses it for the same reason.

Add a second node (`k3d node add`) and a second pod appears automatically.
No manifest change needed.

## Tear down

```bash
kubectl delete -k .                  # remove the app
k3d cluster delete aiops-lab         # nuke the cluster
```

## Troubleshooting

- **Pod stuck in `ImagePullBackOff`** — you forgot step 3 (load image into
  k3d). k3d doesn't see your local Docker daemon's images automatically.
- **`unauthorized` on /stats** — the ConfigMap doesn't include the token;
  the Secret does. Check `envFrom` lists both.
- **Stats show 0s for disk/CPU** — hostPath mounts failed or gopsutil
  didn't read HOST_PROC. `kubectl -n aiops describe pod <name>` shows
  volume mount errors.
- **`kubectl apply -k .` fails with `vps-stats-secret.yaml` not found** —
  create the Secret via the `kubectl create secret` command in step 4,
  not by committing the file.
