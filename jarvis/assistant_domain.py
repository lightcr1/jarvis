import os
import platform
import re
from datetime import datetime

from fastapi import HTTPException


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
) -> dict[str, object] | None:
    t = text.strip().lower()

    if t in {"health", "status", "ping jarvis"}:
        return {"reply": "On it. Backend is healthy.", "data": {"ok": True}}

    if t in {"uptime", "server uptime"}:
        out = run_cmd(["/usr/bin/uptime", "-p"])
        return {"reply": f"On it. {out}", "data": {"raw": out}}

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

    if t in {"time", "date", "time and date", "what time is it"}:
        now = datetime.now().astimezone()
        return {"reply": f"On it. {now.strftime('%Y-%m-%d %H:%M:%S %Z')}.", "data": {"iso": now.isoformat()}}

    if t in {"hostname", "host info", "host"}:
        hostname = platform.node()
        return {"reply": f"On it. Hostname: {hostname}.", "data": {"hostname": hostname}}

    if t in {"help", "skills", "skills overview", "what can you do"}:
        overview = [
            "health/status/ping jarvis",
            "uptime",
            "disk",
            "memory",
            "docker",
            "status <service>",
            "logs <service>",
            "ping <host>",
            "pve vm status <host_id> <node> <vmid>",
            "pve lxc status <host_id> <node> <vmid>",
            "restart|start|stop <service>",
            "system status",
            "time and date",
            "hostname",
        ]
        return {"reply": "On it. Available skills: " + ", ".join(overview) + ".", "data": {"skills": overview}}

    if t.startswith("restart "):
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
