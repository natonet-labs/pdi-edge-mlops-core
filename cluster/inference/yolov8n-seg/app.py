import os
import time
import cv2
import numpy as np
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
from dx_engine import InferenceEngine

MODEL_PATH = os.environ["YOLOV8N_SEG_MODEL_PATH"]
CONF_THRESHOLD = 0.35
NMS_THRESHOLD = 0.45

COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
]

# Prometheus metrics
MODEL_INFO = Gauge("model_info", "Active model version info", ["model", "version"])
REQUEST_COUNT = Counter("inference_requests_total", "Total inference requests")
INFERENCE_LATENCY = Histogram(
    "inference_latency_ms", "NPU inference latency in milliseconds",
    buckets=[5, 10, 15, 20, 30, 50, 100, 200]
)
DETECTION_COUNT = Histogram(
    "detections_per_frame", "Number of segmentation detections returned per inference",
    buckets=[0, 1, 2, 5, 10, 20, 50]
)

_engine_ctx = None
engine = None
input_height = None
input_width = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine_ctx, engine, input_height, input_width
    _engine_ctx = InferenceEngine(MODEL_PATH)
    engine = _engine_ctx.__enter__()
    info = engine.get_input_tensors_info()
    input_height = info[0]["shape"][1]
    input_width = info[0]["shape"][2]
    MODEL_INFO.labels(model="YOLOv8N-SEG", version=engine.get_model_version()).set(1)
    yield
    _engine_ctx.__exit__(None, None, None)


app = FastAPI(lifespan=lifespan)


def letterbox(img, target_h, target_w):
    h, w = img.shape[:2]
    gain = min(target_h / h, target_w / w)
    new_w = int(round(w * gain))
    new_h = int(round(h * gain))
    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    pad_top = int(round((target_h - new_h) / 2 - 0.1))
    pad_left = int(round((target_w - new_w) / 2 - 0.1))
    pad_bottom = target_h - new_h - pad_top
    pad_right = target_w - new_w - pad_left
    img = cv2.copyMakeBorder(
        img, pad_top, pad_bottom, pad_left, pad_right,
        cv2.BORDER_CONSTANT, value=(114, 114, 114)
    )
    return img, gain, pad_top, pad_left


def postprocess(output_tensors, orig_h, orig_w, gain, pad_top, pad_left):
    # output_tensors[0]: (1, 116, N) — 4 box + 80 class scores + 32 mask coefs
    # output_tensors[1]: (1, 32, mh, mw) — prototype masks
    pred = np.transpose(np.squeeze(output_tensors[0]))  # (N, 116)

    boxes_cxcywh = pred[:, :4]
    cls_scores = pred[:, 4:84]
    mask_coefs = pred[:, 84:]

    cls_ids = np.argmax(cls_scores, axis=1)
    confidences = cls_scores[np.arange(len(cls_ids)), cls_ids]

    # Convert cxcywh -> x1y1wh for NMSBoxes
    x1 = boxes_cxcywh[:, 0] - boxes_cxcywh[:, 2] * 0.5
    y1 = boxes_cxcywh[:, 1] - boxes_cxcywh[:, 3] * 0.5
    boxes_x1y1wh = np.column_stack([x1, y1, boxes_cxcywh[:, 2], boxes_cxcywh[:, 3]])

    indices = cv2.dnn.NMSBoxes(
        boxes_x1y1wh.tolist(), confidences.tolist(), CONF_THRESHOLD, NMS_THRESHOLD
    )
    if len(indices) == 0:
        return []

    keep = np.array(indices).reshape(-1)

    # Decode prototype masks for kept detections
    proto = np.squeeze(output_tensors[1])  # (32, mh, mw)
    c, mh, mw = proto.shape
    kept_coefs = mask_coefs[keep]                          # (K, 32)
    masks = kept_coefs @ proto.reshape(c, -1)              # (K, mh*mw)
    masks = 1 / (1 + np.exp(-masks))                      # sigmoid
    masks = masks.reshape(-1, mh, mw)                     # (K, mh, mw)

    # Upscale masks from prototype resolution to input tensor resolution
    scaled_masks = np.zeros((len(keep), input_height, input_width), dtype=np.float32)
    for i, mask in enumerate(masks):
        scaled_masks[i] = cv2.resize(mask, (input_width, input_height), interpolation=cv2.INTER_LINEAR)

    results = []
    for i, idx in enumerate(keep):
        cx, cy, bw, bh = boxes_cxcywh[idx]

        # Crop mask to bounding box region (suppresses mask bleed outside the box)
        bx1 = int(np.clip(cx - bw / 2, 0, input_width))
        by1 = int(np.clip(cy - bh / 2, 0, input_height))
        bx2 = int(np.clip(cx + bw / 2, 0, input_width))
        by2 = int(np.clip(cy + bh / 2, 0, input_height))
        cropped = scaled_masks[i].copy()
        cropped[:by1, :] = 0
        cropped[by2:, :] = 0
        cropped[:, :bx1] = 0
        cropped[:, bx2:] = 0

        # Map bounding box back to original image coordinates
        ox1 = round(float(np.clip((cx - bw / 2 - pad_left) / gain, 0, orig_w - 1)), 1)
        oy1 = round(float(np.clip((cy - bh / 2 - pad_top) / gain, 0, orig_h - 1)), 1)
        ox2 = round(float(np.clip((cx + bw / 2 - pad_left) / gain, 0, orig_w - 1)), 1)
        oy2 = round(float(np.clip((cy + bh / 2 - pad_top) / gain, 0, orig_h - 1)), 1)

        # Extract largest contour polygon and map points to original image coordinates
        binary = (cropped > 0.5).astype(np.uint8)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        polygon = []
        if contours:
            largest = max(contours, key=cv2.contourArea)
            for pt in largest.reshape(-1, 2):
                px = round(float(np.clip((pt[0] - pad_left) / gain, 0, orig_w - 1)), 1)
                py = round(float(np.clip((pt[1] - pad_top) / gain, 0, orig_h - 1)), 1)
                polygon.append([px, py])

        results.append({
            "label": COCO_CLASSES[int(cls_ids[idx])],
            "confidence": round(float(confidences[idx]), 4),
            "box": {"x1": ox1, "y1": oy1, "x2": ox2, "y2": oy2},
            "polygon": polygon,
        })

    return results


@app.get("/health")
def health():
    return {"status": "ok", "model": "YOLOv8N-SEG"}


@app.post("/infer")
async def infer(file: UploadFile = File(...)):
    contents = await file.read()
    img_array = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if frame is None:
        return JSONResponse(status_code=400, content={"error": "invalid image"})

    orig_h, orig_w = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    letterboxed, gain, pad_top, pad_left = letterbox(rgb, input_height, input_width)
    inp = letterboxed[np.newaxis, ...].astype(np.uint8)

    t0 = time.perf_counter()
    outputs = engine.run([inp])
    latency_ms = (time.perf_counter() - t0) * 1000

    detections = postprocess(outputs, orig_h, orig_w, gain, pad_top, pad_left)

    REQUEST_COUNT.inc()
    INFERENCE_LATENCY.observe(latency_ms)
    DETECTION_COUNT.observe(len(detections))

    return {"latency_ms": round(latency_ms, 2), "detections": detections}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
