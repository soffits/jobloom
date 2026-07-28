from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if value is ...:
            return True
    except ValueError:
        return False
    try:
        result = value != value
    except Exception:
        result = False
    if isinstance(result, bool) and result:
        return True
    try:
        import pandas as pd  # type: ignore

        if pd.isna(value) is True:
            return True
    except Exception:
        pass
    return False


def json_safe(value: Any) -> Any:
    if is_missing(value):
        return None
    if isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return json_safe(value.value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items() if json_safe(v) is not None}
    if isinstance(value, list | tuple | set):
        return [json_safe(v) for v in value if json_safe(v) is not None]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    return str(value)
