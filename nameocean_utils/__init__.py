import hashlib
import inspect
import logging
import logging.config
import os
import traceback
from decimal import Decimal
from functools import reduce
from socket import gethostname

import requests
import seqlog


def get_logger(name, verbose=True):
    log_level = "DEBUG" if verbose else "INFO"
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "rpc.standard": {
                "level": log_level,
                "class": "logging.StreamHandler",
                "formatter": "rpc.standard",
            }
        },
        "formatters": {
            "rpc.standard": {
                "format": "%(asctime)s %(module)s: %(message)s",
                "datefmt": "%d-%m-%Y %H:%M:%S",
            }
        },
        "loggers": {"rpc": {"handlers": ["rpc.standard"], "level": log_level}},
    }

    logging.config.dictConfig(log_config)
    return logging.getLogger(name)


def get_task_logger(name, fname, **kwargs):
    seqlog.log_to_seq(
        server_url=os.environ.get("SEQ_URL"),
        api_key=os.environ.get("SEQ_KEY"),
        level=logging.INFO,
        batch_size=5,
        auto_flush_timeout=3,  # seconds
        override_root_logger=True,
        support_extra_properties=True,
    )

    seqlog.set_global_log_properties(task=name, app="river", hostname=gethostname())

    return logging.getLogger(fname)


def river_task(func):
    def task(*args, **kwargs):
        logger = get_task_logger("task-%s" % kwargs.get("task_id", "0"), func.__name__)
        kwargs["logger"] = logger
        try:
            return func(*args, **kwargs)
        except Exception as e:
            tb = "".join(traceback.TracebackException.from_exception(e).format())
            logger.error(tb)
            return {"error": tb}

    task.__name__ = func.__name__

    return task


def notify_discord(text, hook_url=None, username=None):
    hook_url = hook_url or os.getenv("DISCORD_HOOK")
    username = username or os.getenv("DISCORD_USERNAME")

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


def getter(obj, *args, default=None):
    for arg in args:
        try:
            return reduce(
                lambda a, b: (
                    a[int(b)]
                    if b.isdigit()
                    else (getattr(a, b) if hasattr(a, b) else a[b])
                ),
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
    left = [elm for elm in ls if elm[attr] <= pivot[attr]]
    right = [elm for elm in ls if elm[attr] > pivot[attr]]

    return qsort_attr(left, attr) + [pivot] + qsort_attr(right, attr)


def bytesto(bytes, to, bsize=1024):
    a = {"k": 1, "m": 2, "g": 3, "t": 4, "p": 5, "e": 6}
    return Decimal(bytes) / Decimal(bsize ** a[to])
