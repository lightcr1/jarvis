from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import difflib
import json
import os
from pathlib import Path
import re
import time
from typing import Callable


class RiskLevel:
    READ = "read"
    WRITE = "write"
    CRITICAL = "critical"


CONFIRM_WRITE = "YES"
CONFIRM_CRITICAL = "YES, proceed"


@dataclass
class ActionPlan:
    summary: str
    steps: list[str]
    risk: str
    target: str | None
    execute: Callable[[], dict]


@dataclass
class Skill:
    name: str
    description: str
    risk: str
    triggers: list[str]
    examples: list[str]
    handler: Callable[["ExecutionContext"], ActionPlan | dict]


@dataclass
class ExecutionContext:
    text: str
    token: str | None
    verbose: bool
    now: float
    registry: "SkillRegistry"
    policy: "SecurityPolicy"
    learning: "LearningStore"
    metadata: dict = field(default_factory=dict)


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: list[Skill] = []

    def register(self, skill: Skill) -> None:
        self._skills.append(skill)

    def skills(self) -> list[Skill]:
        return list(self._skills)

    def match(self, text: str) -> list[tuple[Skill, float]]:
        normalized = normalize(text)
        scored: list[tuple[Skill, float]] = []
        for skill in self._skills:
            best = 0.0
            for trigger in skill.triggers + skill.examples + [skill.name]:
                score = difflib.SequenceMatcher(None, normalized, normalize(trigger)).ratio()
                best = max(best, score)
            if best > 0.45:
                scored.append((skill, best))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored


class SecurityPolicy:
    def __init__(self) -> None:
        self.allowed_targets = {
            t.strip().lower()
            for t in (os.getenv("ALLOWED_TARGETS") or "").split(",")
            if t.strip()
        }
        self.cooldowns = {
            "restart": int(os.getenv("COOLDOWN_RESTART_SECONDS") or "60"),
            "critical": int(os.getenv("COOLDOWN_CRITICAL_SECONDS") or "90"),
        }
        self._last_action: dict[str, float] = {}

    def is_target_allowed(self, target: str | None, risk: str) -> bool:
        if risk == RiskLevel.READ:
            return True
        if not target:
            return False
        if not self.allowed_targets:
            return False
        return target.lower() in self.allowed_targets

    def check_cooldown(self, key: str, cooldown_key: str) -> tuple[bool, int]:
        now = time.time()
        cooldown = self.cooldowns.get(cooldown_key, 0)
        last = self._last_action.get(key, 0)
        if cooldown and now - last < cooldown:
            return False, int(cooldown - (now - last))
        self._last_action[key] = now
        return True, 0


class JarvisEngine:
    def __init__(self, registry: SkillRegistry, policy: SecurityPolicy) -> None:
        self.registry = registry
        self.policy = policy
        self._pending: dict[str, ActionPlan] = {}
        self.learning = LearningStore()

    def process(self, text: str, token: str | None) -> dict:
        cleaned, verbose = strip_verbose(text)
        cleaned = self.learning.apply_aliases(cleaned)
        ctx = ExecutionContext(
            text=cleaned,
            token=token,
            verbose=verbose,
            now=time.time(),
            registry=self.registry,
            policy=self.policy,
            learning=self.learning,
        )

        if wakeword_enabled() and normalize(cleaned) in wakeword_phrases():
            return self._finalize_response(
                cleaned,
                "status jarvis",
                summary_response(
                    "Understood. J.A.R.V.I.S online and ready.",
                    {
                        "hint": "Try: skills, status jarvis, proxmox health",
                        "wakeword": (os.getenv("JARVIS_WAKEWORD_PHRASE") or "hey jarvis"),
                    },
                ),
                False,
            )

        confirm = self._handle_confirm(cleaned, ctx)
        if confirm:
            return confirm

        feedback = self._handle_feedback(cleaned)
        if feedback:
            return feedback

        learning_cmd = self._handle_learning_commands(cleaned)
        if learning_cmd:
            return self._finalize_response(cleaned, "learning-command", learning_cmd, False)

        proactive_learned = self.learning.find_learned_reply(cleaned, min_score=0.90)
        if proactive_learned:
            return summary_response(
                proactive_learned["summary"],
                {
                    "route": "learned_memory",
                    "confidence": proactive_learned["score"],
                    "source": proactive_learned["source"],
                },
            )

        matches = self.registry.match(cleaned)
        self.learning.record_query(cleaned, bool(matches))
        if not matches:
            return self._fallback(cleaned, ctx)

        top_score = matches[0][1]
        contenders = [m for m in matches if top_score - m[1] < 0.08]
        if len(contenders) > 1 and top_score < 0.86:
            options = [c[0].name for c in contenders[:3]]
            return summary_response(
                "Need clarification.",
                {
                    "reason": "ambiguous",
                    "options": options,
                    "hint": "Pick one of the options or refine your request.",
                },
            )

        skill = matches[0][0]
        result = skill.handler(ctx)
        if isinstance(result, ActionPlan):
            return self._handle_plan(result, ctx)
        return self._finalize_response(cleaned, skill.name, summarize_output(result, ctx), False)

    def _finalize_response(self, text: str, skill_name: str, response: dict, needs_confirmation: bool) -> dict:
        if needs_confirmation:
            return response
        response_data = response.setdefault("data", {})
        self.learning.record_success(text, response.get("summary", ""), skill_name)
        feedback_id = self.learning.record_feedback_item(text, skill_name, response.get("summary", ""))
        response_data["feedback"] = {
            "id": feedback_id,
            "prompt": f"feedback {feedback_id} ok|bad [correct: <dein mapping>]",
        }
        return response

    def _handle_confirm(self, text: str, ctx: ExecutionContext) -> dict | None:
        lowered = text.strip().lower()
        if lowered in {CONFIRM_WRITE.lower(), CONFIRM_CRITICAL.lower()}:
            if not ctx.token:
                return summary_response("Token required.", {"error": "missing_token"})
            plan = self._pending.pop(ctx.token, None)
            if not plan:
                return summary_response("Nothing pending.", {"error": "no_pending_action"})
            response = summarize_output(plan.execute(), ctx)
            return self._finalize_response(text, "confirmed-plan", response, False)
        return None

    def _handle_feedback(self, text: str) -> dict | None:
        match = re.match(r"^feedback\s+(\S+)\s+(ok|bad)(?:\s+correct:\s+(.+))?$", text, re.IGNORECASE)
        if not match:
            return None
        feedback_id, verdict, correction = match.groups()
        saved = self.learning.save_feedback(feedback_id, verdict.lower(), correction or "")
        if not saved:
            return summary_response("Feedback ID unknown.", {"error": "feedback_not_found"})
        return summary_response("Feedback gespeichert.", {"feedback_id": feedback_id, "verdict": verdict.lower()})

    def _handle_learning_commands(self, text: str) -> dict | None:
        lowered = normalize(text)
        if lowered in {"memory show", "learning show", "memory"}:
            return summary_response("Memory snapshot ready.", {"memory": self.learning.snapshot()})

        match = re.match(r"^remember\s+(node|vmid|default)\s+(\S+)\s+(.+)$", text, re.IGNORECASE)
        if not match:
            return None

        kind, key, value = match.groups()
        self.learning.remember(kind.lower(), key, value)
        return summary_response(
            "Memory updated.",
            {"stored": {"type": kind.lower(), "key": key, "value": value.strip()}},
        )

    def _handle_plan(self, plan: ActionPlan, ctx: ExecutionContext) -> dict:
        if plan.risk in {RiskLevel.WRITE, RiskLevel.CRITICAL} and not ctx.token:
            return summary_response("Token required.", {"error": "missing_token"})

        if plan.risk in {RiskLevel.WRITE, RiskLevel.CRITICAL}:
            if not ctx.policy.is_target_allowed(plan.target, plan.risk):
                return summary_response(
                    "Target not allowed.",
                    {"error": "target_not_allowed", "target": plan.target},
                )

        if plan.risk == RiskLevel.CRITICAL:
            if ctx.token:
                self._pending[ctx.token] = plan
            return self._finalize_response(
                ctx.text,
                "critical-plan",
                summary_response(
                "Plan ready. Confirmation required.",
                {
                    "risk": plan.risk,
                    "summary": plan.summary,
                    "steps": plan.steps,
                    "confirm": CONFIRM_CRITICAL,
                },
            ),
                True,
            )

        if plan.risk == RiskLevel.WRITE:
            if ctx.token:
                self._pending[ctx.token] = plan
            return self._finalize_response(
                ctx.text,
                "write-plan",
                summary_response(
                "Confirmation required.",
                {
                    "risk": plan.risk,
                    "summary": plan.summary,
                    "confirm": CONFIRM_WRITE,
                },
            ),
                True,
            )

        response = summarize_output(plan.execute(), ctx)
        return self._finalize_response(ctx.text, "read-plan", response, False)

    def _fallback(self, text: str, ctx: ExecutionContext) -> dict:
        suggestion = self.learning.skill_suggestion(text)
        learned = self.learning.find_learned_reply(text)
        if learned:
            return summary_response(
                learned["summary"],
                {
                    "route": "learned_memory",
                    "confidence": learned["score"],
                    "source": learned["source"],
                    "skill_suggestion": suggestion,
                },
            )

        maybe = self.learning.closest_learned_phrase(text)
        if maybe:
            return summary_response(
                "Need clarification.",
                {
                    "reason": "learned_but_uncertain",
                    "hint": f"Did you mean: '{maybe['source']}'?",
                    "skill_suggestion": suggestion,
                },
            )

        if cloud_configured():
            return summary_response(
                "Cloud routing required.",
                {
                    "info": "No local skill matched. Cloud LLM can be used via /chat in app server.",
                    "offline": False,
                    "route": "cloud",
                    "skill_suggestion": suggestion,
                },
            )
        return summary_response(
            "Offline mode: no matching skill.",
            {
                "offline": True,
                "route": "offline",
                "hint": "Try 'help' or 'skills' for available commands.",
                "skill_suggestion": suggestion,
            },
        )


class LearningStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_MEMORY_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/memory.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {
            "nodes": {},
            "vmids": {},
            "defaults": {},
            "favorite_commands": [],
            "learned_replies": {},
            "query_stats": {},
            "feedback_log": {},
            "aliases": {},
        }

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            return {**self._empty(), **content}
        except (json.JSONDecodeError, OSError):
            return self._empty()

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def apply_aliases(self, text: str) -> str:
        normalized = normalize(text)
        replacement = self.data.get("aliases", {}).get(normalized)
        return replacement or text

    def record_query(self, text: str, matched: bool) -> None:
        key = normalize(text)
        stats = self.data.setdefault("query_stats", {}).setdefault(key, {"total": 0, "unmatched": 0})
        stats["total"] += 1
        if not matched:
            stats["unmatched"] += 1
        self._save()

    def skill_suggestion(self, text: str) -> str | None:
        key = normalize(text)
        stats = self.data.get("query_stats", {}).get(key, {})
        if stats.get("unmatched", 0) >= 3:
            return f"'{text}' wird häufig gefragt. Soll ich dafür einen Skill anlegen?"
        return None

    def record_feedback_item(self, text: str, skill: str, summary: str) -> str:
        item_id = f"fb-{int(time.time() * 1000)}"
        self.data.setdefault("feedback_log", {})[item_id] = {
            "text": text,
            "skill": skill,
            "summary": summary,
            "verdict": "pending",
            "correction": "",
        }
        self._save()
        return item_id

    def save_feedback(self, feedback_id: str, verdict: str, correction: str) -> bool:
        feedback = self.data.setdefault("feedback_log", {}).get(feedback_id)
        if not feedback:
            return False
        feedback["verdict"] = verdict
        feedback["correction"] = correction.strip()
        if verdict == "bad" and correction.strip():
            self.data.setdefault("aliases", {})[normalize(feedback.get("text", ""))] = correction.strip()
        self._save()
        return True

    def remember(self, kind: str, key: str, value: str) -> None:
        value = value.strip()
        key = key.strip()
        if kind == "node":
            self.data.setdefault("nodes", {})[key] = value
        elif kind == "vmid":
            self.data.setdefault("vmids", {})[key] = value
        else:
            self.data.setdefault("defaults", {})[key] = value
        self._save()

    def snapshot(self) -> dict:
        return {
            "nodes": self.data.get("nodes", {}),
            "vmids": self.data.get("vmids", {}),
            "defaults": self.data.get("defaults", {}),
            "aliases": self.data.get("aliases", {}),
            "learned_replies": len(self.data.get("learned_replies", {})),
            "stable_learned_replies": len([v for v in self.data.get("learned_replies", {}).values() if (v or {}).get("confidence", 0) >= 2]),
            "query_stats_size": len(self.data.get("query_stats", {})),
            "feedback_entries": len(self.data.get("feedback_log", {})),
        }

    def record_success(self, text: str, summary: str, skill_name: str) -> None:
        normalized = normalize(text)
        cleaned_summary = (summary or "").strip()
        if not normalized or not cleaned_summary:
            return
        if normalized.startswith("feedback "):
            return

        learned = self.data.setdefault("learned_replies", {})
        existing = learned.get(normalized, {})

        # Prefer deterministic skills and avoid storing noisy cloud/error-like summaries.
        lower_summary = cleaned_summary.lower()
        if any(x in lower_summary for x in ["error", "exception", "traceback"]):
            return

        confidence = int(existing.get("confidence", 0)) + 1
        learned[normalized] = {
            "summary": cleaned_summary,
            "skill": skill_name,
            "updated_at": int(time.time()),
            "confidence": confidence,
        }
        self._save()

    def find_learned_reply(self, text: str, min_score: float = 0.80) -> dict | None:
        normalized = normalize(text)
        learned = self.data.get("learned_replies", {})
        direct = learned.get(normalized)
        if direct and int(direct.get("confidence", 0)) >= 2:
            return {"summary": direct.get("summary", "Done."), "score": 1.0, "source": normalized}

        best_key = ""
        best_score = 0.0
        for key, item in learned.items():
            if int((item or {}).get("confidence", 0)) < 2:
                continue
            score = difflib.SequenceMatcher(None, normalized, key).ratio()
            if score > best_score:
                best_score = score
                best_key = key

        if best_key and best_score >= min_score:
            item = learned[best_key]
            return {"summary": item.get("summary", "Done."), "score": round(best_score, 2), "source": best_key}
        return None

    def closest_learned_phrase(self, text: str) -> dict | None:
        normalized = normalize(text)
        learned = self.data.get("learned_replies", {})
        best_key = ""
        best_score = 0.0
        for key, item in learned.items():
            if int((item or {}).get("confidence", 0)) < 2:
                continue
            score = difflib.SequenceMatcher(None, normalized, key).ratio()
            if score > best_score:
                best_score = score
                best_key = key
        if best_key and 0.62 <= best_score < 0.80:
            return {"source": best_key, "score": round(best_score, 2)}
        return None


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def strip_verbose(text: str) -> tuple[str, bool]:
    tokens = text.split()
    verbose = False
    filtered = []
    for token in tokens:
        if token.lower() in {"--verbose", "verbose", "-v"}:
            verbose = True
        else:
            filtered.append(token)
    return " ".join(filtered), verbose


def wakeword_enabled() -> bool:
    return (os.getenv("JARVIS_WAKEWORD_ENABLED") or "0").strip().lower() not in {"0", "false", "no", "off"}


def wakeword_phrases() -> set[str]:
    primary = normalize((os.getenv("JARVIS_WAKEWORD_PHRASE") or "hey jarvis").strip())
    aliases = {
        primary,
        "hey jarvis",
        "ok jarvis",
        "hello jarvis",
        "jarvis",
    }
    return {a for a in aliases if a}


def cloud_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY"))


def summary_response(summary: str, data: dict | None = None) -> dict:
    return {"summary": summary, "data": data or {}}


def summarize_output(payload: dict, ctx: ExecutionContext) -> dict:
    summary = payload.get("summary") or payload.get("reply") or "Done."
    data = payload.get("data", {})
    if ctx.verbose:
        data = {**data, "details": payload}
    return {"summary": summary, "data": data}


def masked(value: str, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return f"{value[:keep]}***"


def build_registry() -> SkillRegistry:
    registry = SkillRegistry()

    registry.register(
        Skill(
            name="help",
            description="Kurzinfo und Beispiele",
            risk=RiskLevel.READ,
            triggers=["help", "hilfe"],
            examples=["help", "help status jarvis"],
            handler=handle_help,
        )
    )
    registry.register(
        Skill(
            name="skills",
            description="Liste alle Skills mit Risk-Level",
            risk=RiskLevel.READ,
            triggers=["skills", "skill list"],
            examples=["skills"],
            handler=handle_skills,
        )
    )
    registry.register(
        Skill(
            name="status jarvis",
            description="Systemstatus des Assistants",
            risk=RiskLevel.READ,
            triggers=["status jarvis", "system status"],
            examples=["status jarvis"],
            handler=handle_status,
        )
    )
    registry.register(
        Skill(
            name="assistant mood",
            description="Smalltalk Antworten (wie geht's / how are you)",
            risk=RiskLevel.READ,
            triggers=["how are you", "wie gehts", "wie geht's", "hows it going"],
            examples=["how are you"],
            handler=handle_assistant_mood,
        )
    )
    registry.register(
        Skill(
            name="diagnose jarvis",
            description="Self-check ohne Änderungen",
            risk=RiskLevel.READ,
            triggers=["diagnose jarvis", "health check"],
            examples=["diagnose jarvis"],
            handler=handle_diagnose,
        )
    )
    registry.register(
        Skill(
            name="config show",
            description="Zeigt Konfiguration (maskiert)",
            risk=RiskLevel.READ,
            triggers=["config show", "show config"],
            examples=["config show"],
            handler=handle_config_show,
        )
    )
    registry.register(
        Skill(
            name="proxmox health",
            description="Proxmox-Status (vorbereitet)",
            risk=RiskLevel.READ,
            triggers=["proxmox health", "pve health"],
            examples=["proxmox health"],
            handler=handle_proxmox_health,
        )
    )
    registry.register(
        Skill(
            name="proxmox vm status",
            description="Proxmox VM-Status (deterministisch)",
            risk=RiskLevel.READ,
            triggers=["proxmox vm status", "pve vm status"],
            examples=["pve vm status home-pve pve 100"],
            handler=handle_proxmox_vm_status,
        )
    )
    registry.register(
        Skill(
            name="proxmox lxc status",
            description="Proxmox LXC-Status (deterministisch)",
            risk=RiskLevel.READ,
            triggers=["proxmox lxc status", "pve lxc status"],
            examples=["pve lxc status home-pve pve 101"],
            handler=handle_proxmox_lxc_status,
        )
    )
    registry.register(
        Skill(
            name="vm ssh exec",
            description="Remote SSH Befehl (kritisch)",
            risk=RiskLevel.CRITICAL,
            triggers=["vm ssh exec", "ssh exec"],
            examples=["vm ssh exec web01 uptime"],
            handler=handle_vm_ssh_exec,
        )
    )
    registry.register(
        Skill(
            name="service restart",
            description="Restart eines Services (kritisch)",
            risk=RiskLevel.CRITICAL,
            triggers=["service restart", "restart service"],
            examples=["service restart local nginx"],
            handler=handle_service_restart,
        )
    )
    registry.register(
        Skill(
            name="service status",
            description="Status eines Services",
            risk=RiskLevel.READ,
            triggers=["service status", "status service"],
            examples=["service status local nginx"],
            handler=handle_service_status,
        )
    )
    registry.register(
        Skill(
            name="net check",
            description="Ping/DNS Check",
            risk=RiskLevel.READ,
            triggers=["net check", "network check"],
            examples=["net check local google.com"],
            handler=handle_net_check,
        )
    )
    return registry


def handle_help(ctx: ExecutionContext) -> dict:
    examples = [skill.examples[0] for skill in ctx.registry.skills() if skill.examples]
    return {
        "summary": "Top commands ready.",
        "data": {"examples": examples[:8]},
    }


def handle_skills(ctx: ExecutionContext) -> dict:
    skills = [
        {"name": s.name, "risk": s.risk, "description": s.description}
        for s in ctx.registry.skills()
    ]
    return {
        "summary": f"{len(skills)} skills available.",
        "data": {"skills": skills},
    }


def handle_status(ctx: ExecutionContext) -> dict:
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return {
        "summary": "Jarvis is running.",
        "data": {"time": now, "offline": not cloud_configured()},
    }


def handle_assistant_mood(ctx: ExecutionContext) -> dict:
    return {
        "summary": "Understood. Running stable and ready to help.",
        "data": {"mode": "assistant", "tone": "confident"},
    }


def handle_diagnose(ctx: ExecutionContext) -> dict:
    checks = {
        "stt_provider": os.getenv("STT_PROVIDER") or "local",
        "tts_configured": bool(os.getenv("PIPER_MODEL")),
        "proxmox_configured": bool(os.getenv("PROXMOX_API_TOKEN")),
        "cloud_configured": cloud_configured(),
    }
    return {
        "summary": "Diagnostics ready.",
        "data": {"checks": checks, "next_steps": ["Configure missing items via env or config file."]},
    }


def handle_config_show(ctx: ExecutionContext) -> dict:
    data = {
        "LLM_PROVIDER": os.getenv("LLM_PROVIDER") or "openai",
        "OPENAI_API_KEY": masked(os.getenv("OPENAI_API_KEY") or ""),
        "GEMINI_API_KEY": masked(os.getenv("GEMINI_API_KEY") or ""),
        "PROXMOX_BASE_URL": os.getenv("PROXMOX_BASE_URL") or "",
        "PROXMOX_API_TOKEN": masked(os.getenv("PROXMOX_API_TOKEN") or ""),
        "ALLOWED_TARGETS": os.getenv("ALLOWED_TARGETS") or "",
    }
    return {"summary": "Config snapshot.", "data": data}


def handle_proxmox_health(ctx: ExecutionContext) -> dict:
    if not os.getenv("PROXMOX_API_TOKEN"):
        return {
            "summary": "Proxmox not configured.",
            "data": {"hint": "Set PROXMOX_BASE_URL and PROXMOX_API_TOKEN."},
        }
    return {
        "summary": "Proxmox configured (token present).",
        "data": {"mode": "ready"},
    }


def handle_proxmox_vm_status(ctx: ExecutionContext) -> dict:
    parts = ctx.text.split()
    if len(parts) < 6:
        return {
            "summary": "Need clarification.",
            "data": {"hint": "Use: pve vm status <host_id> <node> <vmid>"},
        }

    host_id, node, vmid = parts[3], parts[4], parts[5]
    return {
        "summary": f"Proxmox VM status request ready for {host_id}/{node}/{vmid}.",
        "data": {
            "provider": "proxmox",
            "resource": "vm",
            "host_id": host_id,
            "node": node,
            "vmid": vmid,
            "status": "not_executed_in_engine",
        },
    }


def handle_proxmox_lxc_status(ctx: ExecutionContext) -> dict:
    parts = ctx.text.split()
    if len(parts) < 6:
        return {
            "summary": "Need clarification.",
            "data": {"hint": "Use: pve lxc status <host_id> <node> <vmid>"},
        }

    host_id, node, vmid = parts[3], parts[4], parts[5]
    return {
        "summary": f"Proxmox LXC status request ready for {host_id}/{node}/{vmid}.",
        "data": {
            "provider": "proxmox",
            "resource": "lxc",
            "host_id": host_id,
            "node": node,
            "vmid": vmid,
            "status": "not_executed_in_engine",
        },
    }


def handle_vm_ssh_exec(ctx: ExecutionContext) -> ActionPlan:
    parts = ctx.text.split()
    target = parts[3] if len(parts) > 3 else None
    command = " ".join(parts[4:]) if len(parts) > 4 else ""

    plan = ActionPlan(
        summary=f"Execute remote command on {target}: {command}",
        steps=[
            "Validate SSH configuration.",
            f"Run command on target {target}.",
            "Collect output and status.",
        ],
        risk=RiskLevel.CRITICAL,
        target=target,
        execute=lambda: {
            "summary": "Remote exec not configured.",
            "data": {"target": target, "command": command, "status": "blocked"},
        },
    )
    return plan


def handle_service_restart(ctx: ExecutionContext) -> ActionPlan:
    parts = ctx.text.split()
    target = parts[2] if len(parts) > 2 else None
    service = parts[3] if len(parts) > 3 else None
    cooldown_key = f"restart:{target}:{service}"
    allowed, wait = ctx.policy.check_cooldown(cooldown_key, "restart")
    if not allowed:
        return ActionPlan(
            summary=f"Cooldown active ({wait}s).",
            steps=["Wait for cooldown to expire."],
            risk=RiskLevel.READ,
            target=target,
            execute=lambda: {"summary": f"Cooldown {wait}s remaining.", "data": {"wait": wait}},
        )

    return ActionPlan(
        summary=f"Restart service {service} on {target}.",
        steps=["Validate target allowlist.", "Restart service.", "Verify status."],
        risk=RiskLevel.CRITICAL,
        target=target,
        execute=lambda: {
            "summary": "Service restart not configured.",
            "data": {"target": target, "service": service, "status": "blocked"},
        },
    )


def handle_service_status(ctx: ExecutionContext) -> dict:
    parts = ctx.text.split()
    target = parts[2] if len(parts) > 2 else None
    service = parts[3] if len(parts) > 3 else None
    return {
        "summary": f"Service status ready for {service} on {target}.",
        "data": {"target": target, "service": service, "status": "unknown"},
    }


def handle_net_check(ctx: ExecutionContext) -> dict:
    parts = ctx.text.split()
    target = parts[2] if len(parts) > 2 else "local"
    host = parts[3] if len(parts) > 3 else ""
    return {
        "summary": "Network check prepared.",
        "data": {"target": target, "host": host, "status": "not_executed"},
    }
