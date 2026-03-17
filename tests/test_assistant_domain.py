import unittest
from unittest.mock import Mock

from fastapi import HTTPException

from jarvis.assistant_domain import (
    block_write_if_unauthorized,
    format_rag_reply,
    rag_query_from_prompt,
    select_rag_hits,
    try_skill,
)


class AssistantDomainTests(unittest.TestCase):
    def test_block_write_if_unauthorized_requires_token(self):
        result = block_write_if_unauthorized(
            "admin",
            None,
            granted_permissions=None,
            emergency_stop_enabled=lambda: False,
            permission_check=lambda *_args: True,
        )
        self.assertEqual("missing_token", result["data"]["error"])

    def test_rag_query_from_prompt_detects_tasks_mode(self):
        result = rag_query_from_prompt("zeige mir die taskliste")
        self.assertEqual("tasks", result["mode"])
        self.assertEqual("wikijs", result["source"])

    def test_select_rag_hits_filters_source_and_title(self):
        rag_store = Mock()
        rag_store.search.return_value = [
            {"source": "github", "title": "other", "text": "nope"},
            {"source": "wikijs", "title": "Target", "text": "match"},
            {"source": "wikijs", "title": "other", "text": "later"},
        ]
        hits = select_rag_hits(
            {"query": "target", "source": "wikijs", "title": "target"},
            rag_store=rag_store,
            limit=2,
        )
        self.assertEqual(["Target", "other"], [hit["title"] for hit in hits])

    def test_format_rag_reply_formats_tasks(self):
        reply = format_rag_reply(
            {"mode": "tasks"},
            [{"title": "Task A", "text": "Do the important thing"}],
        )
        self.assertIn("Current tasks from wiki", reply)
        self.assertIn("Task A", reply)

    def test_try_skill_rejects_invalid_ping_host(self):
        with self.assertRaises(HTTPException):
            try_skill(
                "ping invalid host!",
                role="admin",
                token="tok",
                granted_permissions=None,
                emergency_stop_enabled=lambda: False,
                permission_check=lambda *_args: True,
                run_cmd=lambda *_args, **_kwargs: "",
                disk_usage=lambda *_args, **_kwargs: None,
                format_bytes=lambda value: str(value),
                parse_meminfo=lambda: {},
                parse_ping=lambda _out: {},
                tail_lines=lambda text, max_lines=6: text,
                ensure_service_allowed=lambda _service: None,
                proxmox_vm_status=lambda *_args: {},
                proxmox_lxc_status=lambda *_args: {},
            )


if __name__ == "__main__":
    unittest.main()
