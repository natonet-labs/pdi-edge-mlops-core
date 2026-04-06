# Bare Metal MLOps Sandbox

![Status](https://img.shields.io/badge/Status-In%20Progress-yellow)
![Phase](https://img.shields.io/badge/Phase-1%20Complete-green)
![OS](https://img.shields.io/badge/OS-Ubuntu%2024.04-orange?logo=ubuntu&logoColor=white)
![K3s](https://img.shields.io/badge/Orchestration-K3s-326CE5?logo=kubernetes&logoColor=white)
[![DeepX DX-M1](https://img.shields.io/badge/NPU-DeepX%20DX--M1%2025%20TOPS-blue)](https://developer.deepx.ai)
[![LattePanda](https://img.shields.io/badge/SBC-LattePanda%203%20Delta-red?logo=intel&logoColor=white)](https://www.lattepanda.com/lattepanda-3-delta)

## Project Overview

The Bare Metal MLOps Sandbox is a hands-on engineering environment for learning how to deploy and operate machine learning systems on real hardware. Rather than relying on cloud abstractions, this project builds everything from the ground up — bare metal nodes, a local Kubernetes cluster, hardware-accelerated inference, and a full observability stack.

The cluster runs two LattePanda 3 Delta nodes. The control plane hosts a DeepX DX-M1 NPU accelerator, which runs computer vision inference workloads as host-native systemd services. A key discovery during this build: the DX-M1's kernel IPC mechanism (`dxrtd`) is incompatible with container process isolation — inference services must run directly on the host, exposed to the cluster via Kubernetes ExternalName services.

Observability is handled by Prometheus and Grafana, scraping both cluster metrics and per-model inference latency from the NPU services. A private local Docker registry serves container images to both nodes, with a daily garbage collection CronJob to manage storage.

---

## Cluster Architecture

### Hardware Configuration

| Node | Role | Storage | Key Hardware |
|---|---|---|---|
| `panda-control` | Control Plane | 512 GB | DeepX DX-M1 AI Module (25 TOPS NPU) |
| `panda-worker` | Worker | 256 GB | Intel N5105 (LattePanda 3 Delta) |

### Control Plane (`panda-control`)

- **K3s API server, scheduler, controller manager, etcd** — cluster orchestration
- **Local Docker registry** — serves images to both nodes (NodePort 32034)
- **registry-gc CronJob** — daily tag pruning and garbage collection
- **yolov8n-inference** — YOLOv8N object detection via DX-M1 NPU (systemd, port 8000)
- **scrfd-inference** — SCRFD500M face detection via DX-M1 NPU (systemd, port 8002)
- **status-api** — cluster status API for Inky Frame display (systemd, port 8001)
- **Prometheus / Grafana** — cluster health, node metrics, and inference latency

### Worker (`panda-worker`)

- **K3s agent** — receives workloads from control plane, manages containers
- Pulls images from the control plane registry
- CPU-only compute node (no NPU)
- Runs cluster DaemonSet pods (node-exporter, Traefik ServiceLB)

---

## Stack

- **Compute:** Intel Celeron N5105 (LattePanda 3 Delta) × 2 nodes
- **Acceleration:** DeepX DX-M1 (25 TOPS, 4 GB LPDDR5) — host-native inference only (not containerizable)
- **Orchestration:** K3s (Lightweight Kubernetes)
- **Registry:** Private local Docker registry on control plane with daily GC
- **Observability:** Prometheus / Grafana — node metrics, NPU temperature, inference latency
- **OS:** Ubuntu 24.04 LTS

---

## Roadmap

### Phase 1 — Foundation — Complete

| # | Item | Status |
|---|---|---|
| 1 | OS provisioning and static networking on both nodes | Done |
| 2 | K3s cluster initialization (control plane + worker) | Done |
| 3 | DX-M1 NPU driver installation and validation | Done |
| 4 | Local Docker registry with garbage collection CronJob | Done |
| 5 | Prometheus + Grafana observability stack | Done |
| 6 | YOLOv8N inference service (NPU-accelerated, host-native) | Done |
| 7 | SCRFD face detection service (NPU-accelerated, host-native) | Done |
| 8 | Multi-node networking verification (Flannel VXLAN + kube-dns) | Done |
| 9 | Grafana dashboard committed to repo | Done |
| 10 | CI/CD pipeline (GitHub Actions → local registry) | Done |

### Phase 2 — Acceleration & Serving — Upcoming

| # | Item | Status |
|---|---|---|
| 1 | MobileNetV2 classification inference service (third NPU service) | Done |
| 2 | YOLOv8N-SEG segmentation inference service (fourth NPU service) | Upcoming |
| 3 | Update npu-inference Grafana dashboard with new `$job` options | Upcoming |
| 4 | Model version info metric — Prometheus gauge exposing active model version per service | Upcoming |
| 5 | Rollback procedure — re-tag registry + restart service, validated end-to-end | Upcoming |
| 6 | First containerized workload on panda-worker | Upcoming |
| 7 | Inference load test baseline — req/s and latency p50/p95/p99 per model under sustained load | Upcoming |
| 8 | CPU vs. NPU benchmark — same workload on host CPU vs. DX-M1, documented results | Upcoming |

### Phase 3 — Observability & Scale — Upcoming

| # | Item | Status |
|---|---|---|
| 1 | Grafana alert rules — inference latency SLO (>50ms p95) and NPU temperature ceiling | Upcoming |
| 2 | Grafana alert rules — pod restart rate and node-down detection | Upcoming |
| 3 | Alertmanager routing — deliver alerts to a notification channel | Upcoming |
| 4 | Horizontal Pod Autoscaler on panda-worker containerized workload | Upcoming |
| 5 | Automated rollback — Alertmanager webhook triggers revert to previous registry tag on SLO breach | Upcoming |
| 6 | Model output drift detection — track detection count distribution shift over time via Prometheus | Upcoming |
| 7 | Node failure simulation — cordon/drain panda-worker, verify workload rescheduling | Upcoming |
| 8 | Secure remote access via Tailscale for live cluster demonstrations | Upcoming |
