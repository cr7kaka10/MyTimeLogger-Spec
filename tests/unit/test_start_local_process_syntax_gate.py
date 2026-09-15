import py_compile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class StartLocalProcessSyntaxGateTests(unittest.TestCase):
    def test_server_entry_is_currently_parseable(self):
        py_compile.compile(str(ROOT / "server" / "server.py"), doraise=True)

    def test_server_syntax_gate_runs_before_process_creation(self):
        script = (ROOT / "scripts" / "start-local-process.ps1").read_text(encoding="utf-8")
        self.assertIn("& python -m py_compile $serverEntry", script)
        self.assertLess(script.index("& python -m py_compile $serverEntry"), script.index("Start-Process -FilePath 'cmd.exe'"))


if __name__ == "__main__":
    unittest.main()
