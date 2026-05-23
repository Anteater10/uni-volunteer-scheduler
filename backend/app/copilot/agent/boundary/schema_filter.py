from typing import Any


def apply(data: Any, *, allowed_fields: list[str]) -> Any:
    if isinstance(data, list):
        return [apply(item, allowed_fields=allowed_fields) for item in data]
    if not isinstance(data, dict):
        return data

    top_level = {f.split(".", 1)[0] for f in allowed_fields}
    nested: dict[str, list[str]] = {}
    for f in allowed_fields:
        if "." in f:
            head, tail = f.split(".", 1)
            nested.setdefault(head, []).append(tail)

    out: dict[str, Any] = {}
    for key, value in data.items():
        if key not in top_level:
            continue
        if key in nested and isinstance(value, (dict, list)):
            out[key] = apply(value, allowed_fields=nested[key])
        else:
            out[key] = value
    return out
