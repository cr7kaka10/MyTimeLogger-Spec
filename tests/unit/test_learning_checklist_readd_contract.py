import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class LearningChecklistReaddContractTests(unittest.TestCase):
    def test_missing_confirmed_provider_task_is_rejected_before_linking_learning(self):
        source = (ROOT / "server" / "server.py").read_text(encoding="utf-8")
        guard = source.index('if operation == "create" and not provider_task:')
        link = source.index('store.link_learning_checklist_task(user_id, learning_task_id, str(result["result_task_id"]))')
        self.assertLess(guard, link)
        self.assertIn('return {**result, "status": "failed", "error_code": "provider_task_not_found"}', source[guard:link])


if __name__ == "__main__":
    unittest.main()
