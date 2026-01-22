# -*- coding: utf-8 -*-
import hashlib
import os
from urllib.parse import urlparse

import requests

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PUBLIC_DIR = os.path.join(ROOT_DIR, "public")

_CT_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def make_key(product_url: str, image_url: str) -> str:
    base = f"{product_url}|{image_url}".encode("utf-8")
    return hashlib.sha1(base).hexdigest()


def detect_ext(content_type: str, url: str) -> str:
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if ct in _CT_EXT:
        return _CT_EXT[ct]
    path = urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


def _rel_from_public(path: str) -> str:
    return os.path.relpath(path, PUBLIC_DIR).replace("\\", "/")


def ensure_cached(product_url: str, image_url: str, dest_dir: str = "public/assets/products") -> str:
    if not image_url:
        return "assets/placeholder.png"

    key = make_key(product_url, image_url)
    abs_dir = os.path.join(ROOT_DIR, dest_dir)
    os.makedirs(abs_dir, exist_ok=True)

    # We don't know the ext until we request, so check common ones.
    for ext in (".jpg", ".png", ".webp"):
        existing = os.path.join(abs_dir, f"{key}{ext}")
        if os.path.exists(existing):
            return _rel_from_public(existing)

    r = requests.get(image_url, stream=True, timeout=20)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}")

    ext = detect_ext(r.headers.get("content-type", ""), image_url)
    dest_path = os.path.join(abs_dir, f"{key}{ext}")
    if os.path.exists(dest_path):
        return _rel_from_public(dest_path)

    tmp_path = dest_path + ".tmp"
    with open(tmp_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 64):
            if chunk:
                f.write(chunk)
    os.replace(tmp_path, dest_path)

    return _rel_from_public(dest_path)
