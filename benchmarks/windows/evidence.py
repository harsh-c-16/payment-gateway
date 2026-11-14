"""Read-only resource and bounded clock observations; never exports container Env."""

import ctypes
import hashlib
import json
import os
import platform
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from infra import postgres

ROOT = postgres.ROOT


def desktop_only():
    if os.name != "nt":
        raise RuntimeError("Run this workflow in Windows PowerShell on the Desktop checkout")
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
    ) as key:
        desktop = Path(os.path.expandvars(winreg.QueryValueEx(key, "Desktop")[0])).resolve()
    if not ROOT.resolve().is_relative_to(desktop):
        raise RuntimeError("This workflow requires the project under the Windows Desktop")


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False) + "\n", "utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(*args, timeout=30, env=None):
    result = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        # Never include stderr: Docker initialization errors can contain private bindings.
        raise RuntimeError(f"{args[0]} failed with exit {result.returncode}")
    return result.stdout.strip()


def host():
    script = (
        "$c=Get-CimInstance Win32_Processor; $m=Get-CimInstance Win32_ComputerSystem; "
        "$o=Get-CimInstance Win32_OperatingSystem; "
        "$d=Get-CimInstance Win32_DiskDrive; "
        "[pscustomobject]@{cpu_model=@($c.Name);physical_cores=($c|Measure-Object "
        "NumberOfCores -Sum).Sum;total_memory_bytes=[long]$m.TotalPhysicalMemory;"
        "os=$o.Caption;os_version=$o.Version;storage=@($d|Select-Object Model,MediaType,Size)}"
        "|ConvertTo-Json -Depth 5 -Compress"
    )
    source_hash = hashlib.sha256()
    paths = command("git", "ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    for name in sorted(set(paths)):
        path = ROOT / name
        if path.is_file():
            source_hash.update(name.encode("utf-8") + b"\0" + path.read_bytes())
    return {
        **json.loads(command("powershell.exe", "-NoProfile", "-Command", script)),
        "python": platform.python_version(),
        "git_commit": command("git", "rev-parse", "HEAD"),
        "dirty": bool(command("git", "status", "--porcelain")),
        "application_lock_sha256": digest(ROOT / "uv.lock"),
        "source_tree_sha256": source_hash.hexdigest(),
        "docker": json.loads(command("docker", "info", "--format", "{{json .}}"))[
            "OperatingSystem"
        ],
    }


def process_usage():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t)
            for name in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
            )
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    counter = Counters()
    counter.cb = ctypes.sizeof(counter)
    if not psapi.GetProcessMemoryInfo(
        kernel.GetCurrentProcess(), ctypes.byref(counter), counter.cb
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    cpu = os.times()
    return {
        "rss_bytes": counter.WorkingSetSize,
        "peak_rss_bytes": counter.PeakWorkingSetSize,
        "cpu_seconds": cpu.user + cpu.system,
    }


def clock_probe(read_remote, *, samples=5):
    rows = []
    for _ in range(samples):
        wall, start = time.time(), time.perf_counter()
        remote = float(read_remote())
        elapsed = time.perf_counter() - start
        end_wall = time.time()
        offset = remote - (wall + elapsed / 2)
        rows.append(
            {
                "host_utc_epoch": wall,
                "remote_utc_epoch": remote,
                "round_trip_ms": elapsed * 1000,
                "offset_ms": offset * 1000,
                "offset_bound_ms": (abs(offset) + elapsed / 2) * 1000,
                "host_clock_step_ms": abs(end_wall - wall - elapsed) * 1000,
            }
        )
    best = min(rows, key=lambda r: r["round_trip_ms"])
    return {
        "samples": rows,
        "best": best,
        "clock_domain": "Windows UTC vs Docker UTC",
        "elapsed_clock": "local perf_counter; never subtracted across processes",
    }


def container_facts(ids):
    # Select fields explicitly; Config.Env contains passwords and is never requested.
    template = (
        '{"id":{{json .Id}},"image_id":{{json .Image}},'
        '"image":{{json .Config.Image}},"labels":{{json .Config.Labels}},'
        '"state":{{json .State}},"memory_bytes":{{json .HostConfig.Memory}},'
        '"nano_cpus":{{json .HostConfig.NanoCpus}}}'
    )
    return [
        json.loads(row)
        for row in command("docker", "inspect", "--format", template, *ids).splitlines()
    ]


def clocks(ids, *, max_error_ms=500):
    probes = {
        identity: clock_probe(
            lambda identity=identity: command("docker", "exec", identity, "date", "+%s.%N")
        )
        for identity in ids
    }
    return {
        "observed_at": datetime.now(UTC).isoformat(),
        "max_error_ms": max_error_ms,
        "passed": all(
            p["best"]["offset_bound_ms"] <= max_error_ms
            and all(r["host_clock_step_ms"] <= 10 for r in p["samples"])
            for p in probes.values()
        )
        and bool(probes),
        "probes": probes,
    }


def live_snapshot(out, *, max_error_ms=500):
    desktop_only()
    write(out, {"status": "VERIFYING", "passed": False})
    try:
        facts = _live_snapshot(out, max_error_ms=max_error_ms)
        facts["status"] = "VERIFIED"
        write(out, facts)
        return facts
    except Exception as error:
        facts = json.loads(Path(out).read_text(encoding="utf-8"))
        facts.update(status="FAILED", passed=False, error_type=type(error).__name__)
        write(out, facts)
        raise


def _live_snapshot(out, *, max_error_ms=500):
    """Prototype resources must equal its declared allocations before latency claims."""
    desktop_only()
    from infra import prototype

    ids = command(
        "docker", "ps", "-q", "--filter", "label=com.docker.compose.project=" + postgres.PROJECT
    ).splitlines()
    if not ids:
        raise RuntimeError("Start the Desktop prototype before live verification")
    facts = {
        "host": host(),
        "containers": container_facts(ids),
        "clock": clocks(ids, max_error_ms=max_error_ms),
    }
    try:
        facts["verified_allocations"] = prototype.verify()
        actual = {r["labels"].get("com.docker.compose.service") for r in facts["containers"]}
        facts["resource_limits_passed"] = actual == set(facts["verified_allocations"])
    except postgres.SetupError:
        facts["resource_limits_passed"] = False
    status = subprocess.run(
        ["w32tm", "/query", "/status"],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=10,
    )
    facts["windows_time_service"] = {
        "exit_code": status.returncode,
        "output": status.stdout.strip(),
        "scope": "diagnostic; absolute NTP sync is not asserted",
    }
    facts["passed"] = facts["clock"]["passed"] and facts["resource_limits_passed"]
    write(out, facts)
    if not facts["passed"]:
        raise RuntimeError("Resource/clock verification failed; inspect the saved receipt")
    return facts


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/windows/live-controls.json")
    parser.add_argument("--max-clock-error-ms", type=float, default=500)
    args = parser.parse_args()
    live_snapshot(args.out, max_error_ms=args.max_clock_error_ms)
    print("Desktop prototype resource limits and bounded clocks verified")
