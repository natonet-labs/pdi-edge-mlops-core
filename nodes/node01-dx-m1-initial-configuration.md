# Node 01 - DX-M1 NPU Initial Configuration

**Roadmap Phase:** 1 (OS Provisioning) → 2 (NPU Acceleration)  
**Hostname:** `panda-control`  
**Hardware:** LattePanda 3 Delta · Intel Celeron N5105 · DeepX DX-M1 (M.2 NPU)  
**OS:** Ubuntu 24.04.4 LTS (Noble Numbat) · Xorg session  
**Date:** 2026-03-31

---

## Overview

This document covers the initial configuration of Node 01 - the LattePanda 3 Delta unit equipped with the DeepX DX-M1 NPU accelerator module. It covers hardware setup, BIOS configuration, driver verification, NPU inference validation via webcam demos, thermal management, and remote access. Node 02 is a second LattePanda 3 Delta without the DX-M1 module.

> For the full driver installation walkthrough from scratch, see [DX-M1 Setup Guide](/docs/hardware/dx-m1-setup-guide.md).
> For the hardware selection rationale, see [ADR-0001: DeepX DX-M1 vs Hailo-8](/docs/adr/0001-choosing-deepx-dxm1-over-hailo8.md).

---

## 1. Hardware Specification

| Component | Detail |
|---|---|
| SBC | LattePanda 3 Delta |
| CPU | Intel Celeron N5105 (Jasper Lake, 4-core, 10W TDP) |
| RAM | 8GB LPDDR4 |
| Storage (OS + Data) | Transcend 430S 512GB SATA SSD (B-Key slot) |
| Storage (Recovery) | 64GB onboard eMMC (auto-mount disabled) |
| AI Accelerator | DeepX DX-M1 M.2 2280 (M-Key slot) |
| NPU Performance | 25 TOPS (INT8) |
| NPU Memory | 4GB LPDDR5 |
| PCIe Interface | Gen3 x4 physical · runs at Gen2 x2 on this board |
| BIOS Version | S70JR200-CN51G-8G-A |

---

## 2. Critical BIOS Configuration

> **This is the most important step.** Without correct PCIe Root Port settings, the DX-M1 will not enumerate.

### 2.1 Root Cause

The Intel N5105 (Jasper Lake) distributes its 8 PCIe lanes across multiple Root Ports. When a Root Port is set to **Auto**, speed negotiation can fail during DMA buffer initialization - the firmware handshake times out at Gen1 (2.5 GT/s), causing the DX-M1 to not appear in `lspci`.

**Fix:** Force Root Ports to Gen2 (5.0 GT/s) explicitly.

### 2.2 Required BIOS Settings

Enter BIOS: press **DEL** repeatedly at POST.

#### PCIe Root Port 1 (M-Key slot → DX-M1)
```
Chipset → PCH-IO Configuration → PCI Express Configuration → Root Port 1
PCIe Speed: Gen2
```

#### PCIe Root Ports 5 & 6 (bonded x2 link to M-Key)
```
Chipset → PCH-IO Configuration → PCI Express Configuration → Root Port 5
PCIe Speed: Gen2

Chipset → PCH-IO Configuration → PCI Express Configuration → Root Port 6
PCIe Speed: Gen2
```

#### SATA Controller (must remain enabled)
```
Chipset → PCH-IO Configuration → SATA Configuration → SATA Controller
SATA Controller: Enabled
```

> **Note:** Early troubleshooting suggested disabling SATA to fix DX-M1 detection. This was incorrect - disabling SATA was masking a Gen1 speed negotiation failure. With Root Ports forced to Gen2, both the M-Key (DX-M1) and B-Key (SATA SSD) slots work simultaneously without modification. See ADR-0001 for full context.

### 2.3 Verify PCIe Enumeration After Boot

```bash
# DX-M1 present on PCIe bus
lspci -vn | grep 1ff4

# Full bus tree - DX-M1 should appear under Root Port 1c.0
lspci -tv

# Confirm Gen2 x2 negotiated speed
sudo lspci -vvv | grep -E "LnkSta|LnkCap"
# Expected: LnkSta: Speed 5GT/s, Width x2

# SATA SSD present alongside DX-M1
lsblk -o NAME,MODEL,SIZE,TYPE,TRAN
```

---

## 3. DeepX NPU Driver Verification

The DeepX SDK and runtime driver are installed and managed by DKMS. After installation, the source directory (`~/dx_rt_npu_linux_driver`) can be removed.

**Verify driver is loaded:**
```bash
lsmod | grep -E "dxrt|dx_dma"
```

Expected:
```
dxrt_driver            53248  2
dx_dma                520192  9 dxrt_driver
```

**Verify DKMS package:**
```bash
dpkg -l | grep dxrt-driver-dkms
dkms status
```

Expected: `dxrt-driver-dkms/2.1.0-2, 6.17.0-19-generic, x86_64: installed`

**Verify device status:**
```bash
dxrt-cli --status
```

Expected output:
```
DXRT v3.2.0
=======================================================
 * Device 0: M1, Accelerator type
 * RT Driver version   : v2.1.0
 * PCIe Driver version : v2.0.1
 * FW version          : v2.1.5
 * Memory : LPDDR5 5200 Mbps, 3.92GiB
 * PCIe   : Gen2 X2 [01:00:00]

NPU 0: voltage 750 mV, clock 1000 MHz, temperature 6X'C
NPU 1: voltage 750 mV, clock 1000 MHz, temperature 6X'C
NPU 2: voltage 750 mV, clock 1000 MHz, temperature 6X'C
=======================================================
```

The DKMS source at `/usr/src/dxrt-driver-dkms-2.1.0-2/` handles kernel module rebuilds automatically on kernel updates.

---

## 4. Performance Baseline

| Metric | Value |
|---|---|
| Inference latency (YOLOv8-nano) | ~10–20ms per frame |
| NPU core temperature (idle, normal load) | ~49–52°C |
| NPU core count | 3 |
| NPU clock | 1000 MHz |
| NPU memory bandwidth | 5200 Mbps LPDDR5 |

---

## 5. Thermal Management

The DX-M1 in the Titan Case (ABS plastic) requires a **"Level-Fill Thermal Sandwich"** to maintain stable temperatures. Without it, the NPU chip can exceed 60°C due to uneven contact and trapped heat.

### Strategy

The DX-M1 board surface is uneven - the main NPU chip sits higher than surrounding components. Stacking a single thick thermal pad creates air pockets that act as insulators.

**Solution:** Fill valleys first, then cap with a thin continuous bridge pad.

### Materials
- 1mm thermal pad (valley fill)
- 0.5mm thermal pad (cap layer)
- Small aluminum heatsink
- Kapton tape (electrical isolation)

### Build Steps

1. **Safety:** Cover small gold components around the NPU chip with Kapton tape to prevent electrical shorts.
2. **Valley-fill:** Cut 1mm pad into pieces and place into recesses around the main chip until flush with the chip surface.
3. **Cap:** Lay a single continuous 0.5mm strip across the entire module, bridging the filler pieces and the chip.
4. **Heatsink:** Place heatsink on top. Ensure a small air gap between the heatsink bottom and the plastic case floor - direct contact traps heat and prevents convection.

**Result:** Stable idle temperatures of ~52°C (vs. 60°C+ without thermal management).

---

## 6. SDK Directory Structure

The DeepX all-in-one suite is located at `~/dx-all-suite/`. Key directories:

| Path | Purpose |
|---|---|
| `dx-all-suite/dx-venv/` | Python venv with `dx_engine` (runtime API) |
| `dx-all-suite/dx-runtime/dx_rt/` | Runtime source, C++ and Python examples |
| `dx-all-suite/dx-modelzoo/` | Model zoo with `dx_modelzoo` package (separate venv) |
| `dx-all-suite/workspace/res/models/models-2_2_1/` | Pre-compiled `.dxnn` model files |

> **Note:** `dx_modelzoo` is only available in `venv-dx-modelzoo-local`, not `dx-venv`. For inference scripts, use `dx_engine` directly from `dx-venv`.

**Activate the runtime venv:**
```bash
source ~/dx-all-suite/dx-venv/bin/activate
```

---

## 7. NPU Inference Demo Scripts

Demo scripts are located at `~/npu-demos/`. They use `dx_engine.InferenceEngine` directly against pre-compiled `.dxnn` models.

### 7.1 Object Detection - YOLOv8N / YOLOv11N / YOLOv12N

**Script:** `~/npu-demos/webcam_yolo.py`

Runs real-time object detection (80 COCO classes) on webcam feed via the NPU.

**Model selection** (edit `MODEL_NAME` at the top of the script):
```python
MODEL_NAME = "YOLOV11N.dxnn"  # YoloV8N.dxnn, YOLOV11N.dxnn, YOLOV12N-1.dxnn
```

**Run:**
```bash
source ~/dx-all-suite/dx-venv/bin/activate
cd ~/npu-demos
python webcam_yolo.py
```

Press `q` to quit. FPS counter displayed top-left.

**Key implementation notes:**
- Input: letterbox resize to 640×640, BGR→RGB, uint8
- Output: `[1, 84, 8400]` - decoded as cx/cy/w/h + 80 class scores
- Per-class NMS via `cv2.dnn.NMSBoxes`

### 7.2 Face Detection - SCRFD500M

**Script:** `~/npu-demos/webcam_face.py`

Runs real-time face detection with 5 facial keypoints (right eye, left eye, nose, mouth corners).

**Run:**
```bash
source ~/dx-all-suite/dx-venv/bin/activate
cd ~/npu-demos
python webcam_face.py
```

**Key implementation notes:**
- Model: `SCRFD500M_1.dxnn` - multi-scale anchor-based face detector
- Outputs 9 tensors: `score_8/16/32`, `bbox_8/16/32`, `kps_8/16/32`
- Strides 8/16/32 decoded separately then merged before NMS
- Keypoints: green (right eye), blue (left eye), red (nose), cyan/yellow (mouth corners)

### 7.3 Available Pre-compiled Models

All models at `~/dx-all-suite/workspace/res/models/models-2_2_1/`:

| Model | Task |
|---|---|
| `YoloV8N.dxnn`, `YOLOV11N.dxnn`, `YOLOV12N-1.dxnn` | Object detection |
| `SCRFD500M_1.dxnn` | Face detection + keypoints |
| `YOLOV8N_SEG-1.dxnn` | Instance segmentation |
| `yolo26n-pose.dxnn` | Pose estimation |
| `yolo26n-1.dxnn` through `yolo26x-1.dxnn` | Object detection (n/s/m/l/x sizes) |
| `MobileNetV2_2.dxnn`, `EfficientNetB0_4.dxnn` | Image classification |
| `DeepLabV3PlusMobileNetV2_2.dxnn` | Semantic segmentation |

---

## 8. Remote Access - xrdp (RDP)

Remote desktop is configured via **xrdp** with an **XFCE4** session. This provides a separate lightweight remote session independent of the physical GNOME/Xorg desktop. Same underlying system - different window manager skin.

### 8.1 Setup Summary

```bash
sudo apt install xrdp xorgxrdp xfce4 xfce4-goodies -y
echo "startxfce4" > ~/.xsession
sudo chmod 640 /etc/xrdp/key.pem
sudo chown root:ssl-cert /etc/xrdp/key.pem
sudo usermod -aG ssl-cert xrdp
sudo systemctl enable xrdp
sudo systemctl start xrdp
sudo ufw allow 3389/tcp
```

### 8.2 Critical - Disable gnome-remote-desktop

`gnome-remote-desktop` runs as both a **system service** and a **user service**, and starts automatically on login - stealing port 3389 and preventing xrdp from binding. Both layers must be masked permanently.

**Mask the system-level service:**
```bash
sudo systemctl disable --now gnome-remote-desktop
sudo systemctl mask gnome-remote-desktop
```

**Mask the user-level service:**
```bash
systemctl --user disable gnome-remote-desktop
systemctl --user mask gnome-remote-desktop
```

**Verify both are masked:**
```bash
sudo systemctl status gnome-remote-desktop
systemctl --user status gnome-remote-desktop
# Both should show: loaded (masked)
```

> **Why both?** `gnome-remote-desktop` is registered in `graphical.target.wants` as a system service (runs as the `gnome-remote-desktop` system user) AND as a user session service. Masking only one leaves the other free to start and steal port 3389. `mask` creates a symlink to `/dev/null`, which is stronger than `disable` and survives reboots and GNOME session restarts.

**If xrdp fails to start after a reboot** (port already in use):
```bash
sudo lsof -i :3389        # identify the PID
sudo kill <PID>           # free the port
sudo systemctl start xrdp
```

### 8.3 Regenerate xrdp Certificate for Hostname

After changing hostname, regenerate the TLS certificate to avoid stale CN warnings in RDP clients:

```bash
sudo openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout /etc/xrdp/key.pem \
  -out /etc/xrdp/cert.pem \
  -days 3650 \
  -subj "/CN=panda-control"

sudo chmod 640 /etc/xrdp/key.pem
sudo chown root:ssl-cert /etc/xrdp/key.pem
sudo systemctl restart xrdp
```

### 8.4 Connection Details

| Property | Value |
|---|---|
| Host | `panda-control.local` / `<your-static-ip>` (Ethernet only — WiFi disabled) |
| Port | `3389` |
| Username | `delta` |
| Session | XFCE4 (independent from physical display) |
| Client | Microsoft Remote Desktop (Windows App) on Mac |

### 8.5 Firewall Rules

| Port | Protocol | Purpose | Status |
|---|---|---|---|
| 22 | TCP | SSH | Active |
| 3389 | TCP | xrdp - remote session (XFCE4) | Active |
| 6443 | TCP | K3s API server (worker join) | Active |
| 8000 | TCP | YOLOv8N inference service (FastAPI) | Active |
| 8001 | TCP | Cluster status API (FastAPI, for Inky Frame) | Active |
| 8472 | UDP | Flannel VXLAN (pod-to-pod traffic) | Active |
| 9100 | TCP | node-exporter (Prometheus scraping) | Active |
| 10250 | TCP | Kubelet | Active |
| 32000 | TCP | Grafana (NodePort) | Active |
| 51820 | UDP | Flannel WireGuard | Active |

> **Port 3390 note:** In Ubuntu 22.04/24.04, enabling both GNOME Remote Login and Desktop Sharing simultaneously causes Desktop Sharing to shift from port 3389 to port 3390. In this setup, `gnome-remote-desktop` is fully masked at both system and user level, so port 3390 is not open in UFW and nothing listens on it. Re-enable and open it only if Desktop Sharing is needed alongside xrdp.

### 8.6 Mac Drive Sharing via RDP

xrdp supports Mac drive redirection into the remote session via `thinkclient_drives`:

1. In **Windows App** on Mac, edit the `panda-control` connection
2. Go to **Devices & Audio → Folders**
3. Enable **"Redirect local folders"** and add Mac folders to share
4. Shared folders appear at `~/thinkclient_drives/` on the LP3D during the RDP session

To disable drive redirection entirely, add to `/etc/xrdp/xrdp.ini` under `[Globals]`:
```ini
enable_shared_drives=false
```

### 8.7 Notes

- Physical display runs **GNOME on Xorg**. RDP session runs **XFCE4** - different UI, same underlying system.
- Ubuntu 24.04 defaults to **Wayland**. Session must be **Xorg** for xrdp. Select **Ubuntu on Xorg** at the GDM login screen (gear icon).
- VNC via `x11vnc` was evaluated but xrdp was preferred for built-in compression and stability.

---

## 9. Network Configuration — Static IP

panda-control is the K3s control plane. Its Ethernet IP must be stable — if it changes, the cluster breaks. Ubuntu 24.04 cloud images use `cloud-init` to manage network config, which means `50-cloud-init.yaml` controls the interface with `dhcp4: true` by default. Without fixing this, the IP is held stable only by a router DHCP reservation, which is not a reliable guarantee.

### 9.1 Identify the Active Ethernet Interface

The Ethernet interface name differs between machines — do not assume it.

```bash
ip link show
# Look for the enp* interface that is UP and not a virtual interface (flannel, cni0, veth*)
# panda-control: enp2s0
# panda-worker:  enp1s0
```

Confirm it has an active IP and note the current address and gateway:

```bash
ip addr show <interface>
ip route show | grep default
# default via <your-gateway-ip> dev <interface> proto dhcp src <your-static-ip>
#                                                        ^^^^ still a DHCP lease — needs fixing
```

### 9.2 What Was Found on panda-control

```bash
ls /etc/netplan/
# 01-network-manager-all.yaml   ← sets renderer: NetworkManager globally
# 50-cloud-init.yaml            ← enp2s0 dhcp4: true + WiFi config (cloud-init managed)
# 90-NM-c468eb42-*.yaml         ← NetworkManager WiFi connection (auto-generated)
```

Three issues:
- `50-cloud-init.yaml` controlling `enp2s0` with `dhcp4: true` — would reset on reboot
- No cloud-init network disable config in `/etc/cloud/cloud.cfg.d/`
- Netplan file permissions too open (netplan warning on apply)

### 9.3 Disable cloud-init Network Management

Prevents cloud-init from regenerating `50-cloud-init.yaml` and overwriting static config on reboot.

```bash
sudo tee /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg <<EOF
network: {config: disabled}
EOF
```

### 9.4 Write Static IP Config

Overwrite `50-cloud-init.yaml` with a static Ethernet-only config. WiFi (`wlo1`) is disabled and removed from this file.

```bash
sudo tee /etc/netplan/50-cloud-init.yaml <<EOF
network:
  version: 2
  ethernets:
    enp2s0:
      dhcp4: false
      addresses:
        - <your-static-ip>/22
      routes:
        - to: default
          via: <your-gateway-ip>
      nameservers:
        addresses:
          - 1.1.1.1
          - 8.8.8.8
EOF
```

> **Subnet is /22, not /24.** The home network uses a /22 block. Preserve the exact prefix from `ip addr show`.

> **Interface is `enp2s0`**, not `enp1s0`. panda-control and panda-worker have different Ethernet interface names — always verify with `ip link show` before writing the config.

### 9.5 Fix Netplan File Permissions

```bash
sudo chmod 600 /etc/netplan/01-network-manager-all.yaml
sudo chmod 600 /etc/netplan/50-cloud-init.yaml
sudo chmod 600 /etc/netplan/90-NM-c468eb42-54ff-4b88-bec2-598d0e82f133.yaml
```

### 9.6 Apply and Verify

```bash
sudo netplan apply

ip addr show enp2s0
# inet line should show valid_lft forever (not a lease countdown)

ip route show | grep default
# proto static  (not proto dhcp)
```

---

## 10. Session Type Verification

```bash
echo $XDG_SESSION_TYPE   # expected: x11
echo $DISPLAY            # expected: :0
```

If Wayland is detected after a reboot, log out and re-select **Ubuntu on Xorg** at the GDM login screen.

---

## 11. Known Limitations

| Limitation | Detail |
|---|---|
| M-Key is x2, not x4 | LP3 Delta M-Key wired for x2 lanes. DX-M1 negotiates down from x4 to x2. Bandwidth is 8 Gb/s at Gen2 - sufficient for 25 TOPS sustained inference. |
| Gen2 required for stability | Gen1 (2.5 GT/s) causes DMA header overflow during DX-M1 firmware init. Always use Gen2 or higher. |
| B-Key SATA only | B-Key slot is wired for SATA signals. NVMe M.2 drives will not work in the B-Key slot. |
| Wayland incompatible with xrdp | xrdp requires an X11 session. Must log in with Ubuntu on Xorg at GDM. |
| gnome-remote-desktop conflicts with xrdp | Must be masked at both system and user level - see Section 8.2. |
| 64GB eMMC | OS is on SATA SSD. eMMC is kept as a recovery boot device and excluded from auto-mount via udev rule. |

---

## 12. Key File Locations

| File | Purpose |
|---|---|
| `/usr/src/dxrt-driver-dkms-2.1.0-2/` | DKMS kernel module source |
| `~/dx-all-suite/dx-venv/` | Primary Python venv for inference |
| `~/dx-all-suite/workspace/res/models/` | Pre-compiled NPU models |
| `~/npu-demos/webcam_yolo.py` | Object detection demo |
| `~/npu-demos/webcam_face.py` | Face detection demo |
| `/etc/xrdp/xrdp.ini` | xrdp configuration |
| `/etc/xrdp/cert.pem`, `/etc/xrdp/key.pem` | xrdp TLS certificate |
| `~/.xsession` | xrdp session startup (`startxfce4`) |

---

## 13. System Summary

```
delta@panda-control (Node 01)
├── Hardware
│   ├── LattePanda 3 Delta (Intel N5105, 8GB RAM)
│   ├── 64GB eMMC           ← Recovery OS (auto-mount disabled via udev)
│   ├── B-Key slot          ← Transcend 430S 512GB SATA SSD (OS + data)
│   └── M-Key slot          ← DeepX DX-M1
│       ├── PCIe Gen2 x2
│       ├── 3.92GiB LPDDR5 @ 5200 Mbps
│       └── 3x NPU cores @ 1000 MHz · 25 TOPS
├── BIOS
│   ├── SATA Controller: Enabled
│   ├── PCIe Root Port 1: Gen2
│   ├── PCIe Root Port 5: Gen2
│   └── PCIe Root Port 6: Gen2
├── Drivers
│   ├── dx_dma.ko          (PCIe DMA driver, DKMS managed)
│   └── dxrt_driver.ko     (RT interface driver, DKMS managed)
├── Software
│   ├── dx-all-suite        (SDK, runtime, model zoo)
│   ├── dxrt-cli            (device status and management)
│   └── dxcom               (model compiler, ONNX → DXNN)
├── Orchestration
│   ├── K3s v1.34.6         (control plane)
│   ├── Local registry      (NodePort 32034)
│   ├── Prometheus          (kube-prometheus-stack)
│   └── Grafana             (NodePort 32000)
├── Inference
│   └── yolov8n-inference.service  (FastAPI, port 8000, systemd)
│       ├── Model: YoloV8N.dxnn (25 TOPS NPU)
│       ├── GET  /health
│       ├── POST /infer
│       └── GET  /metrics  (Prometheus)
├── Status API
│   └── status-api.service  (FastAPI, port 8001, systemd)
│       └── GET  /status  → CPU%, temp, load1 for both nodes (for Inky Frame)
└── Remote Access
    ├── SSH (port 22)
    └── xrdp / XFCE4 (port 3389)
```

---

## 14. References

- [DeepX Developer Portal](https://developer.deepx.ai)
- [dx-all-suite README](~/dx-all-suite/README.md)
- [xrdp Documentation](https://github.com/neutrinolabs/xrdp)
- [SCRFD Face Detection Paper](https://arxiv.org/abs/2105.04714)
- [DX-M1 Setup Guide](/docs/hardware/dx-m1-setup-guide.md) - Full installation guide
- [ADR-0001: DeepX DX-M1 vs Hailo-8](/docs/adr/0001-choosing-deepx-dxm1-over-hailo8.md) - Hardware selection rationale
- [Thermal Sandwich Guide](/docs/hardware/thermal-sandwich.md) - Thermal management guide
