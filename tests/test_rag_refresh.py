import os
import tempfile
import unittest
from unittest.mock import patch

import jarvisappv4


class RagRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_RAG_CACHE_PATH"] = os.path.join(self.tmpdir.name, "rag_cache.json")
        self.store = jarvisappv4.RagStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        for key in [
            "JARVIS_RAG_CACHE_PATH",
            "GITHUB_REPO",
            "GITHUB_BRANCH",
            "GITHUB_PAT",
            "GITHUB_RAG_MAX_FILES",
            "GITHUB_RAG_MAX_BLOB_CHARS",
            "GITHUB_RAG_INCLUDE_EXTENSIONS",
        ]:
            os.environ.pop(key, None)

    def test_refresh_fetches_github_blob_content_and_filters_to_text_files(self):
        os.environ["GITHUB_REPO"] = "acme/project"
        os.environ["GITHUB_BRANCH"] = "main"

        def fake_http_json(url, method="GET", headers=None, payload=None):
            if url.endswith("/git/trees/main?recursive=1"):
                return {
                    "tree": [
                        {"type": "blob", "path": "README.md", "url": "https://api.github.test/blob/readme", "sha": "sha-readme"},
                        {"type": "blob", "path": "docs/runbook.txt", "url": "https://api.github.test/blob/runbook", "sha": "sha-runbook"},
                        {"type": "blob", "path": "assets/logo.png", "url": "https://api.github.test/blob/logo", "sha": "sha-logo"},
                    ]
                }
            if url == "https://api.github.test/blob/readme":
                return {
                    "encoding": "base64",
                    "content": "IyBUaGlzIHJlcG8gcnVucyBKYXJ2aXMuCkRlcGxveSBmbG93IGFuZCBoZWFsdGggbm90ZXMu",
                    "sha": "sha-readme",
                }
            if url == "https://api.github.test/blob/runbook":
                return {
                    "encoding": "base64",
                    "content": "UnVuYm9vazogcmVzdGFydCBqYXJ2aXMgYW5kIHZlcmlmeSBoZWFsdGgu",
                    "sha": "sha-runbook",
                }
            raise AssertionError(f"unexpected url: {url}")

        with patch.object(self.store, "_http_json", side_effect=fake_http_json):
            report = self.store.refresh()

        self.assertEqual(report["github"], "ok (2)")
        github_items = self.store.data["sources"]["github"]
        self.assertEqual(len(github_items), 2)
        self.assertEqual(github_items[0]["title"], "README.md")
        self.assertIn("deploy flow", github_items[0]["text"].lower())
        self.assertTrue(github_items[0]["url"].startswith("https://github.com/acme/project/blob/main/"))
        self.assertEqual(github_items[0]["sha"], "sha-readme")
        self.assertEqual(github_items[0]["repo"], "acme/project")
        self.assertEqual(github_items[0]["branch"], "main")
        self.assertNotIn("logo.png", [item["title"] for item in github_items])

    def test_refresh_honors_github_file_and_text_caps(self):
        os.environ["GITHUB_REPO"] = "acme/project"
        os.environ["GITHUB_RAG_MAX_FILES"] = "1"
        os.environ["GITHUB_RAG_MAX_BLOB_CHARS"] = "20"

        def fake_http_json(url, method="GET", headers=None, payload=None):
            if "git/trees" in url:
                return {
                    "tree": [
                        {"type": "blob", "path": "README.md", "url": "https://api.github.test/blob/readme"},
                        {"type": "blob", "path": "docs/guide.md", "url": "https://api.github.test/blob/guide"},
                    ]
                }
            return {
                "encoding": "base64",
                "content": "VGhpcyBpcyBhIGxvbmcgZmlsZSBjb250ZW50IHRoYXQgc2hvdWxkIGJlIHRyaW1tZWQu",
                "sha": "sha-any",
            }

        with patch.object(self.store, "_http_json", side_effect=fake_http_json):
            report = self.store.refresh()

        self.assertEqual(report["github"], "ok (1)")
        github_items = self.store.data["sources"]["github"]
        self.assertEqual(len(github_items), 1)
        self.assertLessEqual(len(github_items[0]["text"]), 20)


if __name__ == "__main__":
    unittest.main()
