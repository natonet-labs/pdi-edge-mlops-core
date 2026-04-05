# Node 02 — Worker Readiness Plan

**Hostname:** `panda-worker`
**Hardware:** LattePanda 3 Delta · Intel Celeron N5105 · 8GB RAM · 256GB SATA SSD · no DX-M1
**OS:** Ubuntu 24.04 LTS
**Role:** K3s worker (agent-only) — compute offload, future CPU-bound workloads
**Date:** 2026-04-05

---

## Order of Work

| Step | Task | Status |
|---|---|---|
| 1 | Assign static IP via netplan | Pending |
| 2 | Open UFW firewall ports | Done (via K3s agent install) |
| 3 | Configure xrdp remote access | Pending |
| 4 | Copy registry config from panda-control | Done |
| 5 | Join K3s cluster as agent | Done (2026-04-04) |
| 6 | Verify cluster state | Done |

> **Note on order:** Steps 1–3 should be completed before a K3s agent installation on any future node. On panda-worker, the agent was installed before the static IP was configured via netplan (same mistake as panda-control — see node01 Lessons Learned). Step 1 must still be completed to ensure stability.

---

## Step 1 — Static IP via Netplan

> **Why this must be done on the OS, not just the router:** A DHCP reservation on the router is tied to the router — it breaks if the router is replaced, reconfigured, or the node moves. A static IP configured in netplan survives router changes, DHCP failures, and network topology changes. The OS is the source of truth for the node IP.

**Identify the Ethernet interface:**
```bash
ip link show
# Look for enp* or eth* — the active Ethernet interface
ip addr show <interface>
# Note current IP and gateway
```

**Find the current netplan config:**
```bash
ls /etc/netplan/
cat /etc/netplan/<filename>.yaml
```

**Edit the netplan config to assign a static IP:**
```bash
sudo nano /etc/netplan/<filename>.yaml
```

Replace or add the Ethernet interface configuration:
```yaml
network:
  version: 2
  ethernets:
    <interface-name>:
      dhcp4: false
      addresses:
        - <your-static-ip>/24
      routes:
        - to: default
          via: <your-gateway-ip>
      nameservers:
        addresses:
          - 1.1.1.1
          - 8.8.8.8
```

**Apply and verify:**
```bash
sudo netplan apply
ip addr show <interface-name>
# Confirm the static IP is assigned
ping -c 3 panda-control.local
# Confirm connectivity to control plane
```

**Disable WiFi if present** (panda-worker should be Ethernet-only — same lesson as panda-control):
```bash
nmcli radio wifi off
# or via Settings → WiFi → disable
```

---

## Step 2 — Firewall Ports

UFW should already be active from OS setup. Verify and ensure all required ports are open:

```bash
sudo ufw status
```

Required ports:

| Port | Protocol | Purpose |
|---|---|---|
| 22 | TCP | SSH |
| 9100 | TCP | node-exporter — Prometheus scraping from panda-control |
| 10250 | TCP | Kubelet — K3s control plane communication |
| 8472 | UDP | Flannel VXLAN — pod-to-pod traffic |
| 51820 | UDP | Flannel WireGuard |

Open any that are missing:
```bash
sudo ufw allow 22/tcp
sudo ufw allow 9100/tcp
sudo ufw allow 10250/tcp
sudo ufw allow 8472/udp
sudo ufw allow 51820/udp
sudo ufw enable
```

> **Port 9100 is critical.** Without it, Prometheus on panda-control cannot scrape node-exporter metrics from panda-worker, and the Grafana cluster dashboard will show panda-worker metrics as `down`.

---

## Step 3 — xrdp Remote Access

Same configuration as panda-control. The `gnome-remote-desktop` conflict applies to all Ubuntu 24.04 nodes.

**Install xrdp and XFCE4:**
```bash
sudo apt install xrdp xorgxrdp xfce4 xfce4-goodies -y
echo "startxfce4" > ~/.xsession
sudo chmod 640 /etc/xrdp/key.pem
sudo chown root:ssl-cert /etc/xrdp/key.pem
sudo usermod -aG ssl-cert xrdp
sudo ufw allow 3389/tcp
sudo systemctl enable xrdp
sudo systemctl start xrdp
```

**Mask gnome-remote-desktop at both levels** (critical — will steal port 3389 otherwise):
```bash
sudo systemctl disable --now gnome-remote-desktop
sudo systemctl mask gnome-remote-desktop
systemctl --user disable gnome-remote-desktop
systemctl --user mask gnome-remote-desktop
```

**Regenerate certificate for hostname:**
```bash
sudo openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout /etc/xrdp/key.pem \
  -out /etc/xrdp/cert.pem \
  -days 3650 \
  -subj "/CN=panda-worker"

sudo chmod 640 /etc/xrdp/key.pem
sudo chown root:ssl-cert /etc/xrdp/key.pem
sudo systemctl restart xrdp
```

**Connection details:**

| Property | Value |
|---|---|
| Host | `panda-worker.local` / `<your-static-ip>` |
| Port | `3389` |
| Session | XFCE4 |

> **Wayland note:** Ubuntu 24.04 defaults to Wayland. xrdp requires X11. Select **Ubuntu on Xorg** at GDM login. See node01 configuration guide §8.7 for details.

---

## Step 4 — Registry Config

Copy the K3s registry mirror config from panda-control so panda-worker can pull images from the local registry at `panda-control:32034`.

**From panda-control:**
```bash
scp /etc/rancher/k3s/registries.yaml delta@panda-worker.local:/tmp/registries.yaml
```

**On panda-worker:**
```bash
sudo mkdir -p /etc/rancher/k3s
sudo mv /tmp/registries.yaml /etc/rancher/k3s/registries.yaml
sudo systemctl restart k3s-agent
```

**Verify the registry is reachable from panda-worker:**
```bash
curl http://panda-control:32034/v2/
# Expected: {}
```

---

## Step 5 — K3s Agent Join

> **Status:** Completed 2026-04-04. Documented here for reproducibility.

The K3s join token and control plane IP are required. Retrieve the token from panda-control:
```bash
# On panda-control:
sudo cat /var/lib/rancher/k3s/server/node-token
```

**Run on panda-worker:**
```bash
curl -sfL https://get.k3s.io | \
  K3S_URL=https://<panda-control-ip>:6443 \
  K3S_TOKEN=<node-token> \
  sh -
```

The agent service starts automatically as `k3s-agent.service`.

---

## Step 6 — Verify Cluster State

**From panda-control:**
```bash
kubectl get nodes -o wide
```

Expected:
```
NAME            STATUS   ROLES           AGE   VERSION
panda-control   Ready    control-plane   Xd    v1.34.6+k3s1
panda-worker    Ready    <none>          Xd    v1.34.6+k3s1
```

**Verify node-exporter is reachable from panda-control:**
```bash
curl http://panda-worker.local:9100/metrics | head -5
```

**Verify Prometheus is scraping panda-worker:**

Open Grafana → Explore → Prometheus → query:
```
up{job="node-exporter", instance=~".*:9100"}
```

Both instances should show value `1`.

**Verify pod scheduling works on panda-worker:**
```bash
kubectl run test-worker --image=busybox --restart=Never \
  --overrides='{"spec":{"nodeName":"panda-worker"}}' \
  -- echo "panda-worker is schedulable"
kubectl logs test-worker
kubectl delete pod test-worker
```

---

## Node 02 System Summary

```
delta@panda-worker (Node 02)
├── Hardware
│   ├── LattePanda 3 Delta (Intel N5105, 8GB RAM)
│   ├── 64GB eMMC           ← Recovery (auto-mount disabled via udev)
│   └── B-Key slot          ← 256GB SATA SSD (OS + data)
│       (no DX-M1 — CPU-only compute)
├── Orchestration
│   └── K3s v1.34.6 (agent only)
│       └── Registers with panda-control:6443
├── Observability
│   └── node-exporter (scraped by Prometheus on panda-control, port 9100)
└── Remote Access
    ├── SSH (port 22)
    └── xrdp / XFCE4 (port 3389)
```

---

## Differences from Node 01

| Aspect | panda-control (Node 01) | panda-worker (Node 02) |
|---|---|---|
| K3s role | Control plane | Agent only |
| NPU | DeepX DX-M1 (25 TOPS) | None |
| BIOS config | PCIe Root Ports forced Gen2 | Default (no PCIe device) |
| Inference service | yolov8n-inference (systemd) | None |
| Status API | status-api (systemd, port 8001) | None |
| Registry | Hosts registry (NodePort 32034) | Pulls from panda-control |
| Prometheus | Runs in cluster | Scraped by panda-control |

---

## Pending After Step 1

Once netplan static IP is confirmed on panda-worker, update the K3s agent to pin `--node-ip` so it does not cache a wrong IP if the network changes later. Add to `/etc/systemd/system/k3s-agent.service.env` or the agent's ExecStart:

```bash
# Check current agent service config:
sudo systemctl cat k3s-agent

# Add node-ip to the environment or ExecStart, then:
sudo systemctl daemon-reload
sudo systemctl restart k3s-agent

# Verify the correct internal IP is registered:
kubectl get node panda-worker -o wide
# INTERNAL-IP should match the netplan static IP
```
