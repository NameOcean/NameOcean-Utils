import calendar
import hashlib
import inspect
import logging
import logging.config
import os
import traceback
from contextlib import closing
from decimal import Decimal
from functools import reduce
from socket import AF_INET, SOCK_STREAM, gethostname, socket
from typing import Tuple

import pyredisrpc
import requests
import seqlog


def get_service(services):
    for hostname, port in services:
        with closing(socket(AF_INET, SOCK_STREAM)) as sock:
            sock.settimeout(2)
            if sock.connect_ex((hostname, port)) == 0:
                return (hostname, port)

    raise Exception("Unable to connect to any of the following services: %s" % services)


class RiverRPC:

    def __init__(self, server_name, redis_url=None, river_url=None):
        self.server_name = server_name
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self.river_url = river_url or os.getenv("RIVER_URL")
        self.server = pyredisrpc.Server(server_name, redis_url=self.redis_url)

    def add_method(self, fn, register=True):
        if register:
            self.register_method(fn)
        self.server.method(fn)

    def run(self):
        self.server.run()

    def register_method(self, fn):
        try:
            requests.get(
                "%s?method=%s&server=%s"
                % (self.river_url, fn.__name__, self.server_name)
            )
        except Exception:
            pass


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
        override_root_logger=False,
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
            tb = traceback.TracebackException.from_exception(e).format()
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
