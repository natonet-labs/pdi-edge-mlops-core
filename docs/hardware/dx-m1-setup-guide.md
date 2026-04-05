# DX-M1 AI Accelerator on LattePanda 3 Delta - Complete Setup Guide

**Hardware:** DEEPX DX-M1 M.2 AI Accelerator + LattePanda 3 Delta (Intel N5105)  
**OS:** Ubuntu 24.04 LTS  
**Status:** Fully validated and documented from scratch  
**Last Updated:** March 2026 (Corrected PCIe configuration for dual-slot support)

---

## Table of Contents

1. [Hardware Overview](#1-hardware-overview)
2. [Storage Configuration](#2-storage-configuration)
3. [Understanding PCIe Root Port Configuration](#3-understanding-pcie-root-port-configuration)
4. [BIOS Configuration](#4-bios-configuration)
5. [OS Installation](#5-os-installation)
6. [Verifying PCIe Enumeration](#6-verifying-pcie-enumeration)
7. [Driver Installation](#7-driver-installation)
8. [DX-RT Runtime Installation](#8-dx-rt-runtime-installation)
9. [DX-COM Compiler Installation](#9-dx-com-compiler-installation)
10. [Permissions Setup](#10-permissions-setup)
11. [Persistent Module Loading](#11-persistent-module-loading)
12. [Verification](#12-verification)
13. [Thermal Management](#13-thermal-management)
14. [System Summary](#14-system-summary)
15. [Known Limitations](#15-known-limitations)
16. [Troubleshooting Reference](#16-troubleshooting-reference)

---

## 1. Hardware Overview

| Component | Detail |
| --- | --- |
| SBC | LattePanda 3 Delta |
| CPU | Intel Celeron N5105 (Jasper Lake, 4-core, 10W TDP) |
| RAM | 8GB LPDDR4 |
| Storage (OS) | 64GB onboard eMMC |
| Storage (Data) | Transcend 430S 256GB SATA SSD (B-Key slot) |
| AI Accelerator | DEEPX DX-M1 M.2 2280 |
| NPU Performance | 25 TOPS (INT8) |
| NPU Memory | 4GB LPDDR5 |
| PCIe Interface | Gen3 x4 (runs at Gen2 x2 on this board) |
| BIOS Version | S70JR200-CN51G-8G-A |



---

## 2. Storage Configuration

**Both the M-Key (DX-M1) and B-Key (SATA SSD) slots work simultaneously without modification.** No external enclosures or workarounds are required.

### 2.1. Slot Configuration

- **M-Key (2280):** DEEPX DX-M1 AI Accelerator
- **B-Key (2242/2252/2280):** Transcend 430S 256GB SATA SSD (or any SATA M.2 device)
- **eMMC (64GB):** Ubuntu 24.04 LTS OS

### 2.2. Assembly

1. Install the DX-M1 into the M.2 M-Key slot (top slot, longer connector)
2. Install the Transcend 430S into the M.2 B-Key slot (bottom slot, shorter connector with offset notch)
3. Power on the system

Both devices will be enumerated by the BIOS and OS simultaneously.

---

Here's the corrected verbiage for Section 3:

---

## 3. Understanding PCIe Root Port Configuration

### Root Cause of Initial Non-Detection

The Intel N5105 (Jasper Lake) has only **8 PCIe lanes total**. These are distributed among multiple Root Ports on the PCH (Platform Controller Hub). The actual hardware device address-to-function mapping is:

- **Device 1c.0 (PCIe Root Port):** M-Key slot (x2 lanes) — connects to DX-M1
- **Device 1c.6 (PCIe Root Port):** Ethernet Controller I225-V (x1 lane)
- **Device 17.0 (SATA Controller):** Drives SATA protocol signals to B-Key slot (no PCIe lanes, pure SATA)

By default, the BIOS allocates these Root Ports dynamically during boot. However, **PCIe speed negotiation can fail or behave unpredictably if a Root Port is set to "Auto" (automatic speed detection)**. This was the root cause of the DX-M1 not enumerating: the firmware handshake would time out during DMA buffer initialization on a Root Port stuck at Gen1 (2.5 GT/s).

### The Solution (Not SATA Disabling)

**Force Root Port 1c.0 (M-Key) and Root Port 1c.6 (Ethernet) to PCIe Gen2 (5.0 GT/s).** This eliminates speed negotiation ambiguity and stabilizes the fabric:

- Gen2 (5.0 GT/s) is sufficient for both the Ethernet controller and the DX-M1 firmware initialization
- The DX-M1 can still run full inference at Gen2 x2 (8 Gb/s bandwidth = 25 TOPS sustained)
- SATA Controller remains **enabled**, allowing the B-Key slot to work for SATA SSDs
- No hardware features are sacrificed

### Why "Disable SATA" Was Wrong

Early troubleshooting appeared to succeed by disabling SATA, but this was coincidental. Disabling SATA triggered a BIOS re-enumeration that **forced root port assignment to complete before DX-M1 initialization, masking the real problem: Gen1 speed.** Once Root Ports were explicitly set to Gen2, SATA no longer needed to be disabled.

---

## 4. BIOS Configuration

Enter BIOS by pressing **DEL** repeatedly at POST.

### Required Settings

#### 4.1 Set PCIe Root Port 1 Speed to Gen2

Navigate to:
```
Chipset → PCH-IO Configuration → PCI Express Configuration → Root Port 1
```

Set:
```
PCIe Speed: Gen2
```

**Why Gen2?** Gen1 (2.5 GT/s) causes DMA header overflow during DX-M1 firmware initialization. The firmware timeout leads to non-enumeration. Gen2 (5.0 GT/s) is stable and sufficient for all devices on this board.

#### 4.2 Set PCIe Root Ports 5/6 Speed to Gen2

Navigate to:
```
Chipset → PCH-IO Configuration → PCI Express Configuration → Root Port 5 & Root Port 6
```

Set:
```
PCIe Speed: Gen2 (for both)
```

**Why?** Root Ports 5 and 6 are bonded as a x2 link to the M-Key slot. Forcing explicit speed prevents negotiation ambiguity during DX-M1 firmware handshake.

#### 4.3 Verify SATA Controller is Enabled

Navigate to:
```
Chipset → PCH-IO Configuration → SATA Configuration → SATA Controller
```

Verify:
```
SATA Controller: Enabled (default)
```

**Keep SATA enabled.** The B-Key slot depends on the SATA Controller to drive SATA signal lines to SATA M.2 devices.

#### 4.4 Save and Reboot

Save changes and allow the system to boot fully into the OS before proceeding.

---

## 5. OS Installation

**Recommended OS:** Ubuntu 24.04 LTS

The DEEPX DXNN SDK and DX-RT runtime are tested and packaged specifically for Ubuntu 20.04, 22.04, and 24.04 LTS. Other distributions (including Linux Mint, which is Ubuntu-based) may work but are not officially supported and may cause library dependency issues.

Install Ubuntu 24.04 LTS to the onboard eMMC. Standard installation, no special partitioning required.

---

## 6. Verifying PCIe Enumeration

After BIOS configuration and OS boot, verify **both the DX-M1 and SATA SSD are enumerated**:

### 6.1 Check DX-M1 PCIe Presence

```bash
lspci -vn | grep 1ff4
```

Expected output:

```
01:00.0 1200: 1ff4:0000 (rev 01)
```

If nothing appears, the DX-M1 is not enumerated. Go back to BIOS and verify Root Ports 1, 5, and 6 are set to Gen2 (not Auto).

### 6.2 Check Full Bus Tree

```bash
lspci -tv
```

Expected output (DX-M1 and SATA-based Ethernet on separate Root Ports):

```
-[0000:00]-+-00.0  Intel Corporation Device 4e24
           +-1c.0-[01]----00.0  DEEPX Co., Ltd. DX_M1
           +-1c.6-[02]----00.0  Intel Corporation Ethernet Controller I225-V
```

Note: Device 17.0 (SATA Controller) will also appear on the main bus. The SATA SSD in the B-Key slot will not show in lspci (it's behind the SATA Controller, not directly on PCIe).

### 6.3 Check SATA SSD Detection

```bash
lsblk -o NAME,MODEL,SIZE,TYPE,TRAN
```

Expected output (Transcend 430S and eMMC both present):

```
sda          TS256GMTS430S 238.5G disk sata
├─sda1                         1G part 
└─sda2                     237.4G part 
mmcblk1                     58.2G disk mmc
├─mmcblk1p1                    1G part mmc
└─mmcblk1p2                 57.2G part mmc
```

If `sda` doesn't appear but the DX-M1 does, check BIOS SATA Controller is **Enabled** and verify the drive is properly seated in the B-Key slot.

### 6.4 Check PCIe Speed Negotiation

```bash
sudo lspci -vvv | grep -E "LnkSta|LnkCap"
```

Expected output (DX-M1 running at Gen2 x2):

```
LnkCap:  Port #1, Speed 5GT/s, Width x2
LnkSta:  Speed 5GT/s, Width x2
```

If it shows Gen1 or Downgraded, go back to BIOS and verify your Gen2 settings were saved correctly.

---

## 7. Driver Installation

### 7.1 Install Prerequisites

```bash
sudo apt update && sudo apt install git build-essential linux-headers-$(uname -r) -y
```

### 7.2 Clone the Driver Repository

```bash
git clone https://github.com/DEEPX-AI/dx_rt_npu_linux_driver.git
cd dx_rt_npu_linux_driver/modules
```

### 7.3 Build the Driver

```bash
make DEVICE=m1 PCIE=deepx 2>&1 | tail -10
```

The `.ko` files are built in the source tree but not automatically installed. Manually install them:

```bash
sudo mkdir -p /lib/modules/$(uname -r)/extra
sudo cp ~/dx_rt_npu_linux_driver/modules/pci_deepx/dx_dma.ko /lib/modules/$(uname -r)/extra/
sudo cp ~/dx_rt_npu_linux_driver/modules/rt/dxrt_driver.ko /lib/modules/$(uname -r)/extra/
sudo depmod -A
```

### 7.4 Install udev Rules

```bash
sudo cp ~/dx_rt_npu_linux_driver/modules/dx_dma.conf /etc/modprobe.d/
sudo bash -c 'echo "SUBSYSTEM==\"dxrt\", GROUP=\"deepx\", MODE=\"0660\"" > /etc/udev/rules.d/51-deepx-udev.rules'
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 7.5 Load the Driver

```bash
sudo modprobe dx_dma
sudo modprobe dxrt_driver
```

### 7.6 Verify Driver Binding

```bash
lsmod | grep -i dx
lspci -v -s 01:00.0 | grep -i driver
```

Expected:

```
dxrt_driver    53248  0
dx_dma        520192  1 dxrt_driver
Kernel driver in use: dx_dma_pcie
```

---

## 8. DX-RT Runtime Installation

DX-RT is a C++ build - not a Python package. Download `dx_rt_vX.X.X.tar.gz` from the DEEPX Developer Portal: <https://developer.deepx.ai>

### 8.1 Install Build Dependencies

```bash
sudo apt install cmake ninja-build pkg-config libncurses-dev libncursesw5-dev -y
```

### 8.2 Extract and Build

```bash
tar -xzf ~/Downloads/dx_rt_v*.tar.gz -C ~/dx_rt_npu_linux_driver/modules/
cd ~/dx_rt_npu_linux_driver/modules/dx_rt
sudo ./build.sh --use_ort_off --use_service_off --clean
```

> **Note:** The `--use_ort_off` flag disables the ONNX Runtime dependency which is not required for basic device operation and inference.

### 8.3 Install

The build script installs binaries to `/usr/local/bin` automatically on successful build. Verify:

```bash
which dxrt-cli
```

---

## 9. DX-COM Compiler Installation

DX-COM is the model compiler for converting ONNX/PyTorch/TensorFlow models to DXNN format.

Download `dx_com-X.X.X-*.whl` from the DEEPX Developer Portal, then install:

```bash
pip3 install --break-system-packages ~/Downloads/dx_com-*.whl
```

Add the local bin to PATH if not already set:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Verify:

```bash
dxcom --version
```

Expected:

```
DX-COM (DEEPX Compiler) X.X.X
Copyright (C) 2022-2025 DEEPX Inc.
Target Hardware: M1
```

---

## 10. Permissions Setup

Create a `deepx` group and add your user to it for non-root device access:

```bash
sudo groupadd deepx
sudo chown root:deepx /dev/dxrt0
sudo chmod 660 /dev/dxrt0
sudo usermod -aG deepx $USER
```

Activate group membership in current session:

```bash
newgrp deepx
```

Or log out and back in for permanent effect. Verify non-root access:

```bash
dxrt-cli --status
```

---

## 11. Persistent Module Loading

Ensure drivers load automatically on every boot:

```bash
echo "dx_dma" | sudo tee -a /etc/modules
echo "dxrt_driver" | sudo tee -a /etc/modules
```

Verify:

```bash
cat /etc/modules | grep dx
```

Expected:

```
dx_dma
dxrt_driver
```

---

## 12. Verification

Reboot the system and confirm everything comes up automatically:

```bash
sudo reboot
```

After reboot, run the full verification sequence:

```bash
# PCIe enumeration
lspci -vn | grep 1ff4

# SATA SSD enumeration
lsblk -o NAME,MODEL,SIZE,TYPE,TRAN | grep -E "TS256|sda"

# Driver loaded
lsmod | grep dx

# Device fully operational
dxrt-cli --status
```

### Expected Final Output

```
DXRT v3.2.0
=======================================================
 * Device 0: M1, Accelerator type
---------------------   Version   ---------------------
 * RT Driver version   : v2.1.0
 * PCIe Driver version : v2.0.1
-------------------------------------------------------
 * FW version          : v2.1.5
--------------------- Device Info ---------------------
 * Memory : LPDDR5 5200 Mbps, 3.92GiB
 * Board  : M.2, Rev 1.5
 * Chip Offset : 0
 * PCIe   : Gen2 X2 [01:00:00]

NPU 0: voltage 750 mV, clock 1000 MHz, temperature 6X'C
NPU 1: voltage 750 mV, clock 1000 MHz, temperature 6X'C
NPU 2: voltage 750 mV, clock 1000 MHz, temperature 6X'C
=======================================================
```

---

## 13. Thermal Management

The DX-M1 requires a **"Level-Fill Thermal Sandwich"** to maintain stable temperatures under sustained inference load. Without it, the NPU chip exceeds 60°C due to the uneven board surface trapping heat.

> The specific materials below are for the **Titan Case** (ABS plastic enclosure). The underlying problem — uneven board surface causing poor heatsink contact — applies to any enclosure.

### The Problem

The DX-M1 board is uneven: the main NPU chip sits higher than the surrounding components. Placing a single thick thermal pad over everything creates air pockets in the valleys that act as insulators rather than conductors.

### Materials

| Item | Purpose |
|---|---|
| 1mm thermal pad | Valley fill — brings recesses flush with the chip surface |
| 0.5mm thermal pad | Cap layer — continuous bridge across the entire module |
| Small aluminum heatsink | Heat dissipation |
| Kapton tape | Electrical isolation over gold components |

### Build Steps

#### Step 1 — Safety (Kapton tape)
Cover the small gold components around the main NPU chip with Kapton tape to prevent thermal pad material from causing electrical shorts.

#### Step 2 — Valley fill (1mm pad)
Cut the 1mm pad into small pieces and place them into the recesses around the main chip. Goal: bring the valleys up to the same height as the chip surface. Do not use one large pad — it will bow and create air gaps.

#### Step 3 — Cap (0.5mm strip)
Lay a single continuous 0.5mm strip across the entire module, covering both the 1mm filler pieces and the main chip. This creates a flat, solid bridge for the heatsink.

#### Step 4 — Heatsink
Place the heatsink on top. Ensure a **small air gap** between the heatsink base and the plastic case floor — direct contact with plastic traps heat and prevents convection.

### Why It Works

- **No trapped air:** Valleys filled with conductive pad material instead of dead air
- **No flex:** Even contact prevents the board from bowing under heatsink weight
- **Convection:** Air gap at the base allows airflow across the heatsink fins

**Result:** Stable idle temperatures of ~52°C (vs. 60°C+ without thermal management).

---

## 14. System Summary

```
<your-username>@panda-control
├── Hardware
│   ├── LattePanda 3 Delta (Intel N5105, 8GB RAM)
│   ├── 64GB eMMC  ←  Ubuntu 24.04 LTS (OS)
│   ├── B-Key slot  ←  Transcend 430S 256GB SATA SSD (data storage)
│   └── M-Key slot  ←  DEEPX DX-M1
│       ├── PCIe Gen2 x2
│       ├── 3.92GiB LPDDR5 @ 5200Mbps
│       └── 3x NPU cores @ 1000MHz, 25 TOPS
├── BIOS
│   ├── SATA Controller: Enabled
│   ├── PCIe Root Port 1: Gen2
│   ├── PCIe Root Port 5: Gen2
│   └── PCIe Root Port 6: Gen2
├── Storage
│   ├── /dev/mmcblk1  (eMMC, 64GB)
│   └── /dev/sda  (SATA SSD, 238.5GB)
├── Drivers
│   ├── dx_dma.ko  (PCIe DMA driver)
│   └── dxrt_driver.ko  (RT interface driver)
└── Software
    ├── dxrt-cli  (device status and management)
    └── dxcom  (model compiler, ONNX → DXNN)
```

---

## 15. Known Limitations

| Limitation | Detail |
| --- | --- |
| M-Key is x2, not x4 | LP3 Delta M-Key is wired for x2 lanes, not x4. DX-M1 can run at x4 but negotiates down to x2 on this board. Bandwidth is still 8 Gb/s Gen2, sufficient for 25 TOPS inference. |
| Gen2 required for stability | Gen1 speed (2.5 GT/s) causes DMA header overflow during DX-M1 firmware initialization. Must use Gen2 or higher. |
| B-Key SATA only | B-Key slot is wired for SATA signals; NVMe M.2 drives will not work in the B-Key slot. |


---

## 16. Troubleshooting Reference

### DX-M1 not appearing in `lspci`

**Check BIOS PCIe Speed settings first:**

* Verify **Root Port 1 is Gen2** (not Auto)
* Verify **Root Port 5 is Gen2** (not Auto)
* Verify **Root Port 6 is Gen2** (not Auto)
* Save settings and reboot
* After reboot, run: `lspci -vn | grep 1ff4`

If still not appearing:
* Check physical seating of M.2 module and retention screw
* Run `sudo dmesg | grep -i pci` and look for Gen1 or enumeration errors

### SATA SSD not appearing in `lsblk`

* Verify **SATA Controller is Enabled** in BIOS (not Disabled)
* Check physical seating in B-Key slot
* Run `lsblk` and look for `/dev/sda`
* If device node exists but partitions don't, the drive may need formatting

### `modprobe: FATAL: Module not found`

* The DX-RT build script does not auto-install `.ko` files
* Manually copy from source tree: see [Section 7.3](#73-build-the-driver)

### `dxrt-cli: Device not found`

* Drivers not loaded - run `lsmod | grep dx`
* Device node missing - run `ls /dev/dxrt*`
* If device node exists but access denied - check group membership: `groups $USER`

### `Fail to initialize device 0` / PCIe Bus Errors in dmesg

**This indicates Gen1 speed negotiation failure:**

```
[xx.xxxxxx] dxrt: HeaderOF
[xx.xxxxxx] dxrt: NonFatalErr
[xx.xxxxxx] dxrt: polling_ack: timeout
```

**Fix:**
* Go to BIOS and set **Root Port 1, 5, 6 to Gen2** (not Auto)
* Save and reboot
* Verify with: `sudo lspci -vvv | grep -E "LnkSta|LnkCap"`
* Should show: `LnkSta: Speed 5GT/s, Width x2`

### Drivers not loading after reboot

* Check `/etc/modules` contains `dx_dma` and `dxrt_driver`
* If missing, re-add: see [Section 11](#11-persistent-module-loading)
* Verify modules are installed: `ls /lib/modules/$(uname -r)/extra/dx*.ko`

### Both M-Key and B-Key work but one disappears after reboot

* Ensure drivers are loaded in correct order: `dx_dma` before `dxrt_driver`
* Verify `/etc/modules` has the correct order
* Check `/etc/modprobe.d/dx_dma.conf` for any disable directives

---

*Documented from a complete bring-up on LattePanda 3 Delta with BIOS S70JR200-CN51G-8G-A, Ubuntu 24.04 LTS, kernel 6.17, DX-RT v3.2.0, DX-COM v2.2.1. Corrected March 2026 to reflect proper Root Port speed configuration enabling simultaneous M-Key and B-Key operation.*
