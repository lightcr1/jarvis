import re
import shutil
import subprocess

from fastapi import HTTPException

ALLOWED_SYSTEMD_SERVICES = {
    "jarvis", "nginx", "docker", "ssh", "ufw", "fail2ban"
}


def run_cmd(cmd: list[str], timeout: int = 8) -> str:
    process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    return (process.stdout or "").strip()


def valid_service_name(name: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z0-9_.@-]+", name))


def ensure_service_allowed(service: str) -> None:
    if not valid_service_name(service):
        raise HTTPException(400, "Invalid service name")
    if service not in ALLOWED_SYSTEMD_SERVICES:
        raise HTTPException(403, f"Service not allowed: {service}")


def is_write_command(text: str) -> bool:
    return text.strip().lower().startswith(("restart ", "start ", "stop "))


def format_bytes(size: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def tail_lines(text: str, max_lines: int = 6) -> str:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    return "\n".join(lines[-max_lines:]) if lines else ""


def parse_meminfo() -> dict[str, int] | None:
    try:
        info = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, value = line.split(":", 1)
                parts = value.strip().split()
                if not parts:
                    continue
                info[key] = int(parts[0]) * 1024
        return info
    except Exception:
        return None


def parse_ping(output: str) -> dict[str, str]:
    data: dict[str, str] = {}
    loss_match = re.search(r"(\d+)%\s+packet loss", output)
    if loss_match:
        data["packet_loss"] = f"{loss_match.group(1)}%"
    rtt_match = re.search(r"rtt .* = ([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+)", output)
    if rtt_match:
        data["rtt_min_ms"] = rtt_match.group(1)
        data["rtt_avg_ms"] = rtt_match.group(2)
        data["rtt_max_ms"] = rtt_match.group(3)
        data["rtt_mdev_ms"] = rtt_match.group(4)
    return data


def disk_usage(path: str = "/"):
    return shutil.disk_usage(path)
