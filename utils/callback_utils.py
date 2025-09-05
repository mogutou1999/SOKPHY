# utils/callback_utils.py
from typing import Optional
from uuid import UUID

def parse_callback_uuid(data: str, prefix: str) -> Optional[UUID]:
    if not data or not data.startswith(prefix):
        return None
    parts = data.split(":")
    if len(parts) != 2:
        return None
    try:
        return UUID(parts[1])
    except ValueError:
        return None

def parse_callback_int(data: str, prefix: str) -> Optional[int]:
    if not data or not data.startswith(prefix):
        return None
    parts = data.split(":")
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return int(parts[1])
