"""Real-ESRGAN conversion and tiled 200% display-image enhancement."""
from functools import lru_cache
from math import prod
from pathlib import Path
import re
import sqlite3
import struct

import cv2
import numpy as np

from app.core.config import settings
from app.services.frames.privacy import blur_regions, face_regions

UPSCALE_MARKER = "upscale_2x"


def checkpoint_weights(path):
    """Read the user's Draw Things F16 SQLite checkpoint without unpickling code."""
    import torch

    state = {}
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        for name, layout, dtype, dimensions, blob in connection.execute(
            "SELECT name,format,datatype,dim,data FROM tensors"
        ):
            match = re.fullmatch(r"__realesrgan_x4plus__\[t-(\d+)-([01])\]", name)
            if not match or layout != 1 or dtype != 131072:
                raise ValueError("Unsupported Draw Things tensor format")
            node, parameter = map(int, match.groups())
            shape = tuple(value for value in struct.unpack("<" + "i" * (len(dimensions) // 4), dimensions) if value)
            count = prod(shape)
            if not shape or count <= 0 or len(blob) < count * 2 or len(blob) - count * 2 >= 128:
                raise ValueError("Invalid checkpoint tensor dimensions")
            if node == 0:
                key = "conv_first"
            elif 1 <= node <= 345:
                offset = node - 1
                key = f"body.{offset // 15}.rdb{offset % 15 // 5 + 1}.conv{offset % 5 + 1}"
            elif 346 <= node <= 350:
                key = ["conv_body", "conv_up1", "conv_up2", "conv_hr", "conv_last"][node - 346]
            else:
                raise ValueError("Unexpected Real-ESRGAN layer")
            key += ".weight" if parameter == 0 else ".bias"
            if key in state:
                raise ValueError("Duplicate checkpoint tensor")
            # NNC pads small tensors to 128 bytes; dimensions define the payload.
            values = np.frombuffer(blob, dtype="<f2", count=count).reshape(shape).astype(np.float32)
            if not np.isfinite(values).all():
                raise ValueError("Non-finite checkpoint weights")
            state[key] = torch.from_numpy(values)
    if len(state) != 702:
        raise ValueError("Incomplete Real-ESRGAN x4+ checkpoint")
    return state


@lru_cache(maxsize=1)
def upscaler():
    import torch
    from spandrel import ImageModelDescriptor, ModelLoader

    torch.set_num_threads(1)
    model = ModelLoader().load_from_state_dict(checkpoint_weights(settings.upscale_model_path))
    if not isinstance(model, ImageModelDescriptor) or model.scale != 4:
        raise ValueError("Expected an image-to-image Real-ESRGAN x4+ model")
    return model.cpu().eval()


def tiled_upscale(image, model):
    """Run x4 tiles with overlap, retaining only their 2x center to bound memory."""
    import torch

    height, width = image.shape[:2]
    output = np.empty((height * 2, width * 2, 3), np.uint8)
    tile, padding = settings.upscale_tile_size, 16
    for top in range(0, height, tile):
        for left in range(0, width, tile):
            bottom, right = min(height, top + tile), min(width, left + tile)
            x0, y0 = max(0, left - padding), max(0, top - padding)
            x1, y1 = min(width, right + padding), min(height, bottom + padding)
            rgb = cv2.cvtColor(image[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)
            tensor = torch.from_numpy(rgb.transpose(2, 0, 1).copy()).float().unsqueeze(0) / 255
            with torch.inference_mode():
                result = model(tensor).squeeze(0).clamp(0, 1).permute(1, 2, 0).numpy()
            result = cv2.cvtColor(np.rint(result * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
            # x4+ restores at native scale; Lanczos produces the requested 200%.
            result = cv2.resize(result, ((x1 - x0) * 2, (y1 - y0) * 2), interpolation=cv2.INTER_LANCZOS4)
            output[top * 2:bottom * 2, left * 2:right * 2] = result[
                (top - y0) * 2:(bottom - y0) * 2, (left - x0) * 2:(right - x0) * 2,
            ]
    return output


def enhance_saved_image(content, enhancements):
    image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape[0] * image.shape[1] * 4 > settings.max_image_pixels:
        raise ValueError("Invalid upscaling input")
    if "face_blur" in enhancements:
        # Legacy rows have no retained blur coordinates. Do not run a generative
        # model over those regions: preserve their existing privacy blur at 2x.
        output = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)
        method = "upscale_lanczos_privacy"
    else:
        output = tiled_upscale(image, upscaler())
        output = blur_regions(output, face_regions(output))
        method = "realesrgan_x4plus_2x"
    return output, method
