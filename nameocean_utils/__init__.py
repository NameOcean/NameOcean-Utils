import calendar
import hashlib
import inspect
import os
from functools import reduce
from typing import Tuple

import requests


def notify_discord(text, hook_url=None, username=None):
    if not hook_url:
        hook_url = os.getenv("DISCORD_HOOK")

    if not username:
        username = os.getenv("DISCORD_USERNAME")

    stack = inspect.stack()
    # path = inspect.getabsfile(notify_discord)
    cf = None
    next = False
    for s in stack:
        if next:
            cf = s
        if s.function == "notify_discord":
            next = True

    payload = {
        "content": f"{cf.filename}:{cf.lineno} {text}",
        "username": username,
    }
    result = requests.post(hook_url, json=payload)
    result.raise_for_status()


def hash32(str, length=32):
    return hashlib.sha224(str.encode("utf-8")).hexdigest()[:length]


def get_month_name(month: int) -> Tuple[str, str]:
    return calendar.month_name[month], calendar.month_abbr[month]


def grep(text, match, after=0, before=0, ind=False):
    """
    Return matched lines in given text as a list. Similar to grep function but a simple one.
    """
    idx = []
    if type(text) is str:
        lines = text.split("\n")
    else:
        lines = text

    for i, line in enumerate(lines):
        if str(match) not in line:
            continue

        idx.append(i)
        if after:
            idx += range(i + 1, i + 1 + after)
        if before:
            idx += range(i - before, i)

    idx = sorted(list(set(idx)))

    if ind:
        return idx

    return [lines[i] for i in idx]


def getter(obj, *args, default=None):
    for arg in args:
        try:
            return reduce(
                lambda a, b: a[int(b)]
                if b.isdigit()
                else (getattr(a, b) if hasattr(a, b) else a[b]),
                arg.split("."),
                obj,
            )
        except Exception:
            continue

    return default


def qsort_attr(ls, attr):
    if len(ls) < 2:
        return ls

    pivot = ls.pop()
    left = [l for l in ls if l[attr] <= pivot[attr]]
    right = [l for l in ls if l[attr] > pivot[attr]]

    return qsort_attr(left, attr) + [pivot] + qsort_attr(right, attr)
