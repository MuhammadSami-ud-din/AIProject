"""Checkpoint helpers: unique version numbers, metadata, and safe loading.

Checkpoints are ``models/<character>/vNNN.pt`` with a companion ``vNNN.json``.
New checkpoints store ``{"format": 2, "obs_dim", "action_dim", "state_dict"}``.
Older raw state_dicts are still read, but any checkpoint whose input/output
size does not match the current network (e.g. the 30-feature models trained
before the observation was one-hot encoded) is skipped with a log message
instead of crashing or silently loading with ``strict=False``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional, Tuple

import torch

from backend.learning.config import ACTION_DIM, MODELS_DIR, OBS_DIM

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^v(\d{3,})\.(pt|json)$")
CHECKPOINT_FORMAT = 2


def character_dir(character: str, models_dir: Optional[str] = None) -> str:
    return os.path.join(models_dir or MODELS_DIR, character.lower())


def existing_versions(directory: str) -> list[int]:
    if not os.path.isdir(directory):
        return []
    found = set()
    for name in os.listdir(directory):
        m = _VERSION_RE.match(name)
        if m:
            found.add(int(m.group(1)))
    return sorted(found)


def next_version(directory: str) -> int:
    """Next unused version number (never reuses or overwrites an existing one)."""
    versions = existing_versions(directory)
    return (versions[-1] + 1) if versions else 1


def save_checkpoint(model: torch.nn.Module, directory: str, version: Optional[int] = None,
                    meta: Optional[Dict[str, Any]] = None) -> str:
    """Save ``model`` as vNNN.pt (+ .json). Picks the next free version if None."""
    os.makedirs(directory, exist_ok=True)
    if version is None:
        version = next_version(directory)
    pt_path = os.path.join(directory, f"v{version:03d}.pt")
    if os.path.exists(pt_path):
        raise FileExistsError(f"refusing to overwrite existing checkpoint {pt_path}")
    payload = {
        "format": CHECKPOINT_FORMAT,
        "obs_dim": OBS_DIM,
        "action_dim": ACTION_DIM,
        "state_dict": model.state_dict(),
    }
    torch.save(payload, pt_path)
    full_meta = {"version": version, "obs_dim": OBS_DIM, "action_dim": ACTION_DIM,
                 "timestamp": time.time(), **(meta or {})}
    with open(pt_path[:-3] + ".json", "w") as f:
        json.dump(full_meta, f, indent=2)
    return pt_path


def save_named(model: torch.nn.Module, path: str, meta: Optional[Dict[str, Any]] = None) -> str:
    """Save to an explicit path (used for bc_model.pt)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    torch.save({"format": CHECKPOINT_FORMAT, "obs_dim": OBS_DIM, "action_dim": ACTION_DIM,
                "state_dict": model.state_dict()}, path)
    if meta is not None:
        with open(os.path.splitext(path)[0] + ".json", "w") as f:
            json.dump({"obs_dim": OBS_DIM, "action_dim": ACTION_DIM, **meta}, f, indent=2)
    return path


def load_compatible_state_dict(path: str) -> Optional[Dict[str, torch.Tensor]]:
    """Return the state_dict if it fits the current network, else None (logged)."""
    try:
        raw = torch.load(path, map_location="cpu", weights_only=True)
    except Exception:
        logger.warning("could not read checkpoint %s", path, exc_info=True)
        return None
    state = raw.get("state_dict", raw) if isinstance(raw, dict) else None
    if not isinstance(state, dict):
        logger.warning("checkpoint %s has no state_dict", path)
        return None
    first = state.get("shared_net.0.weight")
    actor = state.get("actor.weight")
    if first is None or actor is None:
        logger.warning("checkpoint %s is missing expected layers; skipped", path)
        return None
    if tuple(first.shape)[1] != OBS_DIM or tuple(actor.shape)[0] != ACTION_DIM:
        logger.info("skipping incompatible checkpoint %s (obs_dim=%d, need %d)",
                    path, tuple(first.shape)[1], OBS_DIM)
        return None
    return state


def find_latest_checkpoint(character: str, models_dir: Optional[str] = None,
                           include_bc: bool = True, exclude=()) -> Optional[str]:
    """Newest compatible vNNN.pt for ``character`` (falls back to bc_model.pt).

    ``exclude``: paths to skip (e.g. checkpoints the promotion gate rolled back).
    """
    directory = character_dir(character, models_dir)
    excluded = {os.path.abspath(p) for p in exclude}
    for v in reversed(existing_versions(directory)):
        path = os.path.join(directory, f"v{v:03d}.pt")
        if os.path.abspath(path) in excluded:
            continue
        if os.path.exists(path) and load_compatible_state_dict(path) is not None:
            return path
    if include_bc:
        bc = os.path.join(directory, "bc_model.pt")
        if os.path.exists(bc) and load_compatible_state_dict(bc) is not None:
            return bc
    return None


def checkpoint_signature(character: str, models_dir: Optional[str] = None) -> Tuple:
    """Cheap fingerprint of a character's model folder (names + mtimes) for cache invalidation."""
    directory = character_dir(character, models_dir)
    if not os.path.isdir(directory):
        return ()
    sig = []
    for name in sorted(os.listdir(directory)):
        if name.endswith(".pt"):
            try:
                sig.append((name, os.path.getmtime(os.path.join(directory, name))))
            except OSError:
                continue
    return tuple(sig)
