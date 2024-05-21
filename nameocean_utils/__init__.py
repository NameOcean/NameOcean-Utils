import calendar
import hashlib
import inspect
import logging
import logging.config
import os
from functools import reduce
from typing import Tuple

import pyredisrpc
import requests
from arq.connections import RedisSettings
from arq.logs import default_log_config
from arq.worker import Worker
from pygelf import GelfUdpHandler


class ArqRPC:

    def __init__(
        self,
        queue_name,
        redis_host=None,
        redis_port=None,
        redis_db=0,
        redis_username=None,
        redis_password=None,
    ):
        self.queue_name = queue_name
        self.redis_settings = RedisSettings(
            host=redis_host or os.getenv("REDIS_HOST"),
            port=redis_port or os.getenv("REDIS_PORT"),
            database=redis_db or os.getenv("REDIS_DB"),
            username=redis_username or os.getenv("REDIS_USER"),
            password=redis_password or os.getenv("REDIS_PASS"),
            conn_timeout=5,
            conn_retries=10,
            retry_on_timeout=True,
        )
        self.functions = []
        self.worker = None
        logging.config.dictConfig(default_log_config(True))

    def add_method(self, fn, register=True):
        self.functions.append(fn)
        if register:
            self.register_method(fn)

    def register_method(self, fn):
        try:
            requests.get(
                "%s?method=%s&server=%s"
                % (self.river_url, fn.__name__, self.server_name)
            )
        except Exception:
            pass

    def get_worker(self):
        if self.worker is None:
            self.worker = Worker(
                functions=self.functions,
                queue_name=self.queue_name,
                redis_settings=self.redis_settings,
            )

        return self.worker

    def run(self):
        self.get_worker().run()


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


def get_task_logger(name, fname, seq_host=None, seq_port=None):
    fmt = "%(asctime)s %(levelname)s:%(name)s:%(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
    )
    logger = logging.getLogger(name)
    logger.addHandler(
        GelfUdpHandler(
            host=seq_host or os.getenv("SEQ_HOST"),
            port=int(seq_port or os.getenv("SEQ_PORT")),
            _task=name,
            _function=fname,
        )
    )
    return logger


def river_task(func):
    def task(*args, **kwargs):
        kwargs["logger"] = get_task_logger(
            "task-%s" % kwargs.get("task_id", "0"), func.__name__
        )
        func(*args, **kwargs)

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
