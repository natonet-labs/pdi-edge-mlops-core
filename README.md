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

### Phase 1 — Foundation — In Progress

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

- Additional NPU inference services (pose estimation, segmentation)
- Model versioning and rollback via registry tags
- Load testing and CPU vs. NPU benchmarking

### Phase 3 — Observability & Scale — Upcoming

- Grafana alerting for NPU temperature and inference latency thresholds
- Horizontal scaling of CPU-bound workloads on panda-worker
- Secure remote access for live demonstrations
