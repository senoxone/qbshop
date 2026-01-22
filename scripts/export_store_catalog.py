# -*- coding: utf-8 -*-
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from typing import List

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from syoma import (
        DEFAULT_ALLOWED_STATUSES,
        MARKUP_PATH,
        MarkupConfig,
        fetch_html,
        init_db,
        load_all_items,
        make_session,
        normalize_text,
        refresh,
        _extract_image_from_product_page,
        _is_product_image_url,
    )
except ModuleNotFoundError:
    import importlib.util

    spec = importlib.util.spec_from_file_location("syoma", os.path.join(ROOT_DIR, "syoma.py"))
    if not spec or not spec.loader:
        raise
    _syoma = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_syoma)
    DEFAULT_ALLOWED_STATUSES = _syoma.DEFAULT_ALLOWED_STATUSES
    MARKUP_PATH = _syoma.MARKUP_PATH
    MarkupConfig = _syoma.MarkupConfig
    fetch_html = _syoma.fetch_html
    init_db = _syoma.init_db
    load_all_items = _syoma.load_all_items
    make_session = _syoma.make_session
    normalize_text = _syoma.normalize_text
    refresh = _syoma.refresh
    _extract_image_from_product_page = _syoma._extract_image_from_product_page
    _is_product_image_url = getattr(_syoma, "_is_product_image_url", None)

from scripts.image_cache import ensure_cached, make_key


DB_PATH = "prices.db"
OUT_PATH = os.path.join("public", "products.json")
PLACEHOLDER = "assets/placeholder.png"


def _stable_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _update_image_fields(title: str, image_url: str, image_local: str, image_key: str) -> None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "UPDATE prices SET image_url=?, image_local=?, image_key=? WHERE title=?",
        (image_url, image_local, image_key, title),
    )
    con.commit()
    con.close()


def _fetch_image_url(item, session) -> str:
    if item.image_url:
        if _is_product_image_url and _is_product_image_url(item.image_url):
            return item.image_url
        if not _is_product_image_url and "/wa-data/public/shop/products/" in item.image_url.lower():
            return item.image_url
    try:
        code, html = fetch_html(session, item.url, timeout=20, retries=2)
        if code < 400:
            img = _extract_image_from_product_page(html) or ""
            if _is_product_image_url and not _is_product_image_url(img):
                return ""
            if not _is_product_image_url and img and "/wa-data/public/shop/products/" not in img.lower():
                return ""
            return img
    except Exception:
        pass
    return ""


def _filter_items(items) -> List:
    out = []
    for it in items:
        if it.stock_status not in DEFAULT_ALLOWED_STATUSES:
            continue
        out.append(it)
    return out


def _sim_rank(sim: str) -> int:
    s = (sim or "").lower()
    if "dual" in s:
        return 0
    if "sim+esim" in s or "sim + esim" in s:
        return 1
    if "esim" in s:
        return 2
    return 3


def _color_key(it) -> str:
    color = it.color_en or it.color_ru or ""
    return normalize_text(color)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-refresh", action="store_true", help="use cached DB only")
    args = parser.parse_args()

    init_db()
    markup_cfg = MarkupConfig(MARKUP_PATH)
    markup_cfg.load()

    refresh_ok = True
    if not args.no_refresh:
        try:
            refresh(base_markup_rub=markup_cfg.default, markup_cfg=markup_cfg, debug=False)
        except Exception as e:
            refresh_ok = False
            print(f"[WARN] refresh failed: {e}")

    items = _filter_items(load_all_items())
    existing_items = []
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH, "r", encoding="utf-8") as f:
                existing_items = json.load(f).get("items", [])
        except Exception:
            existing_items = []

    if not items:
        if existing_items:
            print("[WARN] No items from DB, keeping existing products.json")
            return 0
        if not refresh_ok:
            raise RuntimeError("No cached items and refresh failed.")
        raise RuntimeError("No items to export.")
    items.sort(
        key=lambda it: (
            normalize_text(it.model or ""),
            int(it.memory_gb or 0),
            int(it.price_my or it.price_site or 0),
            it.title,
        )
    )

    session = make_session()
    image_candidates = []
    for it in items:
        image_url = _fetch_image_url(it, session)
        image_candidates.append((it, image_url))

    # Prefer the best SIM variant image per model+color to avoid mismatched photos.
    best_image_by_key = {}
    for it, image_url in image_candidates:
        if not image_url:
            continue
        key = (it.model or "", _color_key(it))
        cur = best_image_by_key.get(key)
        if not cur:
            best_image_by_key[key] = (image_url, _sim_rank(it.sim_desc), int(it.price_site or 0))
            continue
        _url, cur_rank, cur_price = cur
        rank = _sim_rank(it.sim_desc)
        price = int(it.price_site or 0)
        if rank < cur_rank or (rank == cur_rank and price > cur_price):
            best_image_by_key[key] = (image_url, rank, price)

    exported = []
    for it, image_url in image_candidates:
        key = (it.model or "", _color_key(it))
        preferred = best_image_by_key.get(key, (image_url, None, None))[0]
        use_url = preferred or image_url
        image_key = make_key(it.url, use_url) if use_url else ""
        try:
            image_local = ensure_cached(it.url, use_url)
        except Exception:
            image_local = PLACEHOLDER

        if not image_local:
            image_local = PLACEHOLDER
        _update_image_fields(it.title, use_url or "", image_local, image_key)

        markup = int(it.price_my or 0) - int(it.price_site or 0)
        exported.append(
            {
                "id": _stable_id(it.url),
                "title": it.title,
                "price": int(it.price_my or 0),
                "price_site": int(it.price_site or 0),
                "markup": int(markup),
                "image": image_local,
                "url": it.url,
                "meta": {
                    "model": it.model,
                    "memory_gb": it.memory_gb,
                    "color_ru": it.color_ru,
                    "color_en": it.color_en,
                    "sim": it.sim_desc,
                    "status": it.stock_status,
                },
                "updated_ts": int(it.ts or 0),
            }
        )

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"generated_ts": int(time.time()), "items": exported}, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Exported {len(exported)} items to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
