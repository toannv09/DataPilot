"""Cache output LLM theo hash(input), TTL 1 giờ."""

import hashlib
import json
import time

CACHE_TTL_SECONDS = 3600

_cache = {}


def _make_key(data):
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def get_cached(data):
    """Trả về giá trị cache nếu còn hạn, None nếu không có hoặc hết hạn."""
    key = _make_key(data)
    entry = _cache.get(key)
    if entry is None:
        return None

    timestamp, value = entry
    if time.time() - timestamp > CACHE_TTL_SECONDS:
        del _cache[key]
        return None

    return value


def set_cached(data, value):
    """Lưu giá trị vào cache."""
    key = _make_key(data)
    _cache[key] = (time.time(), value)
