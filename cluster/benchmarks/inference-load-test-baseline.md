# Inference Load Test Baseline

**Date:** 2026-04-06
**Tool:** [hey](https://github.com/rakyll/hey)
**Test image:** JPEG, 592 KB
**Concurrency:** 10
**Requests:** 2000 per service
**Node:** panda-control (localhost) — all NPU services run as host-native systemd processes

---

## Results

| Model | Port | Req/s | p50 | p95 | p99 | Slowest |
|---|---|---|---|---|---|---|
| MobileNetV2 | 8003 | 162.7 | 61ms | 66ms | 73ms | 78ms |
| SCRFD500M | 8002 | 33.1 | 298ms | 327ms | 348ms | 364ms |
| YOLOv8N | 8001 | 17.4 | 570ms | 610ms | 645ms | 677ms |
| YOLOv8N-SEG | 8004 | 8.3 | 1202ms | 1257ms | 1304ms | 1377ms |

All 2000 requests returned HTTP 200 for every service.

---

## Observations

- **MobileNetV2 is the fastest by far (162.7 req/s)** — classification outputs a single label+confidence score with no bounding box or mask computation. The NPU handles this workload deterministically; p50→p99 spread is only 12ms.
- **SCRFD500M is ~5× slower than MobileNetV2** — face detection adds bounding box regression and anchor decoding. Still consistent, with a tight 50ms p50→p99 spread.
- **YOLOv8N is ~2× slower than SCRFD** — general object detection across 80 classes with multi-scale anchors and NMS postprocessing.
- **YOLOv8N-SEG is the slowest (8.3 req/s)** — segmentation adds prototype mask generation (32×mh×mw tensor), matrix multiply, sigmoid, resize, and contour extraction on top of standard YOLOv8N. p99 is ~2× the p50, indicating variable mask complexity per image.
- **Latency is stable under sustained load.** Comparing 200-request and 2000-request runs, latency numbers are nearly identical — the DX-M1 NPU shows no thermal throttling or queue buildup at 10 concurrent requests.

---

## Test Command

```bash
BOUNDARY="----HeyBoundary1234"
IMAGE_PATH=~/me.jpg
BODY_FILE=/tmp/hey-body.bin

printf -- "--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"me.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n" "$BOUNDARY" > "$BODY_FILE"
cat "$IMAGE_PATH" >> "$BODY_FILE"
printf "\r\n--%s--\r\n" "$BOUNDARY" >> "$BODY_FILE"

hey -n 2000 -c 10 -m POST \
  -T "multipart/form-data; boundary=----HeyBoundary1234" \
  -D /tmp/hey-body.bin \
  http://localhost:<port>/infer
```
