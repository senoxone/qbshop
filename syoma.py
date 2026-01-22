# -*- coding: utf-8 -*-
"""
SyomaStore iPhone price helper (CLI + daemon + JSON)
- Парсит syomastore.ru (модель/память/цвет/SIM/статус/цена)
- Накрутка по правилам (regex)
- История изменений цен/статусов (price_history)
- Команда :delta
- Умный поиск с синонимами/опечатками + "порог"
- ТОП (минимум) для точного запроса (модель+память)
- Демон-режим --daemon (автообновление)
- Алерты :watch
- JSON режим --json (под Telegram-бота)
"""

import os
import re
import sys
import time
import json
import sqlite3
import traceback
import argparse
from dataclasses import dataclass
from typing import List, Optional, Tuple, Set, Dict, Any
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://syomastore.ru"
CATALOG_URL = "https://syomastore.ru/category/smartfony-apple/"

DB_PATH = "prices.db"
LOG_PATH = "syoma.log"
MARKUP_PATH = "markup_rules.json"

LOCK_PATH = "syoma_refresh.lock"
LOCK_TTL_SECONDS = 45 * 60

STATUS_WORDS = ["В наличии", "Есть на складе", "Под заказ", "Нет в наличии"]
DEFAULT_ALLOWED_STATUSES = {"В наличии", "Есть на складе", "Под заказ"}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

PAGE_DELAY = 0.6
SIM_RESOLVE_DELAY = 0.45

_ENABLE_ANSI = True

SIM_ORDER = {"DualSim": 0, "SIM+eSIM": 1, "eSIM": 2, "unknown": 9}

_PRICE_RE = re.compile(r"(\d[\d\s]*)\s*₽")
_COLOR_EN_RE = re.compile(r"\(([^)]+)\)")
_MODEL_FROM_TITLE_RE = re.compile(r"\b(iPhone\s+.+?)\s+(\d{2,4})\s*(?:GB|ГБ)\b", re.IGNORECASE)
_MEMORY_RE = re.compile(r"\b(\d{2,4})\s*(?:GB|ГБ)\b", re.IGNORECASE)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _enable_windows_ansi():
    if os.name != "nt":
        return
    try:
        import ctypes  # type: ignore
        kernel32 = ctypes.windll.kernel32
        h = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(h, ctypes.byref(mode)):
            kernel32.SetConsoleMode(h, mode.value | 0x0004)
    except Exception:
        pass


_enable_windows_ansi()

_ANSI = {
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "blue": "\x1b[34m",
    "magenta": "\x1b[35m",
    "cyan": "\x1b[36m",
    "gray": "\x1b[90m",
}
_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"


def _ansi(text: str, color: Optional[str] = None, bold: bool = False) -> str:
    if not _ENABLE_ANSI:
        return text
    try:
        if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
            return text
    except Exception:
        return text

    prefix = ""
    if bold:
        prefix += _BOLD
    if color and color in _ANSI:
        prefix += _ANSI[color]
    if not prefix:
        return text
    return f"{prefix}{text}{_RESET}"


def _read_lock_info() -> Tuple[int, int]:
    try:
        with open(LOCK_PATH, "r", encoding="utf-8") as f:
            s = f.read().strip()
        pid_s, ts_s = s.split(":", 1)
        return int(pid_s), int(ts_s)
    except Exception:
        return 0, 0


def acquire_lock() -> None:
    now = int(time.time())

    if os.path.exists(LOCK_PATH):
        pid, ts = _read_lock_info()
        age = now - ts if ts else None
        if (age is None) or (age > LOCK_TTL_SECONDS):
            try:
                os.remove(LOCK_PATH)
                log(f"[WARN] Удалил устаревший lock: {LOCK_PATH} (age={age})")
            except Exception:
                pass

    try:
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, f"{os.getpid()}:{now}".encode("utf-8"))
        finally:
            os.close(fd)
    except FileExistsError:
        pid, ts = _read_lock_info()
        age = now - ts if ts else "?"
        raise RuntimeError(f"Refresh уже запущен (pid={pid}, age={age}s). Удали {LOCK_PATH} если завис.")


def release_lock() -> None:
    try:
        if os.path.exists(LOCK_PATH):
            os.remove(LOCK_PATH)
    except Exception:
        pass


@dataclass
class Item:
    title: str
    url: str
    model: str
    memory_gb: Optional[int]
    color_ru: str
    color_en: str
    sim_desc: str
    sim_count: Optional[int]
    stock_status: str
    price_site: int
    price_my: int
    cashback: Optional[str]
    image_url: str
    image_local: str
    image_key: str
    ts: int


class MarkupConfig:
    """
    Конфиг накруток.

    Новый формат (удобный для GUI):
      {
        "default": 5000,
        "models": { "iPhone 14": 5000, "iPhone 16 Pro Max": 9000, ... }
      }

    Старый формат (regex) поддерживается для совместимости:
      { "default": 5000, "rules": [ {"pattern": "^iPhone\\s+16\\b", "markup": 7000}, ... ] }
    """

    def __init__(self, path: str):
        self.path = path
        self.default: int = 5000
        self.models: Dict[str, int] = {}
        self.rules: List[Dict[str, Any]] = []
        self._compiled: List[Tuple[re.Pattern, int, str]] = []

    def _write_default(self) -> None:
        data = {
            "default": 5000,
            "models": {
                "iPhone 12 mini": 4000,
                "iPhone 14": 5000,
                "iPhone 16": 7000,
                "iPhone 16 Pro Max": 9000,
            },
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self) -> None:
        if not os.path.exists(self.path):
            self._write_default()

        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.default = int(data.get("default", 5000))

        # новый формат
        raw_models = data.get("models", {})
        if isinstance(raw_models, dict):
            self.models = {str(k).strip(): int(v) for k, v in raw_models.items() if str(k).strip()}
        else:
            self.models = {}

        # старый формат regex (на случай если у тебя уже был файл)
        self.rules = data.get("rules", []) if isinstance(data.get("rules", []), list) else []
        self._compile()

    def save(self) -> None:
        data: Dict[str, Any] = {
            "default": int(self.default),
            "models": {k: int(v) for k, v in self.models.items()},
        }
        # не ломаем старые проекты: если rules есть — сохраняем
        if self.rules:
            data["rules"] = self.rules

        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self._compile()

    def _compile(self) -> None:
        self._compiled = []
        for r in self.rules:
            pat = str(r.get("pattern", "")).strip()
            if not pat:
                continue
            mk = int(r.get("markup", self.default))
            try:
                rx = re.compile(pat, re.IGNORECASE)
                self._compiled.append((rx, mk, pat))
            except re.error:
                pass

    @staticmethod
    def _norm_model(m: str) -> str:
        return normalize_text(m).strip()

    # --- чтение накрутки ---
    def get_markup(self, model: str) -> int:
        model = (model or "").strip()
        if not model:
            return int(self.default)

        # 1) точное совпадение по модели (удобный режим)
        nm = self._norm_model(model)
        for k, v in self.models.items():
            if self._norm_model(k) == nm:
                return int(v)

        # 2) fallback: regex rules (если кто-то всё ещё их использует)
        for rx, mk, _pat in self._compiled:
            if rx.search(model):
                return int(mk)

        return int(self.default)

    # совместимость со старым кодом
    def get(self, model: str) -> int:
        return self.get_markup(model)

    # --- управление default ---
    def set_default(self, markup: int) -> None:
        self.default = int(markup)
        self.save()

    # --- управление МОДЕЛЯМИ (для GUI) ---
    def set_model_markup(self, model: str, markup: int) -> None:
        model = (model or "").strip()
        if not model:
            return
        self.models[model] = int(markup)
        self.save()

    def del_model(self, model: str) -> None:
        model = (model or "").strip()
        if model in self.models:
            self.models.pop(model, None)
            self.save()

    def list_models_ordered(self, extra_models: Optional[List[str]] = None) -> List[Tuple[str, int]]:
        extra_models = extra_models or []
        pool = []
        # из каталога + из базы
        for m in get_model_catalog() + list(extra_models):
            m = (m or "").strip()
            if not m:
                continue
            pool.append(m)

        # дополним теми, что уже заданы в models, но не в каталоге
        for m in self.models.keys():
            if m and m not in pool:
                pool.append(m)

        # uniq by normalized
        seen = set()
        uniq = []
        for m in pool:
            nm = self._norm_model(m)
            if nm in seen:
                continue
            seen.add(nm)
            uniq.append(m)

        uniq.sort(key=lambda x: self._norm_model(x))
        return [(m, self.get_markup(m)) for m in uniq]

    # --- старый regex API (оставляем, но GUI им больше не пользуется) ---
    def set_rule(self, pattern: str, mk: int) -> None:
        pattern = pattern.strip()
        for r in self.rules:
            if str(r.get("pattern", "")).strip() == pattern:
                r["markup"] = int(mk)
                self.save()
                return
        self.rules.insert(0, {"pattern": pattern, "markup": int(mk)})
        self.save()

    def del_rule(self, pattern: str) -> None:
        pattern = pattern.strip()
        self.rules = [r for r in self.rules if str(r.get("pattern", "")).strip() != pattern]
        self.save()

    def show(self) -> str:
        lines = [f"DEFAULT = {self.default} ₽", "MODELS:"]
        if not self.models:
            lines.append("  (пусто)")
        else:
            for m, v in sorted(self.models.items(), key=lambda kv: self._norm_model(kv[0])):
                lines.append(f"  {m}: {v} ₽")
        if self.rules:
            lines.append("")
            lines.append("RULES (legacy regex):")
            for _rx, mk, pat in self._compiled:
                lines.append(f"  {mk} ₽ <= /{pat}/i")
        return "\n".join(lines)


def init_db(db_path: str = DB_PATH) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS prices (
          title TEXT PRIMARY KEY,
          url TEXT,
          model TEXT,
          memory_gb INTEGER,
          color_ru TEXT,
          color_en TEXT,
          sim_desc TEXT,
          sim_count INTEGER,
          stock_status TEXT,
          price_site INTEGER NOT NULL,
          price_my INTEGER NOT NULL DEFAULT 0,
          cashback TEXT,
          image_url TEXT,
          image_local TEXT,
          image_key TEXT,
          ts INTEGER NOT NULL
        );
        """
    )

    # Совместимость: добавляем cashback, если колонка отсутствует
    try:
        cur.execute("ALTER TABLE prices ADD COLUMN cashback TEXT;")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE prices ADD COLUMN image_url TEXT;")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE prices ADD COLUMN image_local TEXT;")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE prices ADD COLUMN image_key TEXT;")
    except sqlite3.OperationalError:
        pass

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          title TEXT NOT NULL,
          ts INTEGER NOT NULL,
          price_site INTEGER NOT NULL,
          stock_status TEXT
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_hist_title_ts ON price_history(title, ts);")

    # Совместимость: добавляем model в историю (если старая БД)
    try:
        cur.execute("ALTER TABLE price_history ADD COLUMN model TEXT;")
    except sqlite3.OperationalError:
        pass
    cur.execute("CREATE INDEX IF NOT EXISTS idx_hist_model_ts ON price_history(model, ts);")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS watches (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          query TEXT NOT NULL,
          mode TEXT NOT NULL,
          threshold INTEGER,
          drop_amount INTEGER,
          last_best_my INTEGER,
          last_trigger_ts INTEGER,
          is_enabled INTEGER NOT NULL DEFAULT 1,
          created_ts INTEGER NOT NULL
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_outbox (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts INTEGER NOT NULL,
          watch_id INTEGER,
          message TEXT NOT NULL,
          payload_json TEXT
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_outbox_ts ON alert_outbox(ts);")

    con.commit()
    con.close()


def now_ts() -> int:
    return int(time.time())


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.7,en;q=0.6",
            "Connection": "keep-alive",
            "Referer": "https://www.google.com/",
        }
    )
    return s


def fetch_html(session: requests.Session, url: str, timeout: int = 30, retries: int = 4) -> Tuple[int, str]:
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=timeout, allow_redirects=True)
            return r.status_code, r.text
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
            wait = min(2.5 * attempt, 10.0)
            log(f"[WARN] timeout/conn attempt {attempt}/{retries} wait={wait}s url={url}")
            time.sleep(wait)
    raise last_exc  # type: ignore


def load_all_items(db_path: str = DB_PATH) -> List[Item]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM prices").fetchall()
    con.close()
    return [Item(**dict(r)) for r in rows]


def load_prev_map(db_path: str = DB_PATH) -> Dict[str, Tuple[int, str]]:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    rows = cur.execute("SELECT title, price_site, stock_status FROM prices").fetchall()
    con.close()
    return {t: (int(p), str(s)) for (t, p, s) in rows}


def load_prev_image_map(db_path: str = DB_PATH) -> Dict[str, Tuple[str, str, str]]:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    rows = cur.execute("SELECT title, image_url, image_local, image_key FROM prices").fetchall()
    con.close()
    out: Dict[str, Tuple[str, str, str]] = {}
    for title, image_url, image_local, image_key in rows:
        out[str(title)] = (
            str(image_url or ""),
            str(image_local or ""),
            str(image_key or ""),
        )
    return out


def upsert_items(items: List[Item], db_path: str = DB_PATH) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executemany(
        """
        INSERT INTO prices(
            title,url,model,memory_gb,color_ru,color_en,sim_desc,sim_count,stock_status,
            price_site,price_my,cashback,image_url,image_local,image_key,ts
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(title) DO UPDATE SET
            url=excluded.url,
            model=excluded.model,
            memory_gb=excluded.memory_gb,
            color_ru=excluded.color_ru,
            color_en=excluded.color_en,
            sim_desc=excluded.sim_desc,
            sim_count=excluded.sim_count,
            stock_status=excluded.stock_status,
            price_site=excluded.price_site,
            price_my=excluded.price_my,
            cashback=excluded.cashback,
            image_url=excluded.image_url,
            image_local=excluded.image_local,
            image_key=excluded.image_key,
            ts=excluded.ts
        ;
        """,
        [
            (
                x.title, x.url, x.model, x.memory_gb, x.color_ru, x.color_en,
                x.sim_desc, x.sim_count, x.stock_status,
                x.price_site, x.price_my, x.cashback, x.image_url, x.image_local, x.image_key, x.ts
            )
            for x in items
        ],
    )
    con.commit()
    con.close()


def add_history_rows(changed: List[Tuple[str, int, str, int]], db_path: str = DB_PATH) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executemany(
        "INSERT INTO price_history(title, ts, price_site, stock_status) VALUES(?,?,?,?)",
        [(t, ts, p, st) for (t, p, st, ts) in changed],
    )
    con.commit()
    con.close()



def cleanup_price_history(keep_days: int = 30, db_path: str = DB_PATH) -> None:
    """Удаляем историю старше keep_days дней (по умолчанию 30)."""
    try:
        cutoff = now_ts() - int(keep_days) * 24 * 3600
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("DELETE FROM price_history WHERE ts < ?", (cutoff,))
        con.commit()
        con.close()
    except Exception:
        # не мешаем основному refresh
        pass


def normalize_text(s: str) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"\b(айфон|aifon|ifone|iphon|iph)\b", "iphone", s)
    s = s.replace("про макс", "pro max").replace("про-макс", "pro max").replace("промакс", "pro max")
    s = re.sub(r"\bпро\b", "pro", s)
    s = re.sub(r"\bмакс\b", "max", s)
    s = re.sub(r"\bплюс\b", "plus", s)
    s = re.sub(r"\bмини\b", "mini", s)

    s = s.replace("dual ", "dualsim ").replace(" dual", " dualsim")
    s = s.replace("sim+esim", "sim + esim")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokenize(q: str) -> List[str]:
    q = normalize_text(q)
    return [t for t in re.split(r"[\s,;/]+", q) if t]


def parse_model_memory(title: str) -> Tuple[str, Optional[int]]:
    m = _MODEL_FROM_TITLE_RE.search(title)
    if not m:
        mem = None
        m2 = _MEMORY_RE.search(title)
        if m2:
            try:
                mem = int(m2.group(1))
            except Exception:
                mem = None
        return "iPhone (unknown)", mem

    model = m.group(1).strip()
    model = re.sub(r"\b(\d{1,2})\s+e\b", r"\1e", model, flags=re.IGNORECASE)
    try:
        mem = int(m.group(2))
    except ValueError:
        mem = None
    return model, mem


def parse_color_ru(title: str) -> str:
    parts = _MEMORY_RE.split(title, maxsplit=1)
    if len(parts) < 3:
        return "—"
    tail = parts[2].strip()
    tail = _COLOR_EN_RE.sub("", tail).strip()
    tail = re.sub(r"\s+", " ", tail).strip(" -–—")
    return tail or "—"


def parse_color_en(title: str) -> str:
    m = _COLOR_EN_RE.search(title)
    return (m.group(1).strip() if m else "—")


def parse_stock_status(text: str) -> str:
    for w in STATUS_WORDS:
        if w in text:
            return w
    return "unknown"


def parse_sim_from_title(title: str, url: str) -> Tuple[str, Optional[int]]:
    t = normalize_text(title)
    u = normalize_text(url)

    if "sim + esim" in t or "sim+esim" in u or "sim-esim" in u:
        return "SIM+eSIM", None
    if "dualsim" in t or "dual sim" in t or "dual-sim" in u or "2-sim" in u or "-2-sim" in u:
        return "DualSim", 2
    if "esim" in t or "-esim" in u:
        return "eSIM", None
    return "unknown", None


def parse_sim_from_product_page(html: str) -> Tuple[str, Optional[int]]:
    """Пытаемся максимально надёжно вытащить тип SIM из страницы товара.

    1) Сначала парсим структуру характеристик:
       - "Количество и тип физических SIM карт"
       - "Поддержка eSIM"
    2) Если по ним ничего не нашли — используем старые текстовые эвристики.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Полный текст с переводами строк — чтобы искать отдельные строки характеристик
    raw_text = soup.get_text("\n", strip=True)
    lines = [normalize_text(line) for line in raw_text.splitlines() if line.strip()]

    phys_line = None
    esim_line = None

    for ln in lines:
        # Линия про количество физических SIM
        # Примеры: "количество и тип физических sim карт 1 шт - nanosim"
        if "количество и тип физических sim" in ln:
            phys_line = ln
        # Линия про поддержку eSIM
        if "поддержка esim" in ln or "поддержка e-sim" in ln:
            esim_line = ln

    phys_count: Optional[int] = None
    has_esim: Optional[bool] = None

    # Пытаемся вытащить количество физических SIM
    if phys_line:
        m = re.search(r"\b([0-9])\s*шт", phys_line)
        if not m:
            m = re.search(r"\b([0-9])\b", phys_line)
        if m:
            try:
                phys_count = int(m.group(1))
            except Exception:
                phys_count = None

    # Пытаемся понять, есть ли поддержка eSIM
    if esim_line:
        # типичные формулировки: "да", "есть", "поддерживает" / "нет"
        if any(w in esim_line for w in [" да", " есть", "поддерживает"]):
            has_esim = True
        if any(w in esim_line for w in [" нет", "не поддерживает"]):
            has_esim = False

    # Если удалось распарсить структурные данные — строим ответ
    if phys_count is not None or has_esim is not None:
        # Две физические SIM — однозначно DualSim
        if phys_count is not None and phys_count >= 2:
            return "DualSim", phys_count
        # Одна физическая SIM + eSIM
        if phys_count == 1 and has_esim:
            return "SIM+eSIM", None
        # Только eSIM (0 физ. SIM или не указано, но явно есть eSIM)
        if (phys_count is None or phys_count == 0) and has_esim:
            return "eSIM", None
        # Одна физическая SIM без eSIM — в рамках текущей модели считаем как "обычная SIM"
        # Чтобы не ломать старую логику, пока возвращаем unknown.
        # Если захочешь явно видеть это как "SIM", можно поменять на return "SIM", 1
        if phys_count == 1 and has_esim is False:
            return "unknown", None

    # Fallback: старые текстовые эвристики по всей странице
    tx = normalize_text(soup.get_text(" ", strip=True))

    # SIM+eSIM в любом виде (с +, без пробелов и т.п.)
    if "sim + esim" in tx or "sim+esim" in tx or "sim + e-sim" in tx or "sim+e-sim" in tx:
        return "SIM+eSIM", None

    # Любые упоминания dual-sim / 2 sim
    if "dual sim" in tx or "dualsim" in tx or "2 sim" in tx or "2-sim" in tx or "2sim" in tx:
        return "DualSim", 2

    # Любые варианты eSIM / e-sim / e sim
    if "esim" in tx or "e-sim" in tx or "e sim" in tx:
        return "eSIM", None

    return "unknown", None


def update_item_sim_in_db(title: str, sim_desc: str, sim_count: Optional[int], db_path: str = DB_PATH) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("UPDATE prices SET sim_desc=?, sim_count=? WHERE title=?", (sim_desc, sim_count, title))
    con.commit()
    con.close()


def resolve_unknown_sims_for_results(items: List[Item], session: requests.Session) -> None:
    """Дозаполняет SIM для результатов поиска, у которых sim_desc == 'unknown'.

    Работает аккуратно: между запросами стоит пауза SIM_RESOLVE_DELAY,
    ошибки не считаются критичными, но логируются в syoma.log.
    """
    for it in items:
        if it.sim_desc != "unknown":
            continue
        time.sleep(SIM_RESOLVE_DELAY)
        try:
            code, html = fetch_html(session, it.url, timeout=25, retries=2)
            if code < 400:
                sim_desc, sim_count = parse_sim_from_product_page(html)
                log(f"SIM_RESOLVE code={code} title='{it.title}' url='{it.url}' -> {sim_desc} ({sim_count})")
                if sim_desc != "unknown":
                    it.sim_desc = sim_desc
                    it.sim_count = sim_count
                    update_item_sim_in_db(it.title, sim_desc, sim_count)
                else:
                    # Чтобы легче было искать проблемные карточки
                    log(f"SIM_RESOLVE UNKNOWN_AFTER_PARSE title='{it.title}' url='{it.url}'")
            else:
                log(f"SIM_RESOLVE HTTP_{code} title='{it.title}' url='{it.url}'")
        except Exception as e:
            log(f"SIM_RESOLVE ERROR title='{it.title}' url='{it.url}' err={e}")
            continue


def _abs_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    return urljoin(BASE_URL, url)


def _extract_image_from_block(block) -> str:
    for img in block.find_all("img"):
        for attr in ("data-src", "data-original", "data-lazy-src", "src"):
            val = img.get(attr)
            if not val:
                continue
            if "logo" in val.lower():
                continue
            return _abs_url(val)
    return ""


def _extract_image_from_product_page(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for sel in [
        "meta[property='og:image']",
        "meta[name='twitter:image']",
        "meta[property='og:image:url']",
    ]:
        tag = soup.select_one(sel)
        if tag and tag.get("content"):
            return _abs_url(tag["content"])
    return ""


def parse_catalog_page(html: str) -> List[Tuple[str, str, int, str, Optional[str], str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Tuple[str, str, int, str, Optional[str], str]] = []

    for a in soup.find_all("a", href=True):
        title = a.get_text(" ", strip=True)
        if not title.startswith("Смартфон Apple iPhone"):
            continue

        url = urljoin(BASE_URL, a["href"])

        block = a
        block_text = ""
        for _ in range(14):
            block_text = block.get_text("\n", strip=True)
            if _PRICE_RE.search(block_text):
                break
            if not block.parent:
                break
            block = block.parent

        m = _PRICE_RE.search(block_text)
        if not m:
            continue

        price = int(m.group(1).replace(" ", ""))
        status = parse_stock_status(block_text)
        image_url = _extract_image_from_block(block)

        # Пытаемся вытащить строку про кешбэк прямо из блока карточки.
        # На сайте обычно что-то типа:
        # "Кешбек +698", иногда "+ 698" отдельным элементом.
        cashback: Optional[str] = None
        tx_block = normalize_text(block_text)
        m_cb = re.search(r"(кешбек|кэшбек|кэшбэк|cashback)\s*\+?\s*([0-9]+)", tx_block)
        if m_cb:
            # Нормализуем вид как на сайте: "Кешбек + 698"
            cashback = f"Кешбек + {m_cb.group(2)}"

        out.append((title, url, price, status, cashback, image_url))
    return out



def detect_pages(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    pages = set()
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        m1 = re.search(r"[?&]page=(\d+)", href)
        m2 = re.search(r"/page/(\d+)/", href)
        if m1:
            pages.add(int(m1.group(1)))
        if m2:
            pages.add(int(m2.group(1)))
    return max(pages) if pages else 1


def refresh(base_markup_rub: int, markup_cfg: Optional[MarkupConfig] = None, debug: bool = False) -> int:
    acquire_lock()
    try:
        sess = make_session()
        code, first = fetch_html(sess, CATALOG_URL, timeout=40, retries=3)
        if code >= 400:
            raise RuntimeError(f"Syoma недоступен. HTTP={code}")

        pages = detect_pages(first)
        raw = parse_catalog_page(first)
        if debug:
            log(f"[debug] page1 len={len(first)} pages={pages}")

        for p in range(2, pages + 1):
            time.sleep(PAGE_DELAY)
            try:
                code, html = fetch_html(sess, f"{CATALOG_URL}?page={p}", timeout=35, retries=3)
                if code >= 400:
                    code, html = fetch_html(sess, urljoin(CATALOG_URL, f"page/{p}/"), timeout=35, retries=3)
                raw.extend(parse_catalog_page(html))
            except Exception as e:
                log(f"[WARN] page {p} skipped: {e}")
                continue

        if not raw:
            log("[WARN] Syoma parsed 0 items. Keeping previous cache.")
            return 0

        uniq: Dict[str, Tuple[str, str, int, str, Optional[str], str]] = {}
        for title, url, price, status, cashback, image_url in raw:
            uniq[title] = (title, url, price, status, cashback, image_url)

        if debug:
            log(f"[debug] parsed_raw={len(raw)} unique_titles={len(uniq)}")

        ts = now_ts()
        prev = load_prev_map(DB_PATH)
        prev_images = load_prev_image_map(DB_PATH)

        items: List[Item] = []
        changed_hist: List[Tuple[str, int, str, int]] = []

        for title, url, price_site, status, cashback, image_url in uniq.values():
            model, mem = parse_model_memory(title)
            color_ru = parse_color_ru(title)
            color_en = parse_color_en(title)
            sim_desc, sim_count = parse_sim_from_title(title, url)

            image_local = ""
            image_key = ""
            prev_img = prev_images.get(title)
            if prev_img:
                prev_url, prev_local, prev_key = prev_img
                if not image_url and prev_url:
                    image_url = prev_url
                if image_url and prev_url and image_url == prev_url:
                    image_local = prev_local or ""
                    image_key = prev_key or ""

            if not image_url:
                try:
                    code, html = fetch_html(sess, url, timeout=20, retries=2)
                    if code < 400:
                        image_url = _extract_image_from_product_page(html)
                except Exception:
                    pass

            mk = markup_cfg.get(model) if markup_cfg else base_markup_rub
            price_my = int(price_site) + int(mk)

            items.append(
                Item(
                    title=title,
                    url=url,
                    model=model,
                    memory_gb=mem,
                    color_ru=color_ru,
                    color_en=color_en,
                    sim_desc=sim_desc,
                    sim_count=sim_count,
                    stock_status=status,
                    price_site=int(price_site),
                    price_my=int(price_my),
                    cashback=cashback,
                    image_url=image_url or "",
                    image_local=image_local,
                    image_key=image_key,
                    ts=ts,
                )
            )

            # Логируем историю для ГРАФИКА: каждая позиция на каждом refresh
            changed_hist.append((title, int(price_site), status, ts))

        if changed_hist:
            add_history_rows(changed_hist)
        cleanup_price_history(keep_days=30)

        upsert_items(items)

        try:
            run_watches(items_cache=items, markup_cfg=markup_cfg)
        except Exception as e:
            log(f"[WARN] watches check failed: {e}")

        return len(items)
    finally:
        release_lock()


def extract_model_phrase(query: str) -> Optional[str]:
    tokens = _tokenize(query)
    if not tokens:
        return None

    if tokens and re.fullmatch(r"\d{1,2}e?", tokens[0]) and len(tokens) >= 2 and tokens[1] in {"pro", "max", "plus", "mini"}:
        tokens = ["iphone"] + tokens

    if tokens[0] != "iphone" or len(tokens) < 2:
        return None

    if re.fullmatch(r"\d{1,2}e?", tokens[1]):
        phrase = ["iphone", tokens[1]]
        rest = tokens[2:]
        if "pro" in rest:
            phrase.append("pro")
        if "max" in rest:
            phrase.append("max")
        if "plus" in rest:
            phrase.append("plus")
        if "mini" in rest:
            phrase.append("mini")
        return " ".join(phrase).strip()

    if tokens[1] == "se":
        phrase = ["iphone", "se"]
        if len(tokens) >= 3 and re.fullmatch(r"\d{4}", tokens[2]):
            phrase.append(tokens[2])
        return " ".join(phrase)

    return None


def extract_memory_from_query(query: str) -> Optional[int]:
    for t in _tokenize(query):
        if t in {"64", "128", "256", "512", "1024"}:
            return int(t)
        if t in {"1tb", "1тб"}:
            return 1024
    return None


def classify_query(query: str) -> str:
    tokens = _tokenize(query)
    if not tokens:
        return "general"
    mp = extract_model_phrase(query)
    mem = extract_memory_from_query(query)
    if mp and mem is not None:
        return "precise"
    if mp and mem is None:
        return "model"
    if "iphone" in tokens:
        return "general"
    return "general"


def sort_key(it: Item) -> Tuple:
    return (normalize_text(it.model), it.memory_gb or 0, normalize_text(it.color_ru), SIM_ORDER.get(it.sim_desc, 9), it.price_my)


def search_prices(query: str, items: List[Item], allowed_statuses: Optional[Set[str]] = DEFAULT_ALLOWED_STATUSES) -> List[Item]:
    tokens = _tokenize(query)
    if not tokens:
        return []

    model_phrase = extract_model_phrase(query)
    mem_q = extract_memory_from_query(query)
    mp_tokens = set(model_phrase.split()) if model_phrase else set()

    scored: List[Tuple[int, Item]] = []
    for it in items:
        if allowed_statuses is not None and it.stock_status not in allowed_statuses:
            continue

        title_l = normalize_text(it.title)
        model_l = normalize_text(it.model)

        if model_phrase:
            if not model_l.startswith(model_phrase):
                continue
            if mem_q is not None and (it.memory_gb != mem_q):
                continue

            extra = [t for t in tokens if t not in mp_tokens and t not in {str(mem_q) if mem_q else ""}]
            score = 1000
            for t in extra:
                if t and t in title_l:
                    score += 20
            scored.append((score, it))
            continue

        if classify_query(query) == "general":
            continue

        score = 0
        for t in tokens:
            if len(t) < 3:
                continue
            if t in title_l:
                score += 10
        if score > 0:
            scored.append((score, it))

    scored.sort(key=lambda x: (-x[0], sort_key(x[1])))
    return [x[1] for x in scored]


def group_key(it: Item) -> Tuple[str, int, str]:
    return (it.model, int(it.memory_gb or 0), it.color_ru)


def format_item(it: Item, markup_cfg: MarkupConfig) -> str:
    mk = markup_cfg.get(it.model)
    my_price = it.price_site + mk
    return (
        f"{it.model} / {it.memory_gb or '??'}GB / {it.color_ru}\n"
        f"SIM: {it.sim_desc}\n"
        f"Статус: {it.stock_status}\n"
        f"Цена (сайт): {it.price_site} ₽ | Накрутка: {mk} ₽ | Цена (твоя): {my_price} ₽\n"
        f"Обновлено: {datetime.fromtimestamp(it.ts).strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Ссылка: {it.url}"
    )


def format_grouped(items: List[Item], markup_cfg: MarkupConfig) -> None:
    groups: Dict[Tuple[str, int, str], List[Item]] = {}
    for it in items:
        groups.setdefault(group_key(it), []).append(it)

    for gk in sorted(groups.keys(), key=lambda x: (normalize_text(x[0]), x[1], normalize_text(x[2]))):
        model, mem, color = gk
        print("\n" + "=" * 64)
        print(f"{model} / {mem}GB / {color}")

        arr = groups[gk]
        arr.sort(key=lambda x: (SIM_ORDER.get(x.sim_desc, 9), x.price_my))

        for it in arr:
            mk = markup_cfg.get(it.model)
            my_price = it.price_site + mk
            print(f"- SIM:{it.sim_desc:8} | {it.stock_status:12} | Syoma:{it.price_site} ₽ | Твоя:{my_price} ₽")
            print(f"  {it.url}")


def best_item(items: List[Item], markup_cfg: MarkupConfig) -> Optional[Item]:
    best: Optional[Item] = None
    best_price: Optional[int] = None
    for it in items:
        mk = markup_cfg.get(it.model)
        my_price = it.price_site + mk
        if best_price is None or my_price < best_price:
            best = it
            best_price = my_price
    return best


def parse_window(s: str) -> int:
    s = (s or "").strip().lower()
    if not s:
        return 24 * 3600
    if s.isdigit():
        return int(s)
    m = re.fullmatch(r"(\d+)\s*([hdчд])", s)
    if not m:
        return 24 * 3600
    n = int(m.group(1))
    u = m.group(2)
    if u in {"h", "ч"}:
        return n * 3600
    if u in {"d", "д"}:
        return n * 86400
    return 24 * 3600


def get_history_for_titles(titles: List[str], since_ts: int, db_path: str = DB_PATH) -> Dict[str, List[Tuple[int, int, str]]]:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    out: Dict[str, List[Tuple[int, int, str]]] = {}
    for t in titles:
        rows = cur.execute(
            "SELECT ts, price_site, stock_status FROM price_history WHERE title=? AND ts>=? ORDER BY ts ASC",
            (t, since_ts),
        ).fetchall()
        out[t] = [(int(r[0]), int(r[1]), str(r[2])) for r in rows]
    con.close()
    return out


def cmd_delta(query: str, window_s: int, items_cache: List[Item], markup_cfg: MarkupConfig) -> None:
    cls = classify_query(query)
    if cls == "general":
        print("Запрос слишком общий. Пример: :delta iphone 16 256 24h")
        return

    res_all = search_prices(query, items_cache, allowed_statuses=None)
    if not res_all:
        print("Ничего не найдено по запросу.")
        return

    titles = [it.title for it in res_all]
    since = now_ts() - window_s
    hist = get_history_for_titles(titles, since_ts=since)

    print(_ansi(f"История изменений за ~{window_s//3600}ч:", "cyan", bold=True))

    for it in sorted(res_all, key=sort_key):
        rows = hist.get(it.title, [])
        if len(rows) < 2:
            continue
        first_ts, first_price, first_status = rows[0]
        last_ts, last_price, last_status = rows[-1]
        diff = last_price - first_price

        if diff > 0:
            diff_s = _ansi(f"▲ +{diff} ₽", "red", bold=True)
        elif diff < 0:
            diff_s = _ansi(f"▼ {diff} ₽", "green", bold=True)
        else:
            diff_s = _ansi("= 0 ₽", "gray")

        print("\n" + "-" * 64)
        print(f"{it.model} / {it.memory_gb or '??'}GB / {it.color_ru} / SIM:{it.sim_desc}")
        print(f"Было: {first_price} ₽ ({first_status}) @ {datetime.fromtimestamp(first_ts).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Стало: {last_price} ₽ ({last_status}) @ {datetime.fromtimestamp(last_ts).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Изменение: {diff_s}")
        print(f"Ссылка: {it.url}")

    print("\nЕсли строк мало — возможно, в выбранном окне цена не менялась.")


def db_add_watch(query: str, mode: str, threshold: Optional[int], drop_amount: Optional[int]) -> int:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO watches(query, mode, threshold, drop_amount, last_best_my, last_trigger_ts, is_enabled, created_ts) VALUES(?,?,?,?,?,?,?,?)",
        (query, mode, threshold, drop_amount, None, None, 1, now_ts()),
    )
    con.commit()
    wid = int(cur.lastrowid)
    con.close()
    return wid


def db_list_watches() -> List[Tuple]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    rows = cur.execute(
        "SELECT id, query, mode, threshold, drop_amount, last_best_my, last_trigger_ts, is_enabled, created_ts FROM watches ORDER BY id DESC"
    ).fetchall()
    con.close()
    return rows


def db_del_watch(watch_id: int) -> None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM watches WHERE id=?", (watch_id,))
    con.commit()
    con.close()


def db_update_watch_state(watch_id: int, last_best_my: Optional[int], last_trigger_ts: Optional[int]) -> None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "UPDATE watches SET last_best_my=?, last_trigger_ts=? WHERE id=?",
        (last_best_my, last_trigger_ts, watch_id),
    )
    con.commit()
    con.close()


def db_outbox_add(watch_id: int, message: str, payload: Dict[str, Any]) -> None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO alert_outbox(ts, watch_id, message, payload_json) VALUES(?,?,?,?)",
        (now_ts(), watch_id, message, json.dumps(payload, ensure_ascii=False)),
    )
    con.commit()
    con.close()


def db_outbox_list(limit: int = 50) -> List[Tuple]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    rows = cur.execute(
        "SELECT id, ts, watch_id, message, payload_json FROM alert_outbox ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    con.close()
    return rows


def run_watches(items_cache: List[Item], markup_cfg: Optional[MarkupConfig]) -> None:
    if markup_cfg is None:
        markup_cfg = MarkupConfig(MARKUP_PATH)
        markup_cfg.load()

    watches = db_list_watches()
    if not watches:
        return

    for row in watches:
        wid, query, mode, threshold, drop_amount, last_best_my, last_trigger_ts, is_enabled, created_ts = row
        if int(is_enabled) != 1:
            continue

        found = search_prices(str(query), items_cache, allowed_statuses=DEFAULT_ALLOWED_STATUSES)
        if not found:
            continue

        b = best_item(found, markup_cfg)
        if not b:
            continue

        mk = markup_cfg.get(b.model)
        cur_best_my = b.price_site + mk

        now_ = now_ts()
        if last_trigger_ts and (now_ - int(last_trigger_ts) < 30 * 60):
            db_update_watch_state(int(wid), int(cur_best_my), int(last_trigger_ts))
            continue

        fired = False
        msg = ""
        payload = {
            "query": query,
            "best": {
                "model": b.model,
                "memory_gb": b.memory_gb,
                "color_ru": b.color_ru,
                "sim": b.sim_desc,
                "status": b.stock_status,
                "price_site": b.price_site,
                "markup": mk,
                "price_my": cur_best_my,
                "url": b.url,
            },
        }

        if mode == "lt" and threshold is not None:
            if int(cur_best_my) <= int(threshold):
                fired = True
                msg = f"✅ WATCH #{wid}: {query} стало <= {threshold} ₽. Сейчас: {cur_best_my} ₽"
        elif mode == "drop" and drop_amount is not None:
            if last_best_my is not None and int(cur_best_my) <= int(last_best_my) - int(drop_amount):
                fired = True
                msg = f"📉 WATCH #{wid}: {query} упало на {drop_amount} ₽. Было: {last_best_my} ₽ → Сейчас: {cur_best_my} ₽"

        if fired:
            db_outbox_add(int(wid), msg, payload)
            db_update_watch_state(int(wid), int(cur_best_my), now_)
        else:
            db_update_watch_state(int(wid), int(cur_best_my), int(last_trigger_ts) if last_trigger_ts else None)


def json_search(query: str, items_cache: List[Item], markup_cfg: MarkupConfig, all_statuses: bool = False) -> Dict[str, Any]:
    cls = classify_query(query)
    if cls == "general":
        return {
            "ok": False,
            "error": "query_too_general",
            "hint": "Уточни модель: iphone 16 / iphone 16 pro / iphone se 2022. Можно с памятью: iphone 16 256",
        }

    allowed = None if all_statuses else DEFAULT_ALLOWED_STATUSES
    res = search_prices(query, items_cache, allowed_statuses=allowed)

    sess = make_session()
    resolve_unknown_sims_for_results(res[:20], sess)

    out_items = []
    for it in res:
        mk = markup_cfg.get(it.model)
        out_items.append(
            {
                "title": it.title,
                "url": it.url,
                "model": it.model,
                "memory_gb": it.memory_gb,
                "color_ru": it.color_ru,
                "color_en": it.color_en,
                "sim": it.sim_desc,
                "status": it.stock_status,
                "price_site": it.price_site,
                "markup": mk,
                "price_my": it.price_site + mk,
                "image_url": it.image_url,
                "image_local": it.image_local,
                "updated_ts": it.ts,
            }
        )

    best = best_item(res, markup_cfg)
    best_obj = None
    if best:
        mk = markup_cfg.get(best.model)
        best_obj = {
            "model": best.model,
            "memory_gb": best.memory_gb,
            "color_ru": best.color_ru,
            "sim": best.sim_desc,
            "status": best.stock_status,
            "price_site": best.price_site,
            "markup": mk,
            "price_my": best.price_site + mk,
            "url": best.url,
            "image_url": best.image_url,
            "image_local": best.image_local,
        }

    return {"ok": True, "query": query, "class": cls, "best": best_obj, "items": out_items}


def json_alerts(limit: int = 50) -> Dict[str, Any]:
    rows = db_outbox_list(limit=limit)
    out = []
    for rid, ts, wid, msg, payload_json in rows:
        try:
            payload = json.loads(payload_json) if payload_json else None
        except Exception:
            payload = None
        out.append({"id": rid, "ts": ts, "watch_id": wid, "message": msg, "payload": payload})
    return {"ok": True, "alerts": out}


def print_help():
    print(r"""
Команды:
  :help             — помощь
  :refresh           — обновить Syoma
  :limit N           — лимит короткой выдачи (по умолчанию 3), для точного запроса выводим всё
  :status stock      — только доступные
  :status all        — все статусы
  :sim on/off        — допарсивать SIM (лениво)

История:
  :delta <запрос> [24h|7d|48ч|3д]

Накрутка:
  :markup show
  :markup default N
  :markup set <regex> N
  :markup del <regex>

Алерты:
  :watch <запрос> < 100000
  :watch <запрос> drop 3000
  :watch list
  :watch del ID
  :alerts

JSON:
  python syoma_final.py --json "iphone 16 256"
  python syoma_final.py --json --alerts
Демон:
  python syoma_final.py --daemon --interval 30m
""")


def should_pause() -> bool:
    return os.name == "nt" and not sys.stdin.isatty()


def parse_interval(s: str) -> int:
    s = (s or "").strip().lower()
    if not s:
        return 3600
    if s.isdigit():
        return int(s)
    m = re.fullmatch(r"(\d+)\s*([smhdчд])", s)
    if not m:
        return 3600
    n = int(m.group(1))
    u = m.group(2)
    if u == "s":
        return n
    if u == "m":
        return n * 60
    if u in {"h", "ч"}:
        return n * 3600
    if u in {"d", "д"}:
        return n * 86400
    return 3600


def daemon_loop(interval_s: int, once: bool, markup_cfg: MarkupConfig) -> None:
    log(f"[daemon] interval={interval_s}s once={once}")
    while True:
        try:
            total = refresh(base_markup_rub=markup_cfg.default, markup_cfg=markup_cfg, debug=False)
            log(f"[daemon] refreshed: {total}")
        except Exception as e:
            log(f"[daemon][WARN] refresh failed: {e}")
        if once:
            break
        time.sleep(interval_s)


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--all-statuses", action="store_true")
    parser.add_argument("--alerts", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--delta", action="store_true")
    parser.add_argument("--window", default="24h")
    parser.add_argument("--help", action="store_true")
    parser.add_argument("query", nargs="*")
    args = parser.parse_args()

    if args.help:
        print_help()
        return

    init_db()

    markup_cfg = MarkupConfig(MARKUP_PATH)
    markup_cfg.load()

    if args.daemon:
        daemon_loop(parse_interval(args.interval), args.once, markup_cfg)
        return

    if args.refresh:
        total = refresh(base_markup_rub=markup_cfg.default, markup_cfg=markup_cfg, debug=False)
        log(f"Обновлено позиций: {total}")

    if args.json and args.alerts:
        print(json.dumps(json_alerts(), ensure_ascii=False, indent=2))
        return

    items_cache = load_all_items()

    if args.json:
        q = " ".join(args.query).strip()
        if not q:
            print(json.dumps({"ok": True, "items_in_cache": len(items_cache)}, ensure_ascii=False, indent=2))
            return
        if args.delta:
            window_s = parse_window(args.window)
            res_all = search_prices(q, items_cache, allowed_statuses=None)
            titles = [it.title for it in res_all]
            hist = get_history_for_titles(titles, since_ts=now_ts() - window_s)
            print(json.dumps({"ok": True, "query": q, "window_s": window_s, "history": hist}, ensure_ascii=False, indent=2))
            return
        print(json.dumps(json_search(q, items_cache, markup_cfg, all_statuses=args.all_statuses), ensure_ascii=False, indent=2))
        return

    result_limit = 3
    allowed_statuses: Optional[Set[str]] = DEFAULT_ALLOWED_STATUSES
    sim_resolve_on = True
    session_for_resolve = make_session()

    print("Готово. :help — команды.")

    while True:
        q = input("\nЗапрос клиента (или пусто для выхода): ").strip()
        if not q:
            break

        if q == ":help":
            print_help()
            continue

        if q == ":refresh":
            total = refresh(base_markup_rub=markup_cfg.default, markup_cfg=markup_cfg, debug=True)
            log(f"Обновлено позиций: {total}")
            items_cache = load_all_items()
            log(f"В кэше: {len(items_cache)}")
            continue

        if q.startswith(":limit "):
            try:
                result_limit = int(q.split()[-1])
                log(f"limit={result_limit}")
            except Exception:
                print("Пример: :limit 10")
            continue

        if q == ":status stock":
            allowed_statuses = DEFAULT_ALLOWED_STATUSES
            log("Фильтр: только доступные")
            continue

        if q == ":status all":
            allowed_statuses = None
            log("Фильтр: все статусы")
            continue

        if q == ":sim on":
            sim_resolve_on = True
            log("SIM resolve: ON")
            continue

        if q == ":sim off":
            sim_resolve_on = False
            log("SIM resolve: OFF")
            continue

        if q.startswith(":markup "):
            parts = q.split()
            sub = parts[1] if len(parts) > 1 else ""
            if sub == "show":
                print(markup_cfg.show())
                continue
            if sub == "default" and len(parts) >= 3:
                markup_cfg.set_default(int(parts[2]))
                print(markup_cfg.show())
                continue
            if sub == "set":
                try:
                    rest = q[len(":markup set "):].strip()
                    pat, val = rest.rsplit(" ", 1)
                    markup_cfg.set_rule(pat.strip(), int(val))
                    print(markup_cfg.show())
                except Exception:
                    print(r"Пример: :markup set ^iPhone\s+16\b 7000")
                continue
            if sub == "del":
                pat = q[len(":markup del "):].strip()
                markup_cfg.del_rule(pat)
                print(markup_cfg.show())
                continue
            print("Команды: :markup show | :markup default N | :markup set <regex> N | :markup del <regex>")
            continue

        if q.startswith(":delta "):
            parts = q.split()
            if len(parts) >= 2:
                window_s = 24 * 3600
                if len(parts) >= 3 and re.fullmatch(r"\d+[hdчд]|\d+", parts[-1].lower()):
                    window_s = parse_window(parts[-1])
                    q2 = " ".join(parts[1:-1])
                else:
                    q2 = " ".join(parts[1:])
                cmd_delta(q2, window_s, items_cache, markup_cfg)
            else:
                print("Пример: :delta iphone 16 256 24h")
            continue

        if q.startswith(":watch "):
            rest = q[len(":watch "):].strip()
            if rest == "list":
                rows = db_list_watches()
                if not rows:
                    print("watch-ов нет.")
                    continue
                for row in rows:
                    wid, query, mode, thr, drop, last_best, last_tr, en, ct = row
                    print(f"#{wid} [{('ON' if en else 'OFF')}] {query} | mode={mode} thr={thr} drop={drop} last_best={last_best}")
                continue
            if rest.startswith("del "):
                try:
                    wid = int(rest.split()[-1])
                    db_del_watch(wid)
                    print("Удалил watch", wid)
                except Exception:
                    print("Пример: :watch del 3")
                continue

            m = re.search(r"\s<\s(\d+)\s*$", rest)
            if m:
                thr = int(m.group(1))
                query_part = rest[:m.start()].strip()
                wid = db_add_watch(query_part, "lt", thr, None)
                print(f"Добавлен watch #{wid}: {query_part} < {thr}")
                continue

            m = re.search(r"\sdrop\s(\d+)\s*$", rest)
            if m:
                drop = int(m.group(1))
                query_part = rest[:m.start()].strip()
                wid = db_add_watch(query_part, "drop", None, drop)
                print(f"Добавлен watch #{wid}: {query_part} drop {drop}")
                continue

            print("Примеры:\n  :watch iphone 16 pro 256 < 100000\n  :watch iphone 16 256 drop 3000\n  :watch list\n  :watch del 3")
            continue

        if q == ":alerts":
            rows = db_outbox_list(limit=20)
            if not rows:
                print("outbox пуст.")
                continue
            for rid, ts, wid, msg, payload_json in rows:
                print("\n" + "-" * 64)
                print(datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S"), f"(watch #{wid})")
                print(msg)
            continue

        cls = classify_query(q)
        if cls == "general":
            print("Запрос слишком общий. Уточни: iphone 16 / айфон 15 pro / iphone 16 256")
            continue

        local_limit = 9999 if cls == "precise" else max(result_limit, 10)

        res = search_prices(q, items_cache, allowed_statuses=allowed_statuses)
        if not res:
            res_any = search_prices(q, items_cache, allowed_statuses=None)
            if res_any:
                if sim_resolve_on:
                    resolve_unknown_sims_for_results(res_any[:20], session_for_resolve)
                print("Нашёл совпадения, но среди доступных сейчас нет. Показываю все статусы:")
                format_grouped(res_any[:local_limit], markup_cfg)
                continue
            print("Ничего не нашёл.")
            continue

        if sim_resolve_on:
            resolve_unknown_sims_for_results(res[:20], session_for_resolve)

        if cls == "precise":
            top = best_item(res, markup_cfg)
            if top:
                mk = markup_cfg.get(top.model)
                print(_ansi("ТОП (минимум):", "yellow", bold=True))
                print(f"{top.model} / {top.memory_gb or '??'}GB / {top.color_ru} / SIM:{top.sim_desc}")
                print(f"Твоя цена: {top.price_site + mk} ₽ (Syoma:{top.price_site} ₽ + накрутка:{mk} ₽)")
                print(top.url)
                print("")

        if local_limit >= 9999:
            format_grouped(res, markup_cfg)
        else:
            for i, it in enumerate(res[:local_limit], 1):
                print("\n" + "-" * 40)
                print(f"#{i}\n{format_item(it, markup_cfg)}")


def list_models_in_db(db_path: str = DB_PATH) -> List[str]:
    """Список моделей, реально присутствующих в базе."""
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    rows = cur.execute("SELECT DISTINCT model FROM prices WHERE model IS NOT NULL AND model != ''").fetchall()
    con.close()
    out = [str(r[0]).strip() for r in rows if r and r[0]]
    out.sort(key=lambda x: normalize_text(x))
    return out


def get_model_catalog() -> List[str]:
    """Базовый список моделей для настроек накрутки (не зависит от наличия)."""
    # Можно расширять/править под себя — это просто список в одном месте.
    return [
        "iPhone SE 2022",
        "iPhone 11",
        "iPhone 11 Pro",
        "iPhone 11 Pro Max",
        "iPhone 12 mini",
        "iPhone 12",
        "iPhone 12 Pro",
        "iPhone 12 Pro Max",
        "iPhone 13 mini",
        "iPhone 13",
        "iPhone 13 Pro",
        "iPhone 13 Pro Max",
        "iPhone 14",
        "iPhone 14 Plus",
        "iPhone 14 Pro",
        "iPhone 14 Pro Max",
        "iPhone 15",
        "iPhone 15 Plus",
        "iPhone 15 Pro",
        "iPhone 15 Pro Max",
        "iPhone 16",
        "iPhone 16 Plus",
        "iPhone 16 Pro",
        "iPhone 16 Pro Max",
        "iPhone 16e",
        "iPhone 17",
        "iPhone 17 Plus",
        "iPhone 17 Pro",
        "iPhone 17 Pro Max",
    ]



def history_daily_for_model(title: str, days: int = 30, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Дневная статистика по КОНКРЕТНОЙ позиции (min/max цен сайта).
    Теперь фильтрация идёт по полю title (модель+память+цвет+SIM).
    """
    title = (title or "").strip()
    if not title:
        return []
    since = now_ts() - int(days) * 24 * 3600

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    rows = cur.execute(
        """
        SELECT date(ts,'unixepoch','localtime') as day,
               MIN(price_site) as min_price,
               MAX(price_site) as max_price,
               COUNT(*) as points
        FROM price_history
        WHERE ts >= ? AND title = ?
        GROUP BY day
        ORDER BY day DESC
        """,
        (since, title),
    ).fetchall()

    con.close()
    return [dict(r) for r in rows]


def history_last_changes_for_model(title: str, limit: int = 50, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Последние точки истории по КОНКРЕТНОЙ позиции (по полю title)."""
    title = (title or "").strip()
    if not title:
        return []
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    rows = cur.execute(
        """
        SELECT title, ts, price_site, stock_status
        FROM price_history
        WHERE title = ?
        ORDER BY ts DESC
        LIMIT ?
        """,
        (title, int(limit)),
    ).fetchall()

    con.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    try:
        try:
            with open(LOG_PATH, "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass
        main()
    except Exception:
        log("[ERROR] Скрипт упал. Ошибка ниже:")
        print(traceback.format_exc())
    finally:
        if should_pause():
            input("\nНажми Enter, чтобы закрыть окно...")
