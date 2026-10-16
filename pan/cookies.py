"""Cookie 串工具：__puus/__pus/__pugs 的合并、剥离、Set-Cookie 回填（对齐 YunX QuarkCookieUtil）。"""


def get_cookie_value(cookie: str, name: str) -> str:
    for part in (cookie or "").split(";"):
        part = part.strip()
        if part.startswith(name + "="):
            return part[len(name) + 1:]
    return ""


def merge_from_set_cookies(original: str, set_cookies: list[str],
                           tracked: tuple = ("__puus", "__pus", "__pugs")) -> str:
    """把响应 Set-Cookie 里的跟踪字段合并回原 Cookie 串（同名覆盖）。"""
    merged = dict()
    order = []
    for part in (original or "").split(";"):
        part = part.strip()
        if "=" in part:
            k = part.split("=", 1)[0]
            if k not in merged:
                order.append(k)
            merged[k] = part
    for sc in set_cookies or []:
        kv = sc.split(";", 1)[0].strip()
        if "=" not in kv:
            continue
        k = kv.split("=", 1)[0]
        if k in tracked:
            if k not in merged:
                order.append(k)
            merged[k] = kv
    return "; ".join(merged[k] for k in order)


def without_puus(cookie: str) -> str:
    """剥掉 __puus，用于触发服务端重新下发（AList refreshPuus 口径）。"""
    parts = [p.strip() for p in (cookie or "").split(";") if p.strip()]
    kept = [p for p in parts if not p.startswith("__puus=")]
    return "; ".join(kept)


def pugs_from_set_cookies(set_cookies) -> str | None:
    """从响应头集合里取游客态 __pugs（返回 `__pugs=值` 形态，可直接当 Cookie 头）。"""
    for sc in set_cookies or []:
        kv = sc.split(";", 1)[0].strip()
        if kv.startswith("__pugs=") and len(kv) > len("__pugs="):
            return kv
    return None
