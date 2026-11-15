"""CLIP image encoder: turns a picture into a 512-number vector (embedding)."""
import threading

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

MODEL_NAME = "openai/clip-vit-base-patch32"
DIM = 512

_lock = threading.Lock()
_model = None
_processor = None


def _load():
    global _model, _processor
    with _lock:
        if _model is None:
            _processor = CLIPProcessor.from_pretrained(MODEL_NAME)
            _model = CLIPModel.from_pretrained(MODEL_NAME).eval()
    return _model, _processor


def warm_up():
    _load()


def embed_images(images: list[Image.Image]) -> list[list[float]]:
    """Return one L2-normalised vector per image (so dot product == cosine similarity)."""
    model, processor = _load()
    inputs = processor(images=[im.convert("RGB") for im in images], return_tensors="pt")
    with torch.no_grad():
        feats = model.get_image_features(**inputs)
    if not torch.is_tensor(feats):          # newer transformers versions return an output object
        feats = feats.pooler_output
    feats = feats / feats.norm(dim=-1, keepdim=True)
    return feats.tolist()


def embed_image(image: Image.Image) -> list[float]:
    return embed_images([image])[0]


def to_pgvector(vec: list[float]) -> str:
    """pgvector accepts a text literal like '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
