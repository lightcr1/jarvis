import unittest

from jarvis.llm_utils import trim_to_budget as _trim_to_budget


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


class TrimToBudgetTests(unittest.TestCase):
    def test_under_budget_returns_all(self):
        messages = [_msg("user", "hi"), _msg("assistant", "hello")]
        result = _trim_to_budget(messages, budget=10000)
        self.assertEqual(len(result), 2)

    def test_over_budget_drops_oldest(self):
        long_content = "x" * 400  # ~100 tokens each
        messages = [
            _msg("user", long_content),
            _msg("assistant", long_content),
            _msg("user", long_content),
            _msg("assistant", long_content),
            _msg("user", "short"),
        ]
        result = _trim_to_budget(messages, budget=300)
        self.assertLess(len(result), 5)
        self.assertEqual(result[-1]["content"], "short")

    def test_retains_at_least_two(self):
        long_content = "x" * 40000  # way over any reasonable budget
        messages = [_msg("user", long_content), _msg("assistant", long_content)]
        result = _trim_to_budget(messages, budget=1)
        self.assertEqual(len(result), 2)

    def test_empty_list_ok(self):
        result = _trim_to_budget([], budget=4000)
        self.assertEqual(result, [])

    def test_single_message_not_dropped(self):
        messages = [_msg("user", "x" * 40000)]
        result = _trim_to_budget(messages, budget=1)
        self.assertEqual(len(result), 1)

    def test_exact_budget_not_trimmed(self):
        content = "x" * 400  # 100 estimated tokens
        messages = [_msg("user", content), _msg("assistant", content)]
        result = _trim_to_budget(messages, budget=200)
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
