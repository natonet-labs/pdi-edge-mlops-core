# MobileNetV2 Classification Service

**Model:** `MobileNetV2_2.dxnn`
**Port:** 8003
**Task:** ImageNet image classification (1000 classes)
**Latency:** ~2ms on DX-M1

---

## What It Does

Classifies an entire image into one of 1000 ImageNet categories. Returns a single class ID — no bounding boxes, no confidence score.

```bash
curl -X POST http://localhost:8003/infer -F "file=@image.jpg"
# {"latency_ms": 1.96, "class_id": 741}
```

---

## Why It Has Limited Production Value

**No confidence score.** The DX-M1 compiler embeds argmax inside the model itself. The output tensor (`argmax_output`, shape `[1]`, dtype `uint16`) is the winning class ID only — the probability distribution is discarded before the model returns. There is no way to know if the model was 95% confident or 12% confident.

**Whole-image classification.** This cluster is built for detection and analysis workloads that operate on regions of a frame. Classifying an entire image into a single label is not useful for multi-object edge CV scenes.

**1000 generic ImageNet classes.** Useful for benchmarking, not for any real task on this cluster.

---

## Why It Was Built Anyway

MobileNetV2 is the standard "hello world" classification model shipped with the DX-M1 SDK. Building this service as Phase 2 Step 1 accomplished three things:

1. **Discovered the argmax_output behavior.** The DX-M1 compiler can embed argmax inside the compiled model, returning a class ID directly instead of raw logits. This is not obvious from the SDK docs and affects how postprocessing must be written for any classification model on this hardware.

2. **Established the classification service pattern.** `app.py` shows how to handle a model that returns a scalar output rather than a detection array or keypoint set.

3. **Validated the pipeline.** Confirmed the systemd → ExternalName → Prometheus pattern works for a third concurrent service alongside yolov8n and scrfd.

The service is kept running because it costs nothing and provides a reference implementation. It is not used in any production workload on this cluster.

---

## Key Technical Finding

The original `app.py` assumed the model returned 1000 float logits and applied softmax + top-k. This produced `class_id: 0, confidence: 1.0` on every request regardless of input — a silent wrong answer. The correct output shape was found via:

```python
engine.get_output_tensors_info()
# [{'name': 'argmax_output', 'shape': [1], 'dtype': numpy.uint16, 'elem_size': 2}]
```

**Rule for DX-M1 classification models:** always call `get_output_tensors_info()` before writing postprocessing. Do not assume the output is raw logits.
