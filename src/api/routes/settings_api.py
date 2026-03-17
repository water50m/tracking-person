import os
import json
import torch
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

router = APIRouter()

# ─── Cache CUDA info once at startup (torch init is slow) ─────
_CUDA_AVAILABLE: bool = torch.cuda.is_available()
_DEVICE_NAME: str    = torch.cuda.get_device_name(0) if _CUDA_AVAILABLE else "CPU"
_GPU_COUNT: int      = torch.cuda.device_count()    if _CUDA_AVAILABLE else 0


# Paths
DEFAULTS_PATH = Path("config/default_settings.json")
CONFIG_PATH = Path("config/system_settings.json")
MODELS_DIR = Path("models")

# ─── Default loader (read-only) ───────────────────────────────
def load_defaults() -> dict:
    """Read factory defaults from the committed read-only JSON file."""
    if DEFAULTS_PATH.exists():
        try:
            raw = json.loads(DEFAULTS_PATH.read_text())
            # Strip the _comment key — it's documentation only
            return {k: v for k, v in raw.items() if not k.startswith("_")}
        except Exception as e:
            raise RuntimeError(f"Failed to read default_settings.json: {e}")
    raise RuntimeError(f"Default settings file not found at {DEFAULTS_PATH}")


# ─── Active config r/w ────────────────────────────────────────
def load_config() -> dict:
    """Load active config, falling back to defaults for any missing keys."""
    defaults = load_defaults()
    if CONFIG_PATH.exists():
        try:
            overrides = json.loads(CONFIG_PATH.read_text())
            return {**defaults, **overrides}
        except Exception:
            pass
    return defaults.copy()


def save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


# ─── Pydantic schema ──────────────────────────────────────────
class SettingsUpdate(BaseModel):
    detector_model: str | None = None
    classifier_model: str | None = None
    detection_confidence: float | None = None
    iou_threshold: float | None = None
    max_tracks: int | None = None
    frame_skip: int | None = None
    detection_enabled: bool | None = None
    classification_enabled: bool | None = None


# ─── Endpoints ───────────────────────────────────────────────

@router.get("/settings")
async def get_settings():
    """Return current system configuration + hardware info."""
    cfg = load_config()
    defaults = load_defaults()

    cuda_available = _CUDA_AVAILABLE
    device_name    = _DEVICE_NAME
    gpu_count      = _GPU_COUNT

    detector_path = Path(cfg["detector_model"])
    classifier_path = Path(cfg["classifier_model"])

    # Which keys differ from defaults?
    modified_keys = [k for k in defaults if cfg.get(k) != defaults.get(k)]

    return {
        "config": cfg,
        "defaults": defaults,
        "modified_keys": modified_keys,
        "hardware": {
            "device": "cuda" if cuda_available else "cpu",
            "device_name": device_name,
            "gpu_count": gpu_count,
            "cuda_available": cuda_available,
        },
        "models": {
            "detector": {
                "path": str(detector_path),
                "exists": detector_path.exists(),
                "size_mb": round(detector_path.stat().st_size / 1_048_576, 1) if detector_path.exists() else None,
            },
            "classifier": {
                "path": str(classifier_path),
                "exists": classifier_path.exists(),
                "size_mb": round(classifier_path.stat().st_size / 1_048_576, 1) if classifier_path.exists() else None,
            },
        },
    }


@router.post("/settings")
async def update_settings(body: SettingsUpdate):
    """Partial-update system configuration."""
    cfg = load_config()
    update = body.model_dump(exclude_none=True)
    cfg.update(update)
    save_config(cfg)
    defaults = load_defaults()
    modified_keys = [k for k in defaults if cfg.get(k) != defaults.get(k)]
    return {"status": "saved", "config": cfg, "modified_keys": modified_keys}


@router.get("/settings/defaults")
async def get_defaults():
    """Return the factory-default configuration (read-only)."""
    try:
        return {"defaults": load_defaults(), "path": str(DEFAULTS_PATH)}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


class ResetRequest(BaseModel):
    keys: list[str] | None = None  # None or empty = reset ALL


@router.post("/settings/reset")
async def reset_to_defaults(body: ResetRequest = ResetRequest()):
    """Restore settings to factory defaults.
    If body.keys is provided, only those keys are reset.
    Otherwise ALL settings are reset.
    """
    try:
        defaults = load_defaults()
        cfg = load_config()
        keys_to_reset = body.keys if body.keys else list(defaults.keys())
        for k in keys_to_reset:
            if k in defaults:
                cfg[k] = defaults[k]
        save_config(cfg)
        modified_keys = [k for k in defaults if cfg.get(k) != defaults.get(k)]
        return {"status": "reset", "reset_keys": keys_to_reset, "config": cfg, "modified_keys": modified_keys}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings/models")
async def list_models():
    """List all .pt model files in the root and models/ directory."""
    files = []
    search_dirs = [MODELS_DIR, Path(".")]  # models/ first, root as fallback
    for d in search_dirs:
        if d.exists() and d.is_dir():
            # glob only the immediate directory (no recursive) for speed
            for f in d.glob("*.pt"):
                files.append({
                    "name": f.name,
                    "path": str(f.resolve()),
                    "size_mb": round(f.stat().st_size / 1_048_576, 1),
                })
    seen: set[str] = set()
    unique = []
    for f in files:
        if f["path"] not in seen:
            seen.add(f["path"])
            unique.append(f)
    return {"models": unique}


@router.post("/settings/models/upload")
async def upload_model(file: UploadFile = File(...)):
    """Upload a new .pt model file to the models/ directory."""
    if not file.filename or not file.filename.endswith(".pt"):
        raise HTTPException(status_code=400, detail="Only .pt model files are accepted")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = MODELS_DIR / file.filename
    try:
        contents = await file.read()
        dest.write_bytes(contents)
        size_mb = round(dest.stat().st_size / 1_048_576, 1)
        return {"status": "uploaded", "name": file.filename, "path": str(dest), "size_mb": size_mb}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
