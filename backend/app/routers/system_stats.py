import time

import psutil
from fastapi import APIRouter

from app.sources import smb_stats

router = APIRouter()

_process = psutil.Process()
# First call always returns 0.0 -- prime it at import time so the first real
# request already reflects usage since process start, not since the request.
_process.cpu_percent(interval=None)
# psutil reports a process's CPU time relative to a single core (so it can
# exceed 100% on a multi-core box) -- divide by core count to get a friendly
# 0-100% share of total system CPU for the frontend gauge. Inside a container
# this is the *node's* logical CPU count (containers don't get their own
# `/proc/cpuinfo` without cgroup-aware tooling), not a pod CPU limit -- the
# absolute trend (does it spike under load?) is still meaningful even where
# the exact percentage doesn't line up with a kubelet/metrics-server view.
_CPU_COUNT = psutil.cpu_count() or 1

# CPU/memory must cover the whole process *tree*, not just the uvicorn
# worker: conversion/preview/tagging jobs shell out to ffmpeg as a child
# process, which is where nearly all the CPU (and a good chunk of memory)
# actually goes during a job -- measuring only `_process` made the gauge sit
# near 0% while a conversion was pegging the CPU (chat request 2026-07-19,
# reported via a Kubernetes deployment where `k9s` showed the real number).
# Each live process is tracked by pid across polls so its `cpu_percent()`
# delta is measured against its own previous poll rather than reseeded every
# request (which always reads 0.0 on a process's first call).
_tracked: dict[int, psutil.Process] = {_process.pid: _process}


def _refresh_tracked_children() -> set[int]:
    try:
        live_children = _process.children(recursive=True)
    except psutil.Error:
        live_children = []
    live_pids = {_process.pid} | {p.pid for p in live_children}

    for pid in list(_tracked):
        if pid not in live_pids:
            del _tracked[pid]

    newly_tracked = [p for p in live_children if p.pid not in _tracked]
    for p in newly_tracked:
        _tracked[p.pid] = p
        try:
            p.cpu_percent(interval=None)  # prime -- this read is thrown away
        except psutil.Error:
            pass
    return {p.pid for p in newly_tracked}


@router.get("/system/stats")
def get_system_stats() -> dict:
    just_primed = _refresh_tracked_children()

    cpu_total = 0.0
    memory_total = 0
    for pid, proc in list(_tracked.items()):
        try:
            memory_total += proc.memory_info().rss
            # A freshly-primed child's first real read happens next poll --
            # reading it again this same request would measure a near-zero
            # interval and produce a meaningless spike.
            if pid not in just_primed:
                cpu_total += proc.cpu_percent(interval=None)
        except psutil.NoSuchProcess:
            del _tracked[pid]

    return {
        "cpu_percent": cpu_total / _CPU_COUNT,
        "memory_rss_bytes": memory_total,
        "memory_percent": memory_total / psutil.virtual_memory().total * 100,
        "smb_bytes_transferred_total": smb_stats.get_total_bytes_transferred(),
        "timestamp": time.time(),
    }
