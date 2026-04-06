# Node 01 — Single-Node Readiness Plan

**Hostname:** `panda-control`
**Goal:** Get node 01 production-ready as a K3s control plane before node 02 (worker) arrives.
**Date:** 2026-04-02

---

## Order of Work

| Step | Task | Status |
|---|---|---|
| 1 | Install K3s and verify single-node cluster | Done |
| 2 | Reserve static IP, open firewall ports | Done |
| 3 | Deploy local registry, push first inference image | Done |
| 4 | Deploy node_exporter + Prometheus + Grafana | Done |
| 5 | Build and deploy FastAPI inference container (YOLOv8N) | Done |
| 6 | Add latency/FPS metrics to inference container | Done |
| 7 | Build initial Grafana dashboard | Done |

---

## Step 1 — Install K3s (Single-Node Control Plane)

Install K3s with TLS SANs for both hostname and static IP so the API server certificate remains valid when node 02 joins.

> **Important — set `--node-ip` at install time.** K3s auto-detects the node IP on first startup and caches it. If the network changes later (interface disabled, DHCP reassignment, WiFi removed), K3s will fail to start with `failed to find interface with specified node ip`. Always pin `--node-ip` to `<panda-control-ip>` at install time to prevent this. Reserve the static IP on the router by MAC address *before* running the installer.

```bash
curl -sfL https://get.k3s.io | sh -s - \
  --tls-san panda-control.local \
  --tls-san <panda-control-ip> \
  --node-ip <panda-control-ip> \
  --write-kubeconfig-mode 644
```

**Verify:**
```bash
kubectl get nodes
kubectl get pods -A
```

Expected: node status `Ready`, core K3s pods running in `kube-system`.

Save the join token for node 02:
```bash
sudo cat /var/lib/rancher/k3s/server/node-token
```

---

## Step 2 — Networking

**Reserve a static IP** on your router by MAC address (not on the OS). This keeps the API server address stable when node 02 joins.

**Open required UFW ports:**

```bash
sudo ufw allow 6443/tcp    # K3s API server — workers join here
sudo ufw allow 10250/tcp   # Kubelet
sudo ufw allow 8472/udp    # Flannel VXLAN — pod-to-pod traffic
sudo ufw allow 51820/udp   # Flannel WireGuard (if enabled)
```

**Verify:**
```bash
sudo ufw status
```

---

## Step 3 — Local Docker Registry

Run the registry as a K3s pod so it is part of the cluster from day one.

```bash
kubectl create deployment registry --image=registry:2 --port=5000
```

Expose as NodePort — run as a single line (backslash continuations cause shell errors):
```bash
kubectl expose deployment registry --type=NodePort --port=5000 --target-port=5000 --name=registry
```

Check the assigned NodePort:
```bash
kubectl get svc registry
```

> Note: `kubectl expose` does not support a `--node-port` flag. The NodePort is assigned randomly by K3s. On this cluster it was assigned `32034`. Note the port from `kubectl get svc` and use it consistently in `registries.yaml` and all image references.

Verify the registry is reachable:
```bash
curl http://panda-control:32034/v2/
# Expected: {}
```

**Configure K3s to trust the local registry (HTTP):**

```bash
sudo mkdir -p /etc/rancher/k3s
sudo tee /etc/rancher/k3s/registries.yaml <<EOF
mirrors:
  "panda-control:32034":
    endpoint:
      - "http://panda-control:32034"
EOF
sudo systemctl restart k3s
```

> When node 02 joins, add the same `registries.yaml` on that node so it pulls images from `panda-control` automatically.

### Tag Strategy

```
panda-control:32034/<workload>/<model>:<model-version>-<build>

# Examples:
panda-control:32034/inference/yolov8n:v1.0.0-001
panda-control:32034/inference/scrfd-face:v1.0.0-001
```

- `<workload>` — service category (inference, classifier, etc.)
- `<model>` — model name, lowercase, hyphenated
- `<model-version>` — semantic version of the model weights
- `<build>` — auto-incremented build number from GitHub Actions

### Cleanup Policy

Registry deletion is enabled via `REGISTRY_STORAGE_DELETE_ENABLED=true` on the registry deployment. A K3s CronJob (`registry-gc`) runs daily at 03:00 UTC and:
- Prunes all but the 3 most recent tags per image via the registry API
- Runs `registry garbage-collect --delete-untagged=true` inside the registry pod to reclaim storage

See `cluster/registry-gc/` for the CronJob manifests and GC script.

---

## Step 4 — Observability Stack

Deploy via Helm using the kube-prometheus-stack chart, which bundles Prometheus, Grafana, AlertManager, node-exporter, and kube-state-metrics in a single install.

**Install Helm:**
```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

**Set KUBECONFIG** (required — add to ~/.bashrc to make permanent):
```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
echo 'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml' >> ~/.bashrc
```

**Add chart repo and install:**
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
kubectl create namespace monitoring
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set grafana.adminPassword=<your-password> \
  --set prometheus.prometheusSpec.retention=15d
```

**Expose Grafana as NodePort:**
```bash
kubectl patch svc kube-prometheus-stack-grafana -n monitoring \
  --type='json' \
  -p='[{"op":"replace","path":"/spec/type","value":"NodePort"},{"op":"add","path":"/spec/ports/0/nodePort","value":32000}]'
sudo ufw allow 32000/tcp
```

**Access Grafana:** `http://panda-control.local:32000` — login: `admin` / `<your-password>`

Deploy in this order: node_exporter first for immediate host visibility, then Prometheus, then Grafana.

### Metrics to Collect

| Metric | Tool | Purpose |
|---|---|---|
| Inference latency (ms) | Custom Prometheus exporter in inference service | Core performance indicator |
| Throughput (FPS) | Same exporter | Capacity planning |
| NPU temperature (3 cores) | dxrt-cli scraper | Thermal stability under load |
| NPU memory usage | dxrt-cli scraper | Detect model memory leaks |
| Host CPU usage | node_exporter | Verify NPU offloading, not CPU |
| Host RAM usage | node_exporter | Catch framework overhead |
| Pod restarts | kube-state-metrics | Detect crashes and OOM kills |
| Container CPU/mem | cAdvisor | Per-workload resource tracking |

### Key Grafana Dashboard Panels

- Inference latency over time — line chart, alert threshold at 50ms
- NPU core temperatures — 3 gauges (one per core)
- FPS throughput — line chart
- Host CPU vs NPU load — side-by-side to validate offloading

---

## Step 5 — First Model Deployment (YOLOv8N Inference Service)

**Deployed as:** systemd service on the host, exposed to K3s via ExternalName service.

**Model selection rationale:**

| Model | Format | Size | Task | Latency on DX-M1 |
|---|---|---|---|---|
| YOLOv8N | .dxnn | ~6 MB | Object detection | ~10-20ms |
| SCRFD500M | .dxnn | ~2 MB | Face detection | ~10-15ms |
| MobileNetV2 | .dxnn | ~14 MB | Classification | ~5ms |
| YOLOv8N-SEG | .dxnn | ~7 MB | Segmentation | ~20-30ms |

### Why Not a Container

Containerizing the DX-M1 inference workload was attempted and encountered a chain of issues:

| Issue | Fix Applied |
|---|---|
| `dx_engine` not found | Copied from host venv into Docker build context |
| `libdxrt.so` missing | Copied from `/usr/local/lib/` into image |
| `python-multipart` missing | Added to Dockerfile pip install |
| `dxrt service is not running` | Added `hostPID: true` to pod spec |
| `Fail to initialize device 0` | Added `privileged: true` to container security context |
| InferenceEngine hangs indefinitely | Root cause: `dxrtd` uses `/dev/dxrt0` as a kernel-level IPC bus; container process credentials and cgroup context prevent the kernel driver from routing messages back to the containerized client — not fixable via pod spec flags |

**Root cause:** The DX-RT daemon (`dxrtd`) owns the NPU via `/dev/dxrt0`. `InferenceEngine` communicates with `dxrtd` through the kernel driver using process context (credentials/cgroup) for message routing. Container isolation prevents this routing from completing even with `hostPID` and `privileged` mode.

**Pattern for bare metal hardware accelerators:** run the inference workload natively on the host, expose it to K3s as a cluster service via ExternalName. This is the same pattern used for proprietary GPU/NPU hardware before device plugins exist.

### systemd Service Setup

Install dependencies into the dx-venv:
```bash
source ~/dx-all-suite/dx-venv/bin/activate
pip install uvicorn fastapi python-multipart prometheus-client
```

Create the service:
```bash
sudo tee /etc/systemd/system/yolov8n-inference.service <<EOF
[Unit]
Description=YOLOv8N NPU Inference Service
After=dxrt.service
Requires=dxrt.service

[Service]
User=<your-username>
WorkingDirectory=/home/<your-username>/natonet-labs/bare-metal-mlops-sandbox/cluster/inference/yolov8n
ExecStart=/home/<your-username>/dx-all-suite/dx-venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5s
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now yolov8n-inference
```

> **Note:** `MODEL_PATH` in `app.py` must be the host filesystem path, not a container path:
> `/home/<your-username>/dx-all-suite/workspace/res/models/models-2_2_1/YoloV8N.dxnn`

Verify:
```bash
curl http://localhost:8000/health
# Expected: {"status":"ok","model":"YoloV8N"}
```

### K3s ExternalName Service

Register the host service in K3s so other pods can reach it via cluster DNS:
```bash
kubectl apply -f k8s/host-service.yaml
```

`cluster/inference/yolov8n/k8s/host-service.yaml` points to `panda-control.local:8000`.

### Metrics (Step 6)

Metrics are built into `app.py` — no separate step required. The `/metrics` endpoint exposes:
- `inference_requests_total` — request counter
- `inference_latency_ms` — histogram (buckets: 5-200ms)
- `detections_per_frame` — histogram

Verify:
```bash
curl http://localhost:8000/metrics
```

---

## Step 6 — Inference Metrics Exporter

Add a Prometheus metrics endpoint to the inference container exposing:

- `inference_latency_ms` — histogram
- `inference_fps` — gauge
- `npu_temperature_celsius` — gauge per core (scraped from dxrt-cli)
- `npu_memory_used_bytes` — gauge

---

## Step 7 — Grafana Dashboard

Build dashboards from the metrics collected in Steps 4 and 6. Store dashboard JSON in the repo under `cluster/grafana/dashboards/` so they are version-controlled and reproducible.

---

## Storage Upgrade — 256GB → 512GB (Completed 2026-04-03)

The OS drive was upgraded from a Transcend 430S 256GB to a Transcend 430S 512GB SATA SSD while the system remained live.

**Procedure:**
1. Stop write-heavy services:
   ```bash
   sudo systemctl stop yolov8n-inference
   sudo systemctl stop k3s
   ```
2. Clone live with dd (no eMMC reboot required):
   ```bash
   sudo dd if=/dev/sda of=/dev/sdb bs=4M status=progress conv=fsync
   ```
3. Physical drive swap: removed 256GB from B-Key slot, inserted 512GB.
4. Booted normally, then expanded partition and filesystem:
   ```bash
   sudo growpart /dev/sda 2
   sudo resize2fs /dev/sda2
   ```
5. Restarted services:
   ```bash
   sudo systemctl start k3s
   sudo systemctl start yolov8n-inference
   ```

**Result:** `/dev/sda2` — 468G total, 73G used, 374G available.

---

## Node 02 Join (Completed 2026-04-04)

`panda-worker` arrived and joined the cluster as a K3s agent.

**Join command (run on panda-worker):**
```bash
curl -sfL https://get.k3s.io | K3S_URL=https://<panda-control-ip>:6443 K3S_TOKEN=<node-token> sh -
```

**Registry config (copy from panda-control, run on panda-worker):**
```bash
# from panda-control:
scp /etc/rancher/k3s/registries.yaml <your-username>@panda-worker.local:/tmp/registries.yaml

# on panda-worker:
sudo mkdir -p /etc/rancher/k3s
sudo mv /tmp/registries.yaml /etc/rancher/k3s/registries.yaml
sudo systemctl restart k3s-agent
```

**Verified:**
```
NAME            STATUS   ROLES           AGE   VERSION
panda-control   Ready    control-plane   43h   v1.34.6+k3s1
panda-worker    Ready    <none>          74s   v1.34.6+k3s1
```

Pre-requisites that enabled smooth join:
- Static IP reserved on router (Step 2)
- Port 6443 open on panda-control (Step 2)
- TLS SANs set at K3s install time (Step 1)
- Registry config copied post-join (Step 3)

---

## Lessons Learned

### K3s node-ip must be pinned at install time

**What happened:** panda-control was installed with WiFi and Ethernet both active. K3s auto-detected and cached the WiFi IP (`<wifi-ip>`) as the node's InternalIP. When WiFi was later disabled to use Ethernet-only, K3s crashed on every startup with:
```
failed to start networking: unable to initialize network policy controller:
error getting node subnet: failed to find interface with specified node ip
```
K3s was looking for an interface with the cached WiFi IP, which no longer existed.

**Fix applied:** Added `--node-ip <ethernet-ip>` to `ExecStart` in `/etc/systemd/system/k3s.service` and restarted. K3s then registered the correct IP and stabilized.

**Secondary effect:** Prometheus node-exporter scrape targets still pointed to the old WiFi IP and showed `down` until K3s service discovery updated after re-registration.

**Prevention:** Always reserve the static IP on the router by MAC address and set `--node-ip` at K3s install time (see Step 1). This applies to both control plane and worker nodes.

### Follow installation order: static IP on OS first, then K3s

The root cause above was avoidable by following the industry-standard node provisioning order:

```
1. Decide: which interface? (Ethernet or WiFi — never both for a cluster node)
2. Assign a static IP on the OS itself (netplan/nmcli) — not just a router DHCP reservation
3. Verify the node always boots with that IP regardless of router or network changes
4. Then install K3s with --node-ip pointing to that interface
```

This is not just a "production vs home lab" distinction. It applies to any cluster where the installation standard is followed deliberately. The standard exists to force upfront decisions:

- **Which interface will this node use permanently?** A node with both WiFi and Ethernet active is ambiguous — K3s will pick one and cache it.
- **Is the IP stable across reboots and router changes?** A DHCP reservation on the router works until the router is replaced, reconfigured, or the node moves to a different network.
- **Is the OS the source of truth for the IP?** It should be. A static IP configured in netplan survives router replacements, DHCP failures, and network topology changes.

Had this order been followed on panda-control — decide on Ethernet-only, configure a static IP in netplan, then install K3s — the WiFi interface would never have been a factor and `--node-ip` would have been correct from day one.

**For panda-worker and any future nodes:** configure a static IP via netplan before running the K3s agent installer.

### Prometheus scrape targets must use IPs, not `.local` hostnames

**What happened:** The Prometheus additional scrape config for the NPU inference services used `panda-control.local` as the target hostname. Prometheus runs inside a pod and uses CoreDNS for name resolution — it has no access to mDNS, which is what resolves `.local` hostnames at the OS level. All four inference service targets showed `health: down` and no metrics were scraped.

This is the same class of problem as the containerd registry hostname issue documented in the node02 plan: anything running inside a pod cannot resolve `.local` names, even if `ssh` and `curl` from the host work fine.

**Secondary issue:** The Prometheus CR was configured to load scrape configs from a secret key named `inference.yaml`, but the secret had been created with key `additional-scrape-configs.yaml`. Prometheus silently failed to load the scrape config entirely, logging:
```
loading additional scrape configs from Secret failed: key inference.yaml could not be found in secret inference-scrape-config
```

**Root cause:** Both issues were introduced by out-of-band changes made during a previous dashboard consolidation session — the Prometheus CR and scrape config secret were modified but not committed to the repo, leaving no record of what changed or why.

**Fix applied:**
1. Recreated the `inference-scrape-config` secret with the correct key (`inference.yaml`) and target IPs instead of `.local` hostnames:
```bash
kubectl create secret generic inference-scrape-config \
  --namespace monitoring \
  --from-literal=inference.yaml="$(cat <<'EOF'
- job_name: yolov8n-inference
  static_configs:
    - targets: ["<panda-control-ip>:8001"]
- job_name: scrfd-inference
  static_configs:
    - targets: ["<panda-control-ip>:8002"]
- job_name: mobilenetv2-inference
  static_configs:
    - targets: ["<panda-control-ip>:8003"]
- job_name: yolov8n-seg-inference
  static_configs:
    - targets: ["<panda-control-ip>:8004"]
EOF
)" \
  --dry-run=client -o yaml | kubectl apply -f -
```
2. Restarted the Prometheus StatefulSet to force the config-reloader to apply the new secret:
```bash
kubectl rollout restart statefulset/prometheus-kube-prometheus-stack-prometheus -n monitoring
```

**Prevention:** Always use node IPs (not `.local` hostnames) in any Kubernetes resource that runs inside a pod — scrape configs, registry mirrors, ExternalName services pointing to host services. Any Kubernetes resource that changes cluster state should be committed to the repo alongside the application change that motivated it.
