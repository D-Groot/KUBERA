"""
KUBERA — Input Integrity module.

Implements the actual working POC:
  1. Error Level Analysis (ELA) on the resubmitted document image, to
     surface regions that were compressed at a different quality/generation
     than the rest of the image (a classic signal of localized editing).
  2. Lightweight metadata inspection (EXIF / file-level) for signs the file
     was produced or touched by an image editor rather than a scan/photo/
     export pipeline.

The two signals are combined into a single Input Integrity score in [0, 1].
This is intentionally simple and explainable — a judge/reviewer can see
exactly why a document was flagged, which matters more for a decision-
assurance product than a black-box fraud score.
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PIL import Image, ImageChops, ExifTags


ELA_QUALITY = 90          # JPEG re-save quality used for the ELA pass
ELA_SCALE = 15            # amplification factor so diffs are visible/measurable
TILE = 24                 # px, size of the grid used to localize hot regions
HOT_REGION_THRESHOLD = 3.4  # tile score must be this many std-devs above the
                            # image mean to be reported as a flagged region

EDITOR_SOFTWARE_HINTS = [
    "photoshop", "gimp", "paint.net", "snapseed", "picsart",
    "canva", "affinity", "lightroom", "pixlr",
]


@dataclass
class IntegrityResult:
    integrity_score: float           # 0..1, higher = more trustworthy
    ela_score: float                 # 0..1, higher = more suspicious noise
    metadata_score: float            # 0..1, higher = more suspicious metadata
    flagged_regions: list = field(default_factory=list)  # [{x,y,w,h,score}]
    notes: list = field(default_factory=list)
    ela_preview_path: Optional[str] = None


def _load_as_rgb(path: str) -> Image.Image:
    img = Image.open(path)
    img = img.convert("RGB")
    return img


def _error_level_analysis(img: Image.Image):
    """Re-encode the image at ELA_QUALITY JPEG and diff against the original.

    Returns (diff_array HxWx3 uint8, tile_scores 2D array, hot_regions list).
    """
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=ELA_QUALITY)
    buf.seek(0)
    resaved = Image.open(buf)

    diff = ImageChops.difference(img, resaved)
    diff_arr = np.asarray(diff).astype(np.float32)
    gray = diff_arr.mean(axis=2)  # HxW

    h, w = gray.shape
    tiles_y = max(1, h // TILE)
    tiles_x = max(1, w // TILE)

    tile_scores = np.zeros((tiles_y, tiles_x), dtype=np.float32)
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            y0, y1 = ty * TILE, min((ty + 1) * TILE, h)
            x0, x1 = tx * TILE, min((tx + 1) * TILE, w)
            tile_scores[ty, tx] = gray[y0:y1, x0:x1].mean()

    mean, std = tile_scores.mean(), tile_scores.std() + 1e-6
    z = (tile_scores - mean) / std

    hot_regions = []
    ys, xs = np.where(z > HOT_REGION_THRESHOLD)
    for ty, tx in zip(ys, xs):
        hot_regions.append({
            "x": int(tx * TILE), "y": int(ty * TILE),
            "w": TILE, "h": TILE,
            "z_score": round(float(z[ty, tx]), 2),
        })

    # Global suspicion score. A genuine, once-compressed document has a
    # fairly uniform ELA response — text edges create noise, but no tile
    # dramatically outscores the rest. A locally re-edited + recompressed
    # region stands out as a small number of tiles with an extreme z-score.
    # We therefore key mainly off the PEAK z-score (how anomalous the worst
    # tile is), not the fraction of the image affected — an edited field is
    # small, so fraction-based scoring dilutes the signal.
    max_z = float(z.max())
    suspicious_fraction = float((z > HOT_REGION_THRESHOLD).sum()) / z.size
    peak_component = float(np.clip((max_z - HOT_REGION_THRESHOLD) / 4.0, 0, 1))
    spread_component = float(np.clip(suspicious_fraction * 40, 0, 1))
    ela_score = float(np.clip(0.75 * peak_component + 0.25 * spread_component, 0, 1))

    # amplified visual preview for the reviewer UI
    amplified = np.clip(diff_arr * ELA_SCALE, 0, 255).astype(np.uint8)
    preview = Image.fromarray(amplified)

    return preview, ela_score, hot_regions


def _metadata_inspection(path: str, img: Image.Image):
    notes = []
    suspicion_points = 0.0
    max_points = 4.0

    # 1. EXIF presence / contents
    exif = {}
    try:
        raw_exif = img.getexif()
        for tag_id, value in raw_exif.items():
            tag = ExifTags.TAGS.get(tag_id, tag_id)
            exif[tag] = value
    except Exception:
        pass

    if not exif:
        suspicion_points += 1.0
        notes.append("No EXIF metadata present (common after re-export/screenshot, "
                      "but also common after tampering — treated as a mild signal).")
    else:
        software = str(exif.get("Software", "")).lower()
        if software:
            if any(hint in software for hint in EDITOR_SOFTWARE_HINTS):
                suspicion_points += 2.0
                notes.append(f"EXIF 'Software' tag references an image editor: '{exif.get('Software')}'.")
            else:
                notes.append(f"EXIF 'Software' tag: '{exif.get('Software')}'.")

        if "DateTime" in exif and "DateTimeOriginal" in exif:
            if exif.get("DateTime") != exif.get("DateTimeOriginal"):
                suspicion_points += 1.0
                notes.append("EXIF modification timestamp differs from original capture timestamp.")

    # 2. File-level sanity checks
    try:
        size_bytes = os.path.getsize(path)
        w, h = img.size
        bytes_per_px = size_bytes / max(1, (w * h))
        if bytes_per_px < 0.05:
            suspicion_points += 1.0
            notes.append("Unusually high compression relative to resolution "
                         "(can indicate a recompressed/edited copy).")
    except Exception:
        pass

    metadata_score = float(np.clip(suspicion_points / max_points, 0, 1))
    return metadata_score, notes


def analyze_document(path: str, save_preview_to: Optional[str] = None) -> IntegrityResult:
    """Run the full input-integrity check on an image-based document.

    NOTE (honesty constraint): this POC operates on image files (JPEG/PNG
    scans or photos of documents). It does not parse PDF text layers or run
    OCR — that is listed under 'Next' in the roadmap, not implemented here.
    """
    img = _load_as_rgb(path)
    preview, ela_score, hot_regions = _error_level_analysis(img)
    metadata_score, meta_notes = _metadata_inspection(path, img)

    # Weighted combination — ELA carries more weight because it is the
    # stronger, more localized signal; metadata is corroborating evidence.
    suspicion = 0.7 * ela_score + 0.3 * metadata_score
    integrity_score = float(np.clip(1.0 - suspicion, 0, 1))

    notes = []
    if hot_regions:
        notes.append(f"{len(hot_regions)} region(s) show compression-level inconsistency "
                     f"beyond the document's own noise floor.")
    else:
        notes.append("No localized compression-level anomalies detected.")
    notes.extend(meta_notes)

    preview_path = None
    if save_preview_to:
        preview.save(save_preview_to)
        preview_path = save_preview_to

    return IntegrityResult(
        integrity_score=round(integrity_score, 3),
        ela_score=round(ela_score, 3),
        metadata_score=round(metadata_score, 3),
        flagged_regions=hot_regions[:12],  # cap for UI readability
        notes=notes,
        ela_preview_path=preview_path,
    )
