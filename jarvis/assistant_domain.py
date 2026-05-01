import ast
import base64
import hashlib
import http.client
import json
import operator as _operator
import os
import platform
import re
import secrets
import socket
import ssl as _ssl
import string
import time as _time
import urllib.error
import urllib.parse
import urllib.request
import uuid as _uuid
from datetime import datetime, date as _date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException

# Rotating JARVIS-style acknowledgment phrases — used by newer skill blocks.
# Keeps responses from feeling repetitive; deliberately formal/British.
_ACK_PHRASES = [
    "Certainly, sir.",
    "Of course.",
    "Right away.",
    "As you wish.",
    "Very good, sir.",
    "Understood.",
    "On it.",
    "I've taken care of that.",
    "Consider it done.",
    "At once.",
]
_ack_index = 0


def _ack() -> str:
    global _ack_index
    phrase = _ACK_PHRASES[_ack_index % len(_ACK_PHRASES)]
    _ack_index += 1
    return phrase


def _wmo_to_text(code: int) -> str:
    if code == 0:    return "clear sky"
    if code <= 2:    return "mainly clear"
    if code == 3:    return "overcast"
    if code <= 48:   return "foggy"
    if code <= 55:   return "drizzle"
    if code <= 65:   return "rain"
    if code <= 75:   return "snow"
    if code == 77:   return "snow grains"
    if code <= 82:   return "rain showers"
    if code <= 86:   return "snow showers"
    if code <= 99:   return "thunderstorm"
    return "unknown conditions"


def _fetch_weather(city: str) -> dict | None:
    try:
        geo_url = (
            "https://geocoding-api.open-meteo.com/v1/search?"
            + urllib.parse.urlencode({"name": city, "count": 1, "language": "en", "format": "json"})
        )
        with urllib.request.urlopen(geo_url, timeout=6) as resp:
            geo = json.loads(resp.read())
        results = geo.get("results") or []
        if not results:
            return None
        r = results[0]
        lat, lon, name = r["latitude"], r["longitude"], r.get("name", city)
        country = r.get("country_code", "")

        wx_url = (
            "https://api.open-meteo.com/v1/forecast?"
            + urllib.parse.urlencode({
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,weathercode,windspeed_10m,relative_humidity_2m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                "timezone": "auto", "forecast_days": 4,
            })
        )
        with urllib.request.urlopen(wx_url, timeout=6) as resp:
            wx = json.loads(resp.read())

        cur = wx.get("current", {})
        daily = wx.get("daily", {})
        temp = cur.get("temperature_2m")
        code = int(cur.get("weathercode", 0))
        wind = cur.get("windspeed_10m")
        d_highs  = daily.get("temperature_2m_max") or []
        d_lows   = daily.get("temperature_2m_min") or []
        d_rains  = daily.get("precipitation_probability_max") or []
        d_codes  = daily.get("weathercode") or []
        d_dates  = daily.get("time") or []
        high = d_highs[0] if d_highs else None
        low  = d_lows[0]  if d_lows  else None
        rain = d_rains[0] if d_rains else None

        forecast = []
        for i in range(1, min(4, len(d_dates))):
            forecast.append({
                "date": d_dates[i] if i < len(d_dates) else None,
                "high": d_highs[i] if i < len(d_highs) else None,
                "low":  d_lows[i]  if i < len(d_lows)  else None,
                "rain_pct": d_rains[i] if i < len(d_rains) else None,
                "condition": _wmo_to_text(int(d_codes[i])) if i < len(d_codes) else "Unknown",
            })

        return {
            "city": name, "country": country, "temp": temp,
            "condition": _wmo_to_text(code), "code": code,
            "wind_kmh": wind, "high": high, "low": low, "rain_pct": rain,
            "forecast": forecast,
        }
    except Exception:
        return None


def _is_weather_query(t: str) -> bool:
    keywords = [
        "weather", "wetter", "forecast", "vorhersage",
        "temperature", "temperatur", "how is it outside",
        "wie ist das wetter", "how is the weather",
        "what's the weather", "what is the weather",
        "wird es regnen", "will it rain",
        "wie warm", "wie kalt",
    ]
    stripped = t.strip(" ?")
    return stripped in ("weather", "wetter") or any(kw in t for kw in keywords)


def _extract_city(t: str) -> str | None:
    m = re.search(
        r"\b(?:in|für|for|at)\s+([A-Za-zäöüÄÖÜß][A-Za-zäöüÄÖÜß ]{0,28}?)"
        r"(?=\s*\??$|\s+(?:today|heute|jetzt|now|tomorrow|morgen)|\s*$)",
        t, re.I,
    )
    return m.group(1).strip().title() if m else None


def _safe_eval(expr: str) -> float | None:
    clean = (
        expr.replace('×', '*').replace('÷', '/').replace('^', '**')
            .replace(',', '.').strip()
    )
    if not re.fullmatch(r'[\d\s+\-*/.()%]+', clean):
        return None
    try:
        tree = ast.parse(clean, mode='eval')
    except SyntaxError:
        return None
    _allowed = {
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv,
        ast.UAdd, ast.USub,
    }
    for node in ast.walk(tree):
        if type(node) not in _allowed:
            return None
    _ops: dict = {
        ast.Add: _operator.add, ast.Sub: _operator.sub,
        ast.Mult: _operator.mul, ast.Div: _operator.truediv,
        ast.Pow: _operator.pow, ast.Mod: _operator.mod,
        ast.FloorDiv: _operator.floordiv,
        ast.UAdd: _operator.pos, ast.USub: _operator.neg,
    }
    def _ev(n: ast.expr) -> float:
        if isinstance(n, ast.Constant):
            return float(n.value)
        if isinstance(n, ast.BinOp):
            return _ops[type(n.op)](_ev(n.left), _ev(n.right))
        if isinstance(n, ast.UnaryOp):
            return _ops[type(n.op)](_ev(n.operand))
        raise ValueError("unsupported node")
    try:
        result = _ev(tree.body)
        if not (-1e15 < result < 1e15):
            return None
        return result
    except Exception:
        return None


_UNIT_CANONICAL: dict[str, str] = {
    'km': 'km', 'kilometer': 'km', 'kilometers': 'km', 'kilometre': 'km', 'kilometres': 'km',
    'mi': 'mi', 'mile': 'mi', 'miles': 'mi',
    'm': 'm', 'meter': 'm', 'meters': 'm', 'metre': 'm', 'metres': 'm',
    'cm': 'cm', 'centimeter': 'cm', 'centimeters': 'cm', 'centimetre': 'cm', 'centimetres': 'cm',
    'ft': 'ft', 'foot': 'ft', 'feet': 'ft',
    'in': 'in', 'inch': 'in', 'inches': 'in',
    'kg': 'kg', 'kilogram': 'kg', 'kilograms': 'kg',
    'lb': 'lb', 'lbs': 'lb', 'pound': 'lb', 'pounds': 'lb',
    'g': 'g', 'gram': 'g', 'grams': 'g',
    'l': 'l', 'liter': 'l', 'liters': 'l', 'litre': 'l', 'litres': 'l',
    'ml': 'ml', 'milliliter': 'ml', 'milliliters': 'ml',
    'gal': 'gal', 'gallon': 'gal', 'gallons': 'gal',
    'c': 'c', 'celsius': 'c',
    'f': 'f', 'fahrenheit': 'f',
    'k': 'k', 'kelvin': 'k',
}
_UNIT_DISPLAY: dict[str, str] = {
    'km': 'km', 'mi': 'miles', 'm': 'm', 'cm': 'cm', 'ft': 'ft', 'in': 'in',
    'kg': 'kg', 'lb': 'lbs', 'g': 'g',
    'l': 'L', 'ml': 'mL', 'gal': 'gal',
    'c': '°C', 'f': '°F', 'k': 'K',
}
_DIST_M: dict[str, float] = {'km': 1000, 'm': 1, 'cm': 0.01, 'ft': 0.3048, 'in': 0.0254, 'mi': 1609.344}
_MASS_KG: dict[str, float] = {'kg': 1, 'lb': 0.453592, 'g': 0.001}
_VOL_L: dict[str, float] = {'l': 1, 'ml': 0.001, 'gal': 3.78541}


def _do_convert(value: float, from_raw: str, to_raw: str) -> tuple[float, str] | None:
    fu = _UNIT_CANONICAL.get(from_raw.lower().lstrip('°'))
    tu = _UNIT_CANONICAL.get(to_raw.lower().lstrip('°'))
    if not fu or not tu or fu == tu:
        return None
    if fu == 'c' and tu == 'f': return (value * 9 / 5 + 32, '°F')
    if fu == 'f' and tu == 'c': return ((value - 32) * 5 / 9, '°C')
    if fu == 'c' and tu == 'k': return (value + 273.15, 'K')
    if fu == 'k' and tu == 'c': return (value - 273.15, '°C')
    if fu == 'f' and tu == 'k': return ((value - 32) * 5 / 9 + 273.15, 'K')
    if fu == 'k' and tu == 'f': return ((value - 273.15) * 9 / 5 + 32, '°F')
    for table in (_DIST_M, _MASS_KG, _VOL_L):
        if fu in table and tu in table:
            result = value * table[fu] / table[tu]
            return (result, _UNIT_DISPLAY.get(tu, tu))
    return None


_CITY_TZ: dict[str, str] = {
    "tokyo": "Asia/Tokyo", "japan": "Asia/Tokyo",
    "beijing": "Asia/Shanghai", "shanghai": "Asia/Shanghai", "china": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong",
    "singapore": "Asia/Singapore",
    "sydney": "Australia/Sydney", "melbourne": "Australia/Melbourne",
    "dubai": "Asia/Dubai", "uae": "Asia/Dubai",
    "mumbai": "Asia/Kolkata", "india": "Asia/Kolkata", "delhi": "Asia/Kolkata",
    "moscow": "Europe/Moscow", "russia": "Europe/Moscow",
    "paris": "Europe/Paris", "france": "Europe/Paris",
    "berlin": "Europe/Berlin", "germany": "Europe/Berlin",
    "london": "Europe/London", "uk": "Europe/London", "england": "Europe/London",
    "madrid": "Europe/Madrid", "spain": "Europe/Madrid",
    "rome": "Europe/Rome", "italy": "Europe/Rome",
    "amsterdam": "Europe/Amsterdam",
    "zurich": "Europe/Zurich", "switzerland": "Europe/Zurich",
    "vienna": "Europe/Vienna", "austria": "Europe/Vienna",
    "stockholm": "Europe/Stockholm", "sweden": "Europe/Stockholm",
    "oslo": "Europe/Oslo", "norway": "Europe/Oslo",
    "new york": "America/New_York", "nyc": "America/New_York",
    "boston": "America/New_York",
    "miami": "America/New_York",
    "chicago": "America/Chicago",
    "dallas": "America/Chicago", "houston": "America/Chicago",
    "denver": "America/Denver",
    "los angeles": "America/Los_Angeles", "la": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "toronto": "America/Toronto", "canada": "America/Toronto",
    "montreal": "America/Montreal",
    "vancouver": "America/Vancouver",
    "mexico city": "America/Mexico_City", "mexico": "America/Mexico_City",
    "sao paulo": "America/Sao_Paulo", "brazil": "America/Sao_Paulo",
    "buenos aires": "America/Argentina/Buenos_Aires",
    "cairo": "Africa/Cairo", "egypt": "Africa/Cairo",
    "johannesburg": "Africa/Johannesburg", "south africa": "Africa/Johannesburg",
    "nairobi": "Africa/Nairobi", "kenya": "Africa/Nairobi",
    "lagos": "Africa/Lagos", "nigeria": "Africa/Lagos",
    "utc": "UTC", "gmt": "UTC",
}


def _lookup_tz(city: str) -> ZoneInfo | None:
    key = city.strip().lower()
    tz_name = _CITY_TZ.get(key)
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            return None
    return None


_MONTH_MAP = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
    "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

_NAMED_EVENTS: dict[str, tuple[int, int]] = {
    "christmas":   (12, 25),
    "new year":    (1, 1),
    "new years":   (1, 1),
    "halloween":   (10, 31),
    "valentine":   (2, 14),
    "valentines":  (2, 14),
    "easter":      (4, 20),  # approximate
}


def _resolve_event_date(text: str, *, forward_only: bool = True) -> _date | None:
    t = re.sub(r"'s$|[!?.,;:]+$", '', text.strip().lower())
    for name, (m, d) in _NAMED_EVENTS.items():
        if name in t:
            today = _date.today()
            target = _date(today.year, m, d)
            if forward_only and target < today:
                target = _date(today.year + 1, m, d)
            return target
    iso_m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
    if iso_m:
        try:
            return _date(int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3)))
        except ValueError:
            return None
    for mon_name, mon_num in _MONTH_MAP.items():
        m1 = re.fullmatch(rf"(\d{{1,2}})\s+{mon_name}", t)
        m2 = re.fullmatch(rf"{mon_name}\s+(\d{{1,2}})", t)
        m3 = re.fullmatch(rf"{mon_name}\s+(\d{{1,2}}),?\s+(\d{{4}})", t)
        if m3:
            try:
                return _date(int(m3.group(2)), mon_num, int(m3.group(1)))
            except ValueError:
                pass
        for mobj in (m1, m2):
            if mobj:
                try:
                    today = _date.today()
                    d_val = _date(today.year, mon_num, int(mobj.group(1)))
                    if forward_only and d_val < today:
                        d_val = _date(today.year + 1, mon_num, int(mobj.group(1)))
                    return d_val
                except ValueError:
                    pass
    return None


def block_write_if_unauthorized(
    role: str,
    token: str | None,
    *,
    granted_permissions: list[str] | None,
    emergency_stop_enabled,
    permission_check,
) -> dict[str, object] | None:
    if emergency_stop_enabled():
        return {"reply": "Emergency stop active.", "data": {"error": "emergency_stop"}}
    if not token:
        return {"reply": "Token required.", "data": {"error": "missing_token"}}
    if not permission_check(role, token, granted_permissions):
        return {
            "reply": "Permission denied.",
            "data": {"error": "permission_denied", "permission": "actions.write.execute", "role": role},
        }
    return None


def try_skill(
    text: str,
    *,
    role: str,
    token: str | None,
    granted_permissions: list[str] | None,
    emergency_stop_enabled,
    permission_check,
    run_cmd,
    disk_usage,
    format_bytes,
    parse_meminfo,
    parse_ping,
    tail_lines,
    ensure_service_allowed,
    proxmox_vm_status,
    proxmox_lxc_status,
    proxmox_vm_action,
    proxmox_lxc_action,
    user_prefs: dict | None = None,
) -> dict[str, object] | None:
    t = text.strip().lower()

    if t in {"health", "status", "ping jarvis"}:
        return {"reply": "On it. Backend is healthy.", "data": {"ok": True}}

    # ── Morning / status briefing ─────────────────────────────────────────────
    if t in {"briefing", "morning briefing", "status briefing", "daily briefing",
             "give me a briefing", "give me a status report", "status report",
             "good morning", "good afternoon", "good evening", "what's the situation", "sitrep"}:
        now = datetime.now().astimezone()
        hour = now.hour
        if 5 <= hour < 12:
            salutation = "Good morning, sir."
        elif 12 <= hour < 17:
            salutation = "Good afternoon, sir."
        elif 17 <= hour < 22:
            salutation = "Good evening, sir."
        else:
            salutation = "Sir, working late again."
        time_str = now.strftime("%H:%M")
        date_str = now.strftime("%A, %d %B %Y")
        uptime_raw = run_cmd(["/usr/bin/uptime", "-p"], timeout=5).strip()
        load1, load5, _ = os.getloadavg()
        cores = os.cpu_count() or 1
        load_pct = load1 / cores * 100
        meminfo = parse_meminfo() or {}
        total_mem = meminfo.get("MemTotal", 0)
        avail_mem = meminfo.get("MemAvailable", 0)
        mem_pct = (total_mem - avail_mem) / total_mem * 100 if total_mem else 0
        usage = disk_usage("/")
        disk_pct = usage.used / usage.total * 100 if usage.total else 0
        notes_raw = (user_prefs or {}).get("notes", []) if user_prefs else []
        notes_count = len(notes_raw) if isinstance(notes_raw, list) else 0
        location = (user_prefs or {}).get("location", "") if user_prefs else ""
        lines = [
            f"It is {time_str} on {date_str}.",
            f"All systems nominal. Load {load1:.2f} ({load_pct:.0f}% of {cores} core(s)), "
            f"RAM {mem_pct:.0f}% used, disk {disk_pct:.0f}% used.",
            f"Uptime: {uptime_raw}.",
        ]
        if location:
            lines.append(f"Location set to {location}. Say 'weather' for a full forecast.")
        if notes_count:
            lines.append(f"You have {notes_count} note(s) on file.")
        reply = f"{salutation} " + " ".join(lines)
        return {
            "reply": reply,
            "data": {
                "route": "briefing",
                "salutation": salutation,
                "time": time_str,
                "date": date_str,
                "load1": load1,
                "load_pct": round(load_pct, 1),
                "mem_pct": round(mem_pct, 1),
                "disk_pct": round(disk_pct, 1),
                "uptime": uptime_raw,
                "notes_count": notes_count,
                "location": location,
            },
        }

    if t in {"uptime", "server uptime"}:
        out = run_cmd(["/usr/bin/uptime", "-p"])
        return {"reply": f"On it. {out}", "data": {"raw": out}}

    if t in {"disks", "all disks", "disk usage", "df -h", "disk space all", "all disk usage"}:
        out = run_cmd(["/bin/df", "-h", "-x", "tmpfs", "-x", "devtmpfs", "-x", "squashfs"], timeout=8)
        rows = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 6:
                # Standard df output: Filesystem Size Used Avail Use% Mount
                rows.append({"fs": parts[0], "size": parts[1], "used": parts[2], "avail": parts[3], "pct": parts[4], "mount": parts[5]})
        if not rows:
            return {"reply": "On it. Could not read disk information.", "data": {"mounts": []}}
        lines = [f"  {r['mount']}: {r['used']}/{r['size']} ({r['pct']} used, {r['avail']} free)" for r in rows]
        return {"reply": "On it. Disk usage:\n" + "\n".join(lines), "data": {"mounts": rows}}

    if t in {"disk", "df"}:
        usage = disk_usage("/")
        used_pct = usage.used / usage.total * 100 if usage.total else 0
        reply = (
            f"On it. Disk /: {used_pct:.0f}% used "
            f"({format_bytes(usage.used)}/{format_bytes(usage.total)})."
        )
        return {
            "reply": reply,
            "data": {
                "path": "/",
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
            },
        }

    if t in {"memory", "ram"}:
        info = parse_meminfo()
        if info and "MemTotal" in info and "MemAvailable" in info:
            total = info["MemTotal"]
            avail = info["MemAvailable"]
            used = total - avail
            used_pct = used / total * 100 if total else 0
            reply = (
                f"On it. Memory: {format_bytes(avail)} free / "
                f"{format_bytes(total)} total ({used_pct:.0f}% used)."
            )
            return {"reply": reply, "data": {"total_bytes": total, "available_bytes": avail, "used_bytes": used}}
        out = run_cmd(["/usr/bin/free", "-h"])
        return {"reply": "On it. Memory details ready.", "data": {"raw": out}}

    if t in {"docker", "docker ps"}:
        out = run_cmd(
            ["/usr/bin/sudo", "/usr/bin/docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
            timeout=12,
        )
        rows = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                rows.append({"name": parts[0], "status": parts[1], "image": parts[2]})
        if not rows:
            reply = "On it. No containers running."
        else:
            summary = ", ".join([f"{row['name']} ({row['status']})" for row in rows[:3]])
            reply = f"On it. {len(rows)} container(s) running."
            if summary:
                reply = f"{reply} {summary}"
        return {"reply": reply, "data": {"containers": rows}}

    if t.startswith("pve vm status "):
        parts = t.split()
        if len(parts) != 6:
            raise HTTPException(400, "Usage: pve vm status <host_id> <node> <vmid>")
        host_id, node, vmid = parts[3], parts[4], parts[5]
        data = proxmox_vm_status(host_id, node, vmid).get("data", {})
        status = data.get("status") or "unknown"
        return {"reply": f"On it. Proxmox VM {vmid} on {node} is {status}.", "data": data}

    if t.startswith("pve lxc status "):
        parts = t.split()
        if len(parts) != 6:
            raise HTTPException(400, "Usage: pve lxc status <host_id> <node> <vmid>")
        host_id, node, vmid = parts[3], parts[4], parts[5]
        data = proxmox_lxc_status(host_id, node, vmid).get("data", {})
        status = data.get("status") or "unknown"
        return {"reply": f"On it. Proxmox LXC {vmid} on {node} is {status}.", "data": data}

    proxmox_action_match = re.fullmatch(r"pve\s+(start|stop)\s+(vm|lxc)\s+(\S+)\s+(\S+)\s+(\S+)", t)
    if proxmox_action_match:
        blocked = block_write_if_unauthorized(
            role,
            token,
            granted_permissions=granted_permissions,
            emergency_stop_enabled=emergency_stop_enabled,
            permission_check=permission_check,
        )
        if blocked is not None:
            return blocked

        action, resource, host_id, node, vmid = proxmox_action_match.groups()
        if resource == "vm":
            result = proxmox_vm_action(host_id, node, vmid, action)
        else:
            result = proxmox_lxc_action(host_id, node, vmid, action)
        task_id = (result.get("data") if isinstance(result, dict) else None) or ""
        reply = f"On it. Proxmox {resource.upper()} {vmid} on {node} queued for {action}."
        data = {
            "provider": "proxmox",
            "resource": resource,
            "action": action,
            "host_id": host_id,
            "node": node,
            "vmid": vmid,
            "task_id": task_id,
        }
        return {"reply": reply, "data": data}

    if t.startswith("status "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        active = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        enabled = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-enabled", service], timeout=8)
        out = run_cmd(
            ["/usr/bin/sudo", "/bin/systemctl", "status", service, "--no-pager", "-n", "10"],
            timeout=12,
        )
        return {
            "reply": f"On it. {service} is {active} ({enabled}).",
            "data": {"service": service, "active": active, "enabled": enabled, "raw": out},
        }

    if t.startswith("logs "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        out = run_cmd(
            ["/usr/bin/sudo", "/bin/journalctl", "-u", service, "-n", "60", "--no-pager"],
            timeout=12,
        )
        snippet = tail_lines(out, max_lines=6)
        return {
            "reply": f"On it. Latest {service} logs (last 6 lines):\n{snippet or '(no log lines)'}",
            "data": {"service": service, "raw": out},
        }

    if t.startswith("ping "):
        host = t.split(" ", 1)[1].strip()
        if not re.fullmatch(r"[a-zA-Z0-9.\-]+", host):
            raise HTTPException(400, "Invalid host")
        out = run_cmd(["/usr/bin/sudo", "/bin/ping", "-c", "2", host], timeout=8)
        metrics = parse_ping(out)
        loss = metrics.get("packet_loss", "unknown loss")
        avg = metrics.get("rtt_avg_ms")
        reply = f"On it. Ping {host}: {loss}"
        if avg:
            reply = f"{reply}, avg {avg} ms."
        return {"reply": reply, "data": {"host": host, "raw": out, **metrics}}

    if t in {"system status", "system_status", "system health"}:
        usage = disk_usage("/")
        meminfo = parse_meminfo() or {}
        total = meminfo.get("MemTotal", 0)
        avail = meminfo.get("MemAvailable", 0)
        used_pct = (total - avail) / total * 100 if total else 0
        load1, load5, load15 = os.getloadavg()
        cores = os.cpu_count() or 0
        return {
            "reply": (
                "On it. "
                f"Load {load1:.2f} ({cores} cores), "
                f"Memory {used_pct:.0f}% used, "
                f"Disk / {usage.used / usage.total * 100:.0f}% used."
            ),
            "data": {
                "load": {"1m": load1, "5m": load5, "15m": load15},
                "cpu_cores": cores,
                "memory": {"total_bytes": total, "available_bytes": avail},
                "disk": {
                    "path": "/",
                    "total_bytes": usage.total,
                    "used_bytes": usage.used,
                    "free_bytes": usage.free,
                },
                "platform": platform.platform(),
            },
        }

    if t in {"time", "date", "time and date", "what time is it", "what day is it", "what's today", "today"}:
        now = datetime.now().astimezone()
        time_str = now.strftime("%H:%M")
        date_str = now.strftime("%A, %d %B %Y")
        return {"reply": f"On it. It is {time_str} on {date_str}.", "data": {"iso": now.isoformat()}}

    if t in {"hostname", "host info", "host"}:
        hostname = platform.node()
        return {"reply": f"On it. Hostname: {hostname}.", "data": {"hostname": hostname}}

    if t in {"kernel", "kernel version", "uname", "uname -r"}:
        k = run_cmd(["/bin/uname", "-r"], timeout=5).strip()
        full = run_cmd(["/bin/uname", "-a"], timeout=5).strip()
        return {"reply": f"On it. Kernel: {k}.", "data": {"kernel": k, "uname_full": full}}

    if t in {"who", "who is logged in", "logged in users", "current users", "active users", "w"}:
        out = run_cmd(["/usr/bin/who"], timeout=6)
        lines = [l for l in out.splitlines() if l.strip()]
        if not lines:
            return {"reply": "On it. No users currently logged in.", "data": {"users": []}}
        users = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                users.append({"user": parts[0], "tty": parts[1], "from": parts[4] if len(parts) > 4 else ""})
        summary = ", ".join(u["user"] for u in users)
        return {
            "reply": f"On it. {len(users)} user(s) logged in: {summary}.",
            "data": {"users": users, "raw": out},
        }

    if t in {"last", "last logins", "recent logins", "who logged in", "login history"}:
        out = run_cmd(["/usr/bin/last", "-n", "10", "-F"], timeout=8)
        lines = [l for l in out.splitlines() if l.strip() and not l.startswith("wtmp")]
        if not lines:
            return {"reply": "On it. No recent login history available.", "data": {"logins": []}}
        recent = lines[:5]
        return {
            "reply": f"On it. Last {len(recent)} login(s):\n" + "\n".join(f"  {l[:60]}" for l in recent),
            "data": {"logins": lines},
        }

    if t in {"sysinfo", "system info", "system information", "about this system", "about system", "os info"}:
        hostname = platform.node()
        os_info = platform.platform()
        cpu_count = os.cpu_count() or 0
        load1, load5, load15 = os.getloadavg()
        uptime_out = run_cmd(["/usr/bin/uptime", "-p"], timeout=5).strip()
        meminfo = parse_meminfo() or {}
        total_mem = meminfo.get("MemTotal", 0)
        avail_mem = meminfo.get("MemAvailable", 0)
        usage = disk_usage("/")
        reply = (
            f"On it. {hostname} — {os_info}. "
            f"{cpu_count} cores, load {load1:.2f}. "
            f"RAM {format_bytes(total_mem)} total, {format_bytes(avail_mem)} free. "
            f"Disk / {format_bytes(usage.total)} total. "
            f"Uptime: {uptime_out}."
        )
        return {
            "reply": reply,
            "data": {
                "hostname": hostname,
                "os": os_info,
                "cpu_cores": cpu_count,
                "load": {"1m": load1, "5m": load5, "15m": load15},
                "ram_total": total_mem,
                "ram_available": avail_mem,
                "disk_total": usage.total,
                "uptime": uptime_out,
            },
        }

    if t in {"load", "load average", "loadavg", "server load"}:
        load1, load5, load15 = os.getloadavg()
        cores = os.cpu_count() or 1
        pct = load1 / cores * 100
        return {
            "reply": f"On it. Load average: {load1:.2f} (1m) / {load5:.2f} (5m) / {load15:.2f} (15m) — {pct:.0f}% utilization on {cores} core(s).",
            "data": {"load1": load1, "load5": load5, "load15": load15, "cores": cores, "pct": pct},
        }

    if t in {"cpu", "cpu usage", "cpu load", "processor"}:
        load1, load5, load15 = os.getloadavg()
        cores = os.cpu_count() or 0
        pct = load1 / cores * 100 if cores else 0
        return {
            "reply": f"On it. CPU load: {load1:.2f} (1m) / {load5:.2f} (5m) / {load15:.2f} (15m) — {pct:.0f}% of {cores} cores.",
            "data": {"load1": load1, "load5": load5, "load15": load15, "cores": cores},
        }

    if t in {"processes", "top", "top processes", "ps"}:
        out = run_cmd(["/usr/bin/ps", "aux", "--sort=-%cpu"], timeout=8)
        lines = out.strip().splitlines()
        header = lines[0] if lines else ""
        rows = []
        for line in lines[1:11]:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                rows.append({"pid": parts[1], "cpu": parts[2], "mem": parts[3], "cmd": parts[10][:40]})
        top3 = ", ".join(f"{r['cmd'].split()[-1]} ({r['cpu']}%)" for r in rows[:3]) if rows else "none"
        return {
            "reply": f"On it. Top processes: {top3}",
            "data": {"processes": rows, "header": header},
        }

    if t in {"ports", "open ports", "listening ports", "network connections", "connections", "netstat", "ss"}:
        out = run_cmd(["/bin/ss", "-tuln"], timeout=8)
        rows = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                proto  = parts[0]
                state  = parts[1]
                local  = parts[4]
                rows.append({"proto": proto, "state": state, "local": local})
        listening = [r for r in rows if r["state"] in ("LISTEN", "UNCONN")]
        if not rows:
            return {"reply": "On it. No open ports found.", "data": {"ports": [], "listening": []}}
        summary = ", ".join(r["local"].rsplit(":", 1)[-1] for r in listening[:8]) if listening else "none"
        return {
            "reply": f"On it. {len(listening)} listening port(s): {summary}",
            "data": {"ports": rows, "listening": listening},
        }

    if t in {"ip", "ip address", "my ip", "network", "ifconfig", "ip addr", "network info"}:
        out = run_cmd(["/sbin/ip", "-4", "addr", "show", "scope", "global"], timeout=6)
        ips = re.findall(r"inet\s+([\d.]+/\d+)", out)
        if ips:
            return {"reply": f"On it. IP addresses: {', '.join(ips)}.", "data": {"addresses": ips}}
        return {"reply": "On it. Could not determine IP address.", "data": {"addresses": []}}

    if t in {"whoami", "who am i", "my account", "my user", "current user"}:
        name = (user_prefs.get("display_name") or "").strip() if user_prefs else ""
        loc  = (user_prefs.get("location") or "").strip() if user_prefs else ""
        note_count = len(user_prefs.get("notes") or []) if user_prefs else 0
        parts = []
        if name: parts.append(f"name: {name}")
        if loc:  parts.append(f"location: {loc}")
        if note_count: parts.append(f"{note_count} saved note(s)")
        detail = " — " + ", ".join(parts) if parts else ""
        return {
            "reply": f"On it. You're the authenticated user{detail}.",
            "data": {"display_name": name, "location": loc, "note_count": note_count},
        }

    if t in {"help", "skills", "skills overview", "what can you do", "was kannst du", "was kannst du tun"}:
        overview = [
            "weather / wetter [in <city>] — current weather + 3-day forecast",
            "weather forecast / vorhersage — multi-day view",
            "I'm in <city> — save location for weather",
            "calculate <expr> — e.g. 'calculate 15 * 7' or 'was ist 100 / 4'",
            "convert <N> <unit> to <unit> — e.g. '100 km to miles', '30 C to F'",
            "days until <event/date> — e.g. 'days until Christmas'",
            "days since <date>",
            "what day is <N> days/weeks from now",
            "time in <city> — e.g. 'time in Tokyo'",
            "timer for <N> minutes/seconds/hours",
            "remind me in <N> minutes to <task>",
            "disks — disk usage for all mount points",
            "ports / open ports — listening network ports",
            "kernel — kernel version",
            "who — currently logged-in users",
            "last — recent login history",
            "load / load average — system load",
            "remember that <text> — save a note",
            "what do you remember — list saved notes",
            "forget <keyword> — delete matching notes",
            "health / status / ping jarvis",
            "uptime",
            "disk",
            "memory / ram",
            "cpu / cpu load",
            "processes / top",
            "ip / ip address",
            "docker",
            "status <service>",
            "logs <service>",
            "ping <host>",
            "system status",
            "sysinfo — hostname, OS, CPU, RAM, disk, uptime",
            "time / date",
            "hostname",
            "pve vm|lxc status <host> <node> <id>",
            "pve start|stop vm|lxc <host> <node> <id>",
            "restart|start|stop <service>",
            "uuid — generate a UUID v4",
            "timestamp — current Unix timestamp",
            "dns <host> — resolve hostname to IP",
            "is <N> prime — prime number check",
            "factorial <N> — N! (up to 20)",
            "fibonacci <N> — first N Fibonacci numbers",
            "hex to rgb #rrggbb — color conversion",
            "rgb to hex <r> <g> <b> — color to hex",
            "word count <text> — count words & chars",
            "base64 encode/decode <text>",
            "sha256 / md5 <text> — hash a string",
            "hex/bin/oct <number> — base conversion",
            "generate password [<length>] — secure random password",
            "url encode/decode <text>",
            "flip a coin — heads or tails",
            "roll [N]d[S] — dice roller, e.g. 'roll 2d6'",
            "ascii <char|code> — ASCII character lookup",
            "to roman <N> / roman <ROMAN> — Roman numeral conversion",
            "morse <text> — encode to Morse code",
            "morse decode <...> — decode from Morse code",
            "sort <n1> <n2> ... — sort a list of numbers",
            "average <n1> <n2> ... — mean of numbers",
            "min/max <n1> <n2> ... — find min or max",
            "briefing / morning briefing — full status report",
            "http status <url> — HTTP response code check",
            "ssl <domain> — SSL certificate expiry check",
            "reboot — schedule system reboot (admin)",
            "shutdown [in <N> min] — system shutdown (admin)",
            "cancel shutdown — abort a pending shutdown",
        ]
        return {"reply": "On it. Available skills:\n" + "\n".join(f"• {s}" for s in overview), "data": {"skills": overview}}

    if t.startswith("restart ") and not re.match(
        r"restart\s+(?:the\s+)?(?:system|server|machine|host)\b", t, re.I
    ):
        blocked = block_write_if_unauthorized(
            role,
            token,
            granted_permissions=granted_permissions,
            emergency_stop_enabled=emergency_stop_enabled,
            permission_check=permission_check,
        )
        if blocked is not None:
            return blocked
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "restart", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return {"reply": f"On it. {service} restarted ({st}).", "data": {"service": service, "active": st}}

    if t.startswith("start "):
        blocked = block_write_if_unauthorized(
            role,
            token,
            granted_permissions=granted_permissions,
            emergency_stop_enabled=emergency_stop_enabled,
            permission_check=permission_check,
        )
        if blocked is not None:
            return blocked
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "start", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return {"reply": f"On it. {service} started ({st}).", "data": {"service": service, "active": st}}

    if t.startswith("stop "):
        blocked = block_write_if_unauthorized(
            role,
            token,
            granted_permissions=granted_permissions,
            emergency_stop_enabled=emergency_stop_enabled,
            permission_check=permission_check,
        )
        if blocked is not None:
            return blocked
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "stop", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return {"reply": f"On it. {service} stopped ({st}).", "data": {"service": service, "active": st}}

    # ── System shutdown / reboot ──────────────────────────────────────────────
    _shutdown_m = re.match(r"(?:shutdown|shut\s+down|poweroff|power\s+off)(?:\s+in\s+(\d+)\s*(?:min(?:utes?)?|m))?", t, re.I)
    _reboot_m = re.match(r"(?:reboot|restart\s+(?:the\s+)?(?:system|server|machine|host)|system\s+reboot)", t, re.I)
    if _shutdown_m or _reboot_m:
        blocked = block_write_if_unauthorized(
            role, token,
            granted_permissions=granted_permissions,
            emergency_stop_enabled=emergency_stop_enabled,
            permission_check=permission_check,
        )
        if blocked is not None:
            return blocked
        if _reboot_m:
            run_cmd(["/usr/bin/sudo", "/sbin/shutdown", "-r", "+1"], timeout=10)
            return {"reply": f"{_ack()} System reboot scheduled in 1 minute.", "data": {"route": "system_control", "action": "reboot", "delay_min": 1}}
        delay = int(_shutdown_m.group(1) or 1)
        delay = max(1, min(60, delay))
        run_cmd(["/usr/bin/sudo", "/sbin/shutdown", "-h", f"+{delay}"], timeout=10)
        return {"reply": f"{_ack()} System shutdown in {delay} minute(s).", "data": {"route": "system_control", "action": "shutdown", "delay_min": delay}}

    _cancel_shutdown_m = re.match(r"(?:cancel\s+(?:shutdown|reboot)|abort\s+(?:shutdown|reboot))", t, re.I)
    if _cancel_shutdown_m:
        blocked = block_write_if_unauthorized(
            role, token,
            granted_permissions=granted_permissions,
            emergency_stop_enabled=emergency_stop_enabled,
            permission_check=permission_check,
        )
        if blocked is not None:
            return blocked
        run_cmd(["/usr/bin/sudo", "/sbin/shutdown", "-c"], timeout=10)
        return {"reply": f"{_ack()} Shutdown/reboot cancelled.", "data": {"route": "system_control", "action": "cancel"}}

    # ── JARVIS identity ───────────────────────────────────────────────────────
    if re.search(r"\b(who are you|what are you|tell me about yourself|wer bist du|was bist du)\b", t):
        return {
            "reply": (
                "I'm J.A.R.V.I.S. — Just A Rather Very Intelligent System. "
                "AI backbone of this private smart home and infrastructure network. "
                "I handle home automation, server infrastructure, knowledge queries, and system controls. "
                "Say 'skills' for a full list of what I can do without an AI model."
            ),
            "data": {"route": "identity"},
        }

    # ── Natural language: system queries ─────────────────────────────────────
    if re.search(r"\b(server uptime|how long.*running|how long.*up|wie lange.*läuft)\b", t):
        out = run_cmd(["/usr/bin/uptime", "-p"], timeout=8)
        return {"reply": f"On it. {out}", "data": {"raw": out}}

    if re.search(r"\b(open ports?|listening ports?|what ports?|network connections?|what is listening)\b", t):
        out = run_cmd(["/bin/ss", "-tuln"], timeout=8)
        rows = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                rows.append({"proto": parts[0], "state": parts[1], "local": parts[4]})
        listening = [r for r in rows if r["state"] in ("LISTEN", "UNCONN")]
        summary = ", ".join(r["local"].rsplit(":", 1)[-1] for r in listening[:8]) if listening else "none"
        return {"reply": f"On it. {len(listening)} listening port(s): {summary}", "data": {"ports": rows, "listening": listening}}

    if re.search(r"\b(docker container|what containers|running containers|list container|zeige container)\b", t):
        out = run_cmd(
            ["/usr/bin/sudo", "/usr/bin/docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
            timeout=12,
        )
        rows = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                rows.append({"name": parts[0], "status": parts[1], "image": parts[2]})
        top = ", ".join(r["name"] for r in rows[:5]) if rows else "none"
        return {"reply": f"On it. {len(rows)} container(s): {top}.", "data": {"containers": rows}}

    if re.search(r"\b(system health|overall status|how is the system|gesamtstatus)\b", t):
        usage = disk_usage("/")
        meminfo = parse_meminfo() or {}
        total = meminfo.get("MemTotal", 0)
        avail = meminfo.get("MemAvailable", 0)
        used_pct = (total - avail) / total * 100 if total else 0
        load1, _, _ = os.getloadavg()
        cores = os.cpu_count() or 1
        return {
            "reply": (
                f"On it. System health: CPU {load1 / cores * 100:.0f}%, "
                f"RAM {used_pct:.0f}% used, "
                f"Disk {usage.used / usage.total * 100:.0f}% used."
            ),
            "data": {"load1": load1, "mem_pct": used_pct, "disk_pct": usage.used / usage.total * 100 if usage.total else 0},
        }

    logs_m = re.match(r"(?:show|tail|get|fetch|view|zeige?)\s+(?:logs?\s+for\s+|logs?\s+)(\w[\w.-]{1,30})", t, re.I)
    if logs_m:
        svc = logs_m.group(1).strip().lower()
        try:
            ensure_service_allowed(svc)
            out = run_cmd(["/usr/bin/sudo", "/bin/journalctl", "-u", svc, "-n", "60", "--no-pager"], timeout=12)
            snippet = tail_lines(out, max_lines=6)
            return {"reply": f"On it. Latest {svc} logs:\n{snippet or '(no log lines)'}", "data": {"service": svc, "raw": out}}
        except Exception:
            pass

    # ── Natural language: system resource queries ────────────────────────────
    if re.search(r"\b(how much (memory|ram|disk|space|cpu|load)|system (load|usage)|arbeitsspeicher|festplatte)\b", t):
        if re.search(r"\b(memory|ram|arbeitsspeicher)\b", t):
            info = parse_meminfo()
            if info and "MemTotal" in info and "MemAvailable" in info:
                total = info["MemTotal"]
                avail = info["MemAvailable"]
                used  = total - avail
                pct   = used / total * 100 if total else 0
                return {"reply": f"On it. Memory: {format_bytes(avail)} free of {format_bytes(total)} ({pct:.0f}% used).", "data": {"total_bytes": total, "available_bytes": avail}}
        if re.search(r"\b(disk|space|festplatte)\b", t):
            usage = disk_usage("/")
            pct = usage.used / usage.total * 100 if usage.total else 0
            return {"reply": f"On it. Disk /: {pct:.0f}% used ({format_bytes(usage.used)}/{format_bytes(usage.total)}).", "data": {"total": usage.total, "used": usage.used, "free": usage.free}}
        if re.search(r"\b(cpu|load|prozessor)\b", t):
            load1, load5, _ = os.getloadavg()
            cores = os.cpu_count() or 1
            pct = load1 / cores * 100
            return {"reply": f"On it. CPU load: {load1:.2f} ({pct:.0f}% of {cores} cores).", "data": {"load1": load1, "cores": cores}}

    # ── Date arithmetic ───────────────────────────────────────────────────────
    days_until_m = re.search(
        r"(?:how many\s+)?days\s+(?:until|till|to|before|bis)\s+(.+)"
        r"|(?:how long\s+)?(?:until|till|bis)\s+(.+)",
        t, re.I,
    )
    if days_until_m:
        event_text = (days_until_m.group(1) or days_until_m.group(2) or "").strip()
        target = _resolve_event_date(event_text)
        if target is not None:
            today = _date.today()
            delta = (target - today).days
            if delta == 0:
                reply = f"On it. {event_text.title()} is today!"
            elif delta == 1:
                reply = f"On it. {event_text.title()} is tomorrow."
            elif delta < 0:
                reply = f"On it. {event_text.title()} was {abs(delta)} day(s) ago."
            else:
                reply = f"On it. {delta} day(s) until {event_text.title()} ({target.strftime('%A, %d %B %Y')})."
            return {"reply": reply, "data": {"route": "date_calc", "target": str(target), "days": delta, "event": event_text}}

    days_since_m = re.search(r"(?:how many\s+)?days\s+since\s+(.+)", t, re.I)
    if days_since_m:
        event_text = days_since_m.group(1).strip()
        target = _resolve_event_date(event_text, forward_only=False)
        if target is not None:
            today = _date.today()
            delta = (today - target).days
            if delta == 0:
                reply = f"On it. {event_text.title()} is today."
            else:
                reply = f"On it. {abs(delta)} day(s) since {event_text.title()} ({target.strftime('%d %B %Y')})."
            return {"reply": reply, "data": {"route": "date_calc", "target": str(target), "days": delta, "event": event_text}}

    date_offset_m = re.match(
        r"what\s+(?:day|date)\s+is\s+(\d+)\s+(day|days|week|weeks)\s+(?:from\s+now|from\s+today|later|ahead)",
        t, re.I,
    )
    if date_offset_m:
        n = int(date_offset_m.group(1))
        unit = date_offset_m.group(2).lower()
        delta_days = n * 7 if "week" in unit else n
        target = _date.today() + timedelta(days=delta_days)
        return {
            "reply": f"On it. {n} {unit} from today is {target.strftime('%A, %d %B %Y')}.",
            "data": {"route": "date_calc", "target": str(target), "days_offset": delta_days},
        }

    # ── Calculator ───────────────────────────────────────────────────────────
    calc_match = re.match(
        r"(?:calculate|calc|compute|berechne?)\s*:?\s*(.+)"
        r"|(?:what(?:'s| is)|was ist)\s+(\d.*)",
        t, re.I,
    )
    if calc_match:
        raw_expr = (calc_match.group(1) or calc_match.group(2) or "").strip()
        expr = (
            raw_expr
            .replace(" mal ", "*").replace(" durch ", "/")
            .replace(" plus ", "+").replace(" minus ", "-")
            .replace(" times ", "*").replace(" divided by ", "/")
            .replace(" multiplied by ", "*").replace(" mod ", "%")
        )
        result = _safe_eval(expr)
        if result is not None:
            fmt = f"{result:g}" if result == int(result) and abs(result) < 1e12 else f"{result:.6g}"
            return {
                "reply": f"Understood. {raw_expr} = **{fmt}**",
                "data": {"route": "calc", "expression": raw_expr, "result": result},
            }

    # ── Unit conversion ───────────────────────────────────────────────────────
    conv_m = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(°?[a-zA-ZäöüÄÖÜ]+(?:\s+[a-zA-Z]+)?)"
        r"\s+(?:to|in|nach|zu|ins?)\s+"
        r"(°?[a-zA-ZäöüÄÖÜ]+(?:\s+[a-zA-Z]+)?)",
        t, re.I,
    )
    if conv_m:
        try:
            num = float(conv_m.group(1).replace(',', '.'))
            from_raw = conv_m.group(2).strip()
            to_raw   = conv_m.group(3).strip()
            converted = _do_convert(num, from_raw, to_raw)
            if converted is not None:
                res_val, res_unit = converted
                fmt_in  = f"{num:g}"
                fmt_out = f"{res_val:.4g}" if res_val != int(res_val) else str(int(round(res_val)))
                from_disp = _UNIT_DISPLAY.get(_UNIT_CANONICAL.get(from_raw.lower().lstrip('°'), ''), from_raw)
                return {
                    "reply": f"Understood. {fmt_in} {from_disp} = **{fmt_out} {res_unit}**",
                    "data": {
                        "route": "convert",
                        "from_value": num, "from_unit": from_raw,
                        "to_unit": to_raw, "result": res_val, "result_unit": res_unit,
                    },
                }
        except (ValueError, TypeError):
            pass

    # ── UUID / timestamp / DNS ────────────────────────────────────────────────
    if t in {"uuid", "generate uuid", "new uuid", "create uuid", "uuid4", "random uuid"}:
        uid = str(_uuid.uuid4())
        return {"reply": f"{_ack()} UUID: `{uid}`", "data": {"route": "uuid", "uuid": uid}}

    if t in {"timestamp", "unix timestamp", "unix time", "epoch", "current timestamp", "now timestamp", "unixtime"}:
        ts = int(_time.time())
        iso = datetime.now(tz=ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"reply": f"{_ack()} Current Unix timestamp: `{ts}` ({iso} UTC).", "data": {"route": "timestamp", "unix": ts, "iso": iso}}

    dns_m = re.match(r"(?:dns|resolve|lookup|nslookup|dig)\s+([a-zA-Z0-9._-]+)", t, re.I)
    if dns_m:
        host = dns_m.group(1).strip().lower()
        try:
            results = socket.getaddrinfo(host, None)
            ips = list(dict.fromkeys(r[4][0] for r in results))[:4]
            return {
                "reply": f"{_ack()} {host} resolves to: {', '.join(ips)}",
                "data": {"route": "dns", "host": host, "addresses": ips},
            }
        except socket.gaierror:
            return {"reply": f"{_ack()} Could not resolve {host}.", "data": {"route": "dns", "host": host, "addresses": [], "error": "nxdomain"}}

    # ── Developer utilities ───────────────────────────────────────────────────
    # Match against original `text` (not `t`) to preserve case for encode/decode payloads.
    b64_enc_m = re.match(r"base64\s+(?:encode|enc)\s+(.+)", text, re.I)
    if b64_enc_m:
        raw = b64_enc_m.group(1).strip()
        encoded = base64.b64encode(raw.encode()).decode()
        return {"reply": f"{_ack()} Base64: `{encoded}`", "data": {"route": "base64", "op": "encode", "result": encoded}}

    b64_dec_m = re.match(r"base64\s+(?:decode|dec)\s+(\S+)", text, re.I)
    if b64_dec_m:
        raw = b64_dec_m.group(1).strip()
        try:
            decoded = base64.b64decode(raw).decode()
            return {"reply": f"{_ack()} Decoded: `{decoded}`", "data": {"route": "base64", "op": "decode", "result": decoded}}
        except Exception:
            return {"reply": f"{_ack()} Invalid base64 input.", "data": {"route": "base64", "op": "decode", "error": "invalid"}}

    hash_m = re.match(r"(?:sha256|sha|md5|hash|checksum)\s+(.+)", text, re.I)
    if hash_m:
        prefix = text.split()[0].lower()
        raw = hash_m.group(1).strip()
        algo = "md5" if prefix == "md5" else "sha256"
        digest = hashlib.new(algo, raw.encode()).hexdigest()
        display = raw[:30] + "…" if len(raw) > 30 else raw
        return {"reply": f"{_ack()} {algo.upper()}(`{display}`) = `{digest}`", "data": {"route": "hash", "algo": algo, "result": digest}}

    url_enc_m = re.match(r"url\s+(?:encode|enc)\s+(.+)", text, re.I)
    if url_enc_m:
        raw = url_enc_m.group(1).strip()
        encoded = urllib.parse.quote(raw, safe='')
        return {"reply": f"{_ack()} URL encoded: `{encoded}`", "data": {"route": "url", "op": "encode", "result": encoded}}

    url_dec_m = re.match(r"url\s+(?:decode|dec)\s+(.+)", text, re.I)
    if url_dec_m:
        raw = url_dec_m.group(1).strip()
        decoded = urllib.parse.unquote(raw)
        return {"reply": f"{_ack()} URL decoded: `{decoded}`", "data": {"route": "url", "op": "decode", "result": decoded}}

    num_base_m = re.match(r"(hex|bin|oct)\s+(\d+)$", t, re.I)
    if num_base_m:
        base_name = num_base_m.group(1).lower()
        n = int(num_base_m.group(2))
        if base_name == "hex":
            result = hex(n)
        elif base_name == "bin":
            result = bin(n)
        else:
            result = oct(n)
        return {"reply": f"{_ack()} {n} in {base_name}: `{result}`", "data": {"route": "base_convert", "base": base_name, "input": n, "result": result}}

    pw_m = re.match(r"(?:generate|random|gen|create)\s+(?:a\s+)?password(?:\s+(\d+))?", t, re.I)
    if pw_m:
        length = max(8, min(64, int(pw_m.group(1) or 20)))
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
        pw = ''.join(secrets.choice(alphabet) for _ in range(length))
        return {"reply": f"{_ack()} Generated password ({length} chars): `{pw}`", "data": {"route": "password", "length": length, "password": pw}}

    hex_rgb_m = re.match(r"(?:hex(?:\s+to)?\s+rgb|color)\s+#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", text, re.I)
    if hex_rgb_m:
        raw_hex = hex_rgb_m.group(1)
        if len(raw_hex) == 3:
            raw_hex = "".join(c * 2 for c in raw_hex)
        r_val, g_val, b_val = int(raw_hex[0:2], 16), int(raw_hex[2:4], 16), int(raw_hex[4:6], 16)
        return {"reply": f"{_ack()} #{raw_hex.upper()} → RGB({r_val}, {g_val}, {b_val})", "data": {"route": "color", "hex": f"#{raw_hex.upper()}", "r": r_val, "g": g_val, "b": b_val}}

    rgb_hex_m = re.match(r"(?:rgb(?:\s+to)?\s+hex|rgb)\s+(\d{1,3})[,\s]+(\d{1,3})[,\s]+(\d{1,3})", t, re.I)
    if rgb_hex_m:
        r_val, g_val, b_val = int(rgb_hex_m.group(1)), int(rgb_hex_m.group(2)), int(rgb_hex_m.group(3))
        if all(0 <= v <= 255 for v in (r_val, g_val, b_val)):
            hex_str = f"#{r_val:02X}{g_val:02X}{b_val:02X}"
            return {"reply": f"{_ack()} RGB({r_val}, {g_val}, {b_val}) → `{hex_str}`", "data": {"route": "color", "hex": hex_str, "r": r_val, "g": g_val, "b": b_val}}

    wc_m = re.match(r"(?:word\s+count|count\s+words?|wc)\s+(.+)", text, re.I)
    if wc_m:
        raw_text = wc_m.group(1).strip().strip('"\'')
        words = len(raw_text.split())
        chars = len(raw_text)
        chars_no_spaces = len(raw_text.replace(" ", ""))
        return {"reply": f"{_ack()} `{words}` word(s), `{chars}` char(s) ({chars_no_spaces} without spaces).", "data": {"route": "word_count", "words": words, "chars": chars, "chars_no_spaces": chars_no_spaces}}

    prime_m = re.match(r"(?:is\s+)?(\d+)\s+(?:prime|a\s+prime)(?:\s*\?)?$|(?:prime|is\s+prime)\s+(\d+)", t, re.I)
    if prime_m:
        n = int(prime_m.group(1) or prime_m.group(2))
        if n < 2:
            is_p = False
        elif n == 2:
            is_p = True
        elif n % 2 == 0:
            is_p = False
        else:
            is_p = all(n % i != 0 for i in range(3, int(n ** 0.5) + 1, 2))
        verdict = "prime" if is_p else "not prime"
        return {"reply": f"{_ack()} {n} is **{verdict}**.", "data": {"route": "prime", "n": n, "is_prime": is_p}}

    factorial_m = re.match(r"(?:factorial|fact)\s+(\d+)|(\d+)\s*!$", t, re.I)
    if factorial_m:
        n = int(factorial_m.group(1) or factorial_m.group(2))
        if n > 20:
            return {"reply": f"{_ack()} {n}! is too large to display inline.", "data": {"route": "factorial", "n": n, "error": "too_large"}}
        result = 1
        for i in range(2, n + 1):
            result *= i
        return {"reply": f"{_ack()} {n}! = **{result}**", "data": {"route": "factorial", "n": n, "result": result}}

    fib_m = re.match(r"(?:fibonacci|fib(?:onacci)?)\s+(\d+)$", t, re.I)
    if fib_m:
        n = min(int(fib_m.group(1)), 30)
        a, b, seq = 0, 1, [0]
        for _ in range(n - 1):
            a, b = b, a + b
            seq.append(a)
        display = ", ".join(str(x) for x in seq[:10])
        if len(seq) > 10:
            display += f", … (to F({n - 1})={seq[-1]})"
        return {"reply": f"{_ack()} Fibonacci({n}): {display}", "data": {"route": "fibonacci", "n": n, "sequence": seq}}

    # ── Coin flip / dice roll ─────────────────────────────────────────────────
    if re.match(r"(?:flip\s+(?:a\s+)?coin|coin\s+flip|heads\s+or\s+tails|toss\s+(?:a\s+)?coin)", t, re.I):
        result = secrets.choice(["Heads", "Tails"])
        return {"reply": f"{_ack()} {result}.", "data": {"route": "coin_flip", "result": result}}

    dice_m = re.match(r"(?:roll|throw|toss)\s+(?:a\s+)?(?:(\d+)[dD](\d+)|(?:dice|die|würfel)|(\d+)\s+dice|d(\d+))|(?:dice|roll dice)", t, re.I)
    if dice_m:
        count = int(dice_m.group(1) or dice_m.group(3) or 1)
        sides = int(dice_m.group(2) or dice_m.group(4) or 6)
        count = max(1, min(20, count))
        sides = max(2, min(100, sides))
        rolls = [secrets.randbelow(sides) + 1 for _ in range(count)]
        total = sum(rolls)
        rolls_str = ", ".join(str(r) for r in rolls)
        reply = f"On it. Rolled {count}d{sides}: [{rolls_str}] — total **{total}**." if count > 1 else f"On it. Rolled d{sides}: **{total}**."
        return {"reply": reply, "data": {"route": "dice", "count": count, "sides": sides, "rolls": rolls, "total": total}}

    # ── ASCII lookup ──────────────────────────────────────────────────────────
    ascii_m = re.match(r"(?:ascii|char(?:code)?)\s+(.+)", text, re.I)
    if ascii_m:
        raw = ascii_m.group(1).strip()
        if raw.lstrip("-").isdigit():
            code = int(raw)
            if 0 <= code <= 127:
                ch = chr(code)
                display = repr(ch) if code < 32 or code == 127 else f"'{ch}'"
                return {"reply": f"{_ack()} ASCII {code} = {display}", "data": {"route": "ascii", "code": code, "char": ch}}
            return {"reply": f"{_ack()} {code} is out of the ASCII range (0–127).", "data": {"route": "ascii", "error": "out_of_range"}}
        if len(raw) == 1:
            code = ord(raw)
            return {"reply": f"{_ack()} '{raw}' = ASCII {code} (hex 0x{code:02X})", "data": {"route": "ascii", "char": raw, "code": code}}
        return {"reply": f"{_ack()} ASCII lookup expects a single character or decimal code.", "data": {"route": "ascii", "error": "invalid_input"}}

    # ── Roman numerals ────────────────────────────────────────────────────────
    roman_to_int_m = re.match(r"(?:roman|roman\s+to\s+(?:int|number|decimal))\s+([IVXLCDM]+)$", text, re.I)
    int_to_roman_m = re.match(r"(?:to\s+roman|int(?:eger)?\s+to\s+roman|roman(?:\s+numeral)?)\s+(\d+)$", t, re.I)
    if roman_to_int_m:
        s = roman_to_int_m.group(1).upper()
        _roman_vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
        result_r = 0
        prev = 0
        for ch in reversed(s):
            v = _roman_vals.get(ch, 0)
            result_r = result_r - v if v < prev else result_r + v
            prev = v
        return {"reply": f"{_ack()} {s} = **{result_r}**", "data": {"route": "roman", "op": "to_int", "roman": s, "value": result_r}}
    if int_to_roman_m:
        n_r = int(int_to_roman_m.group(1))
        if not (1 <= n_r <= 3999):
            return {"reply": f"{_ack()} Roman numerals cover 1–3999 only.", "data": {"route": "roman", "error": "out_of_range"}}
        _roman_table = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),
                        (50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
        roman_str, tmp = "", n_r
        for val, sym in _roman_table:
            while tmp >= val:
                roman_str += sym; tmp -= val
        return {"reply": f"{_ack()} {n_r} in Roman numerals = **{roman_str}**", "data": {"route": "roman", "op": "to_roman", "value": n_r, "roman": roman_str}}

    # ── Morse code ────────────────────────────────────────────────────────────
    _MORSE = {
        "A":".-","B":"-...","C":"-.-.","D":"-..","E":".","F":"..-.","G":"--.","H":"....","I":"..","J":".---",
        "K":"-.-","L":".-..","M":"--","N":"-.","O":"---","P":".--.","Q":"--.-","R":".-.","S":"...","T":"-",
        "U":"..-","V":"...-","W":".--","X":"-..-","Y":"-.--","Z":"--..",
        "0":"-----","1":".----","2":"..---","3":"...--","4":"....-","5":".....","6":"-....","7":"--...","8":"---..","9":"----.",
    }
    _MORSE_REV = {v: k for k, v in _MORSE.items()}
    morse_enc_m = re.match(r"morse\s+(?:encode|enc|to\s+morse)?\s*(.+)", text, re.I)
    morse_dec_m = re.match(r"(?:morse\s+(?:decode|dec|from\s+morse)|unmorse|decode\s+morse)\s+([.\-/ ]+)", text, re.I)
    if morse_dec_m:
        raw_morse = morse_dec_m.group(1).strip()
        words_m = raw_morse.split(" / ")
        decoded_parts = []
        for word in words_m:
            chars_m = word.strip().split()
            decoded_parts.append("".join(_MORSE_REV.get(c, "?") for c in chars_m))
        decoded = " ".join(decoded_parts)
        return {"reply": f"{_ack()} Morse decoded: **{decoded}**", "data": {"route": "morse", "op": "decode", "result": decoded}}
    if morse_enc_m:
        payload = morse_enc_m.group(1).strip().upper()
        if not re.match(r"^[A-Z0-9 ]+$", payload):
            return {"reply": f"{_ack()} Morse encoding supports A–Z and 0–9 only.", "data": {"route": "morse", "error": "unsupported_chars"}}
        parts = []
        for word in payload.split():
            parts.append(" ".join(_MORSE.get(c, "?") for c in word))
        encoded = " / ".join(parts)
        return {"reply": f"{_ack()} Morse: `{encoded}`", "data": {"route": "morse", "op": "encode", "result": encoded}}

    # ── HTTP health check ─────────────────────────────────────────────────────
    http_m = re.match(
        r"(?:http\s+(?:status|check|ping|get)|check\s+(?:url|http|site|endpoint))\s+(https?://\S+)",
        text, re.I,
    )
    if http_m:
        url = http_m.group(1).strip().rstrip("/")
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        try:
            ctx = _ssl.create_default_context() if parsed.scheme == "https" else None
            conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
            conn = conn_cls(host, port, timeout=8, context=ctx) if ctx else conn_cls(host, port, timeout=8)
            conn.request("HEAD", path, headers={"User-Agent": "JARVIS/1.0"})
            resp = conn.getresponse()
            code = resp.status
            conn.close()
            ok = 200 <= code < 400
            status_word = "OK" if ok else "DOWN"
            return {
                "reply": f"{_ack()} {url} returned **{code}** — {status_word}.",
                "data": {"route": "http_check", "url": url, "status_code": code, "ok": ok},
            }
        except Exception as e:
            return {
                "reply": f"{_ack()} Could not reach {url}: {type(e).__name__}.",
                "data": {"route": "http_check", "url": url, "ok": False, "error": type(e).__name__},
            }

    # ── SSL certificate check ─────────────────────────────────────────────────
    ssl_m = re.match(
        r"(?:ssl|tls|cert(?:ificate)?)\s+(?:check\s+|status\s+|expiry\s+|expire[sd]?\s+)?([a-zA-Z0-9._-]+\.[a-zA-Z]{2,})",
        text, re.I,
    )
    if ssl_m:
        host = ssl_m.group(1).strip().lower()
        try:
            ctx = _ssl.create_default_context()
            with ctx.wrap_socket(socket.create_connection((host, 443), timeout=8), server_hostname=host) as s:
                cert = s.getpeercert()
            not_after = cert.get("notAfter", "")
            expire_dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=ZoneInfo("UTC"))
            now_utc = datetime.now(tz=ZoneInfo("UTC"))
            days_left = (expire_dt.date() - now_utc.date()).days
            expire_str = expire_dt.strftime("%d %b %Y")
            if days_left < 0:
                verdict = f"**expired {-days_left} day(s) ago**"
            elif days_left <= 14:
                verdict = f"expires in **{days_left} day(s)** — renew urgently"
            elif days_left <= 30:
                verdict = f"expires in **{days_left} days** — renewal recommended"
            else:
                verdict = f"valid for **{days_left} more days** (until {expire_str})"
            return {
                "reply": f"{_ack()} SSL cert for {host}: {verdict}.",
                "data": {"route": "ssl_check", "host": host, "expires": expire_str, "days_left": days_left, "valid": days_left >= 0},
            }
        except _ssl.SSLCertVerificationError:
            return {"reply": f"{_ack()} SSL cert for {host} is **invalid** (verification failed).", "data": {"route": "ssl_check", "host": host, "valid": False, "error": "verification_failed"}}
        except Exception as e:
            return {"reply": f"{_ack()} Could not check SSL for {host}: {type(e).__name__}.", "data": {"route": "ssl_check", "host": host, "valid": False, "error": type(e).__name__}}

    # ── Numeric list operations ───────────────────────────────────────────────
    numlist_m = re.match(
        r"(?:(sort|average|avg|mean|min|max|sum)\s+)([-\d.,\s]+)$", t, re.I,
    )
    if numlist_m:
        op = numlist_m.group(1).lower()
        raw_nums = re.findall(r"-?\d+(?:\.\d+)?", numlist_m.group(2))
        if raw_nums:
            nums = [float(x) for x in raw_nums]
            fmt = lambda v: str(int(v)) if v == int(v) else f"{v:g}"
            if op == "sort":
                result_list = sorted(nums)
                display = ", ".join(fmt(v) for v in result_list)
                return {"reply": f"{_ack()} Sorted: **{display}**", "data": {"route": "numlist", "op": "sort", "result": result_list}}
            if op in {"average", "avg", "mean"}:
                avg = sum(nums) / len(nums)
                return {"reply": f"{_ack()} Average: **{fmt(avg)}**", "data": {"route": "numlist", "op": "average", "result": avg, "count": len(nums)}}
            if op == "min":
                m_val = min(nums)
                return {"reply": f"{_ack()} Min: **{fmt(m_val)}**", "data": {"route": "numlist", "op": "min", "result": m_val}}
            if op == "max":
                m_val = max(nums)
                return {"reply": f"{_ack()} Max: **{fmt(m_val)}**", "data": {"route": "numlist", "op": "max", "result": m_val}}
            if op == "sum":
                s_val = sum(nums)
                return {"reply": f"{_ack()} Sum: **{fmt(s_val)}**", "data": {"route": "numlist", "op": "sum", "result": s_val}}

    # ── Natural language: service queries ───────────────────────────────────
    svc_status_m = re.match(
        r"(?:check|is|status of|how is|wie ist|läuft|ist)\s+(\w[\w.-]{1,30})\s+(?:running|status|up|ok|active|online|laufend)?$",
        t, re.I,
    )
    if svc_status_m:
        svc = svc_status_m.group(1).strip().lower()
        try:
            ensure_service_allowed(svc)
            active = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", svc], timeout=8)
            return {"reply": f"On it. {svc} is {active}.", "data": {"service": svc, "active": active}}
        except Exception:
            pass

    svc_restart_m = re.match(
        r"(?:restart|reload|bounce)\s+(\w[\w.-]{1,30})$",
        t, re.I,
    )
    if svc_restart_m:
        svc = svc_restart_m.group(1).strip().lower()
        blocked = block_write_if_unauthorized(
            role, token, granted_permissions=granted_permissions,
            emergency_stop_enabled=emergency_stop_enabled, permission_check=permission_check,
        )
        if blocked is not None:
            return blocked
        try:
            ensure_service_allowed(svc)
            run_cmd(["/usr/bin/sudo", "/bin/systemctl", "restart", svc], timeout=15)
            st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", svc], timeout=8)
            return {"reply": f"On it. {svc} restarted ({st}).", "data": {"service": svc, "active": st}}
        except Exception:
            pass

    # ── Natural language: set location ──────────────────────────────────────
    loc_match = re.match(
        r"(?:my location is|i(?:'m| am) in|i live in|i(?:'m| am) from|"
        r"mein standort ist|ich bin in|ich wohne in|ich komme aus)\s+(.+)",
        t, re.I,
    )
    if loc_match:
        city = loc_match.group(1).strip().rstrip(".,!?").strip().title()
        if city:
            return {
                "reply": f"Location set to {city}. I'll use that for weather and other location-aware queries.",
                "data": {"save_to_prefs": {"location": city}, "location": city},
            }

    # ── Set display name ─────────────────────────────────────────────────────
    name_m = re.match(
        r"(?:my name is|call me|i(?:'m| am)\s+called)\s+([A-Za-zÀ-ž][a-zA-ZÀ-ž]{1,29})\s*[.,!?]?\s*$",
        t,
    )
    if name_m:
        name = name_m.group(1).strip().title()
        _skip = {"in", "at", "from", "a", "the", "here", "home", "going", "ok", "ready", "jarvis"}
        if len(name) >= 2 and name.lower() not in _skip:
            return {
                "reply": f"Got it. I'll call you {name}.",
                "data": {"save_to_prefs": {"display_name": name}, "display_name": name},
            }

    # ── Natural language: time / date (German + English) ────────────────────
    if re.search(
        r"\b(wie spät ist es|wie viel uhr|uhrzeit|welches datum|was ist das datum|wie ist das datum"
        r"|what time|what's the time|current time|what's the date|current date)\b", t
    ):
        now = datetime.now().astimezone()
        time_str = now.strftime("%H:%M")
        date_str = now.strftime("%A, %d %B %Y")
        return {"reply": f"On it. It is {time_str} on {date_str}.", "data": {"iso": now.isoformat()}}

    # ── Timezone query ────────────────────────────────────────────────────────
    tz_m = re.search(
        r"(?:what(?:'s| is) the )?(?:current\s+)?time\s+in\s+(.+)"
        r"|(?:wie viel uhr|uhrzeit)\s+in\s+(.+)",
        t, re.I,
    )
    if tz_m:
        city_raw = (tz_m.group(1) or tz_m.group(2) or "").strip().rstrip("?.")
        tz = _lookup_tz(city_raw)
        if tz is not None:
            now_there = datetime.now(tz)
            time_str = now_there.strftime("%H:%M")
            date_str = now_there.strftime("%A, %d %B %Y")
            offset = now_there.strftime("%z")
            return {
                "reply": f"On it. In {city_raw.title()}: {time_str} on {date_str} (UTC{offset[:3]}:{offset[3:]}).",
                "data": {
                    "route": "timezone",
                    "city": city_raw.title(),
                    "tz": str(tz),
                    "iso": now_there.isoformat(),
                    "time": time_str,
                },
            }

    # ── Natural language: weather ────────────────────────────────────────────
    if _is_weather_query(t):
        city = _extract_city(t)
        if not city and user_prefs:
            city = (user_prefs.get("location") or "").strip() or None
        if not city:
            return {
                "reply": "Which city should I check? Tell me your location — for example: 'I'm in Munich' — and I'll remember it.",
                "data": {"route": "weather", "needs_location": True},
            }
        weather = _fetch_weather(city)
        if weather is None:
            return {
                "reply": f"I couldn't retrieve weather data for {city}. The service may be unavailable.",
                "data": {"route": "weather", "city": city, "error": "fetch_failed"},
            }
        w = weather
        rain_part = f" {w['rain_pct']}% chance of rain." if w.get("rain_pct") is not None else ""
        wind_part = f" Wind {w['wind_kmh']} km/h." if w.get("wind_kmh") is not None else ""
        high_low  = f" High {w['high']}°C, low {w['low']}°C." if w.get("high") is not None else ""
        reply = (
            f"Understood. {w['city']}: {w['temp']}°C, {w['condition']}."
            f"{high_low}{rain_part}{wind_part}"
        )
        is_forecast_query = any(kw in t for kw in (
            "forecast", "vorhersage", "3 day", "3-day", "morgen", "tomorrow",
            "nächste tage", "next days", "this week", "diese woche",
        ))
        if is_forecast_query and w.get("forecast"):
            days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            lines = []
            for fc in w["forecast"][:3]:
                date_str = fc.get("date") or ""
                try:
                    d = _date.fromisoformat(date_str)
                    label = days[d.weekday()]
                except Exception:
                    label = date_str
                rain_fc = f", {fc['rain_pct']}% rain" if fc.get("rain_pct") is not None else ""
                lines.append(f"  {label}: {fc['high']}°/{fc['low']}° {fc['condition']}{rain_fc}")
            if lines:
                reply += "\n" + "\n".join(lines)
        return {"reply": reply.strip(), "data": {"route": "weather", **w}}

    # ── Timer / Reminder ──────────────────────────────────────────────────────
    _timer_m = re.match(
        r"(?:set\s+a?\s*)?timer\s+(?:for\s+)?(\d+)\s*(second|seconds|sec|s|minute|minutes|min|m|hour|hours|hr|h)\b",
        t, re.I,
    )
    _remind_m = re.match(
        r"remind\s+me\s+in\s+(\d+)\s*(second|seconds|sec|s|minute|minutes|min|m|hour|hours|hr|h)\s+"
        r"(?:to|that|about|zu|dass?|über)\s+(.+)",
        t, re.I,
    )
    if _timer_m or _remind_m:
        if _remind_m:
            n, unit_raw, label = int(_remind_m.group(1)), _remind_m.group(2).lower(), _remind_m.group(3).strip().rstrip(".,!?")
        else:
            n, unit_raw, label = int(_timer_m.group(1)), _timer_m.group(2).lower(), None
        if unit_raw.startswith("h"):
            delay_ms = n * 3_600_000
            unit_disp = f"{n} hour{'s' if n != 1 else ''}"
        elif unit_raw.startswith("m"):
            delay_ms = n * 60_000
            unit_disp = f"{n} minute{'s' if n != 1 else ''}"
        else:
            delay_ms = n * 1_000
            unit_disp = f"{n} second{'s' if n != 1 else ''}"
        if label:
            reply = f"On it. I'll remind you to {label} in {unit_disp}."
        else:
            reply = f"On it. Timer set for {unit_disp}."
        return {
            "reply": reply,
            "data": {
                "route": "reminder",
                "delay_ms": delay_ms,
                "label": label or f"Timer: {unit_disp}",
            },
        }

    # ── Notes: remember / recall ──────────────────────────────────────────────
    note_save = re.match(
        r"(?:remember(?: that)?|note(?: that)?|merke?|notiz):?\s+(.+)",
        t, re.I,
    )
    if note_save:
        note_text = note_save.group(1).strip().rstrip(".,!?").strip()
        if note_text:
            existing = list(user_prefs.get("notes") or []) if user_prefs else []
            existing.append(note_text)
            return {
                "reply": f"Noted. I'll remember: \"{note_text}\"",
                "data": {"save_to_prefs": {"notes": existing}, "route": "note_saved"},
            }

    if re.search(r"\b(what do you remember|what did you note|my notes|show notes|zeig meine notizen)\b", t):
        notes = list(user_prefs.get("notes") or []) if user_prefs else []
        if not notes:
            return {"reply": "No notes on file. Say 'remember that…' to add one.", "data": {"route": "notes", "notes": []}}
        items = "\n".join(f"• {n}" for n in notes[-10:])
        return {"reply": f"On it. Your notes:\n{items}", "data": {"route": "notes", "notes": notes}}

    if re.match(r"(?:clear all notes|delete all notes|remove all notes|clear notes|erase notes)", t, re.I):
        return {
            "reply": "Done. All notes cleared.",
            "data": {"save_to_prefs": {"notes": []}, "route": "notes_cleared"},
        }

    note_forget = re.match(r"(?:forget|delete note|remove note)\s+(.+)", t, re.I)
    if note_forget:
        keyword = note_forget.group(1).strip().lower()
        notes = list(user_prefs.get("notes") or []) if user_prefs else []
        remaining = [n for n in notes if keyword not in n.lower()]
        removed = len(notes) - len(remaining)
        if removed:
            return {
                "reply": f"Done. Removed {removed} note(s) matching '{keyword}'.",
                "data": {"save_to_prefs": {"notes": remaining}, "route": "note_deleted"},
            }
        return {"reply": f"No notes matching '{keyword}' found.", "data": {"route": "note_deleted", "removed": 0}}

    return None


def rag_query_from_prompt(text: str) -> dict | None:
    raw = (text or "").strip()
    lowered = raw.lower()

    wiki_match = re.search(r"(?:wiki\s*seite|wiki\s*page)\s+([a-zA-Z0-9_\-./ ]+)", lowered)
    if wiki_match:
        title = wiki_match.group(1).strip(" .,!?:;\"'“”„").strip()
        return {"query": title or raw, "source": "wikijs", "title": title, "mode": "page"}

    if any(tok in lowered for tok in ["taskliste", "tasks", "aufgaben", "to do", "todo", "budgetplan", "budget"]):
        return {"query": "tasks", "source": "wikijs", "title": "", "mode": "tasks"}

    gh_match = re.search(r"(?:github|repo|repository)\s+([a-zA-Z0-9_\-./ ]+)", lowered)
    if gh_match:
        topic = gh_match.group(1).strip(" .,!?:;\"'“”„").strip()
        return {"query": topic or raw, "source": "github", "title": "", "mode": "repo"}

    if any(tok in lowered for tok in ["wiki", "wikijs", "github", "repository", "repo", "rag"]):
        return {"query": raw, "source": "", "title": "", "mode": "generic"}

    return None


def select_rag_hits(intent: dict, *, rag_store, limit: int = 3) -> list[dict]:
    query = intent.get("query") or ""
    source = (intent.get("source") or "").strip().lower()
    title = (intent.get("title") or "").strip().lower()

    hits = rag_store.search(query, limit=8)
    if source:
        hits = [hit for hit in hits if (hit.get("source") or "").lower() == source]

    if title:
        exact = [hit for hit in hits if (hit.get("title") or "").strip().lower() == title]
        if exact:
            hits = exact + [hit for hit in hits if hit not in exact]

    return hits[:limit]


def format_rag_reply(intent: dict, hits: list[dict]) -> str:
    mode = intent.get("mode") or "generic"
    if not hits:
        return "Understood. I found no matching RAG entries."

    if mode == "tasks":
        lines = []
        for index, hit in enumerate(hits[:5], start=1):
            title = hit.get("title") or "task"
            text = (hit.get("text") or "").strip()
            snippet = text[:110] + ("…" if len(text) > 110 else "")
            lines.append(f"{index}. {title} — {snippet}" if snippet else f"{index}. {title}")
        return "Understood. Current tasks from wiki:\n" + "\n".join(lines)

    top = hits[0]
    snippet = (top.get("text") or "").strip()
    snippet = snippet[:260] + ("…" if len(snippet) > 260 else "")
    if snippet:
        return f"Understood. From {top.get('source')}: {top.get('title')} — {snippet}"
    return f"Understood. From {top.get('source')}: {top.get('title')}"


def cloud_llm_available() -> bool:
    return bool((os.getenv("OPENAI_API_KEY") or "").strip() or (os.getenv("GEMINI_API_KEY") or "").strip())


def rag_needs_smart_llm(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        term in lowered
        for term in [
            "liste",
            "list",
            "lese",
            "read",
            "vor",
            "vorlesen",
            "erklär",
            "explain",
            "zusammen",
            "summary",
            "analys",
            "plan",
            "budget",
            "task",
            "aufgabe",
        ]
    )


def rag_llm_answer(user_text: str, hits: list[dict], *, get_provider, get_gemini, get_openai) -> str:
    provider = get_provider()
    context_lines = []
    for index, hit in enumerate(hits[:8], start=1):
        context_lines.append(
            f"[{index}] source={hit.get('source','')} title={hit.get('title','')} text={hit.get('text','')}"
        )
    context_blob = "\n".join(context_lines)

    prompt = (
        "You are J.A.R.V.I.S. Use only the provided RAG context. "
        "Answer in German, concise and structured, with bullets for lists/tasks. "
        "If user asks to list/read items, enumerate clearly.\n\n"
        f"User request: {user_text}\n\nRAG context:\n{context_blob}"
    )

    if provider == "gemini" and os.getenv("GEMINI_API_KEY"):
        client = get_gemini()
        model = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
        resp = client.models.generate_content(
            model=model,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
        )
        return (getattr(resp, "text", "") or "").strip() or "Understood. No output returned."

    if os.getenv("OPENAI_API_KEY"):
        client = get_openai()
        model = os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are J.A.R.V.I.S from Iron Man."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=int(os.getenv("OPENAI_MAX_TOKENS") or "220"),
        )
        return (resp.choices[0].message.content or "").strip() or "Understood. No output returned."

    raise RuntimeError("No supported cloud LLM configured for RAG smart response")
