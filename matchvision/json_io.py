"""Atomic incremental JSON writing: no giant serialized string in memory."""
import json


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, allow_nan=False, separators=(",", ":"))
    temporary.replace(path)
