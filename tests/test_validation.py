from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stage_site import ASSETS, DATA, FILES
from validate_project import run_pipeline, verify_artifact, verify_contract, write_json


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        self.root.mkdir()
        self.data = {
            "schemaVersion": 2, "generatedAt": "2026-10-10T00:00:00Z", "directoryPolicy": "open-only-v1",
            "months": [{"id": 9, "period": "202609", "label": "Septiembre"}],
            "directory": [{"cc": "38101", "status": "Abierta", "dm": "DM de prueba", "region": "Región de prueba"}],
            **{key: {} for key in ("profile", "business", "mix", "partners")},
        }
        sources = {}
        for key in ("directory", "profile", "business_aa", "business_real", "partners", "mix_manifest"):
            name = f"{key}.txt"
            self.put(f"data/engines/{name}", key)
            sources[key] = {"file": name, "bytes": len(key), "sha256": hashlib.sha256(key.encode()).hexdigest()}
        self.audit = {"schemaVersion": 2, "generatedAt": self.data["generatedAt"], "issueCount": 0, "issues": [],
                      "warningCount": 1, "warnings": ["Referencia no informada"], "sources": sources,
                      "directory": {"validStores": 1}, "profile": {"rows": 1}}
        report = {"storeCount": 1, "series": {"tplh": [[0, None, None, 1, 0, 0]]}}
        self.exports = {"schemaVersion": 1, "generatedAt": self.data["generatedAt"], "directoryPolicy": "open-only-v1",
                        "months": self.data["months"], "warningCount": 1, "metrics": [{"id": "tplh"}],
                        "reports": {"store": {"38101": copy.deepcopy(report)}, "dm": {"DM de prueba": copy.deepcopy(report)},
                                    "region": {"Región de prueba": copy.deepcopy(report)}}}
        self.save_contract()

    def put(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def save_contract(self):
        for name, payload in (("dashboard", self.data), ("audit", self.audit), ("exports", self.exports)):
            self.put(f"data/{name}.json", json.dumps(payload, ensure_ascii=False))

    def artifact(self):
        output = self.root / "dist"
        for name in FILES:
            self.put(name, "current")
        for name in ASSETS:
            self.put(f"assets/{name}", "current")
        expected = {*FILES, *(f"data/{name}" for name in DATA), *(f"assets/{name}" for name in ASSETS)}
        for name in expected:
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((self.root / name).read_bytes())
        (output / ".nojekyll").touch()
        return output

    def test_zero_remains_valid_and_source_warnings_are_preserved(self):
        info = verify_contract(self.root)
        self.assertEqual(info["stores"], 1)
        self.assertEqual(info["months"], [9])
        self.assertEqual(info["warnings"], self.audit["warnings"])
        self.assertEqual(info["scopes"], {"store": 1, "dm": 1, "region": 1})

    def test_source_change_after_build_blocks_validation(self):
        self.put("data/engines/profile.txt", "changed")
        with self.assertRaisesRegex(ValueError, "Motor cambiado"):
            verify_contract(self.root)

    def test_mismatched_generation_blocks_validation(self):
        self.exports["generatedAt"] = "old"
        self.save_contract()
        with self.assertRaisesRegex(ValueError, "misma carga"):
            verify_contract(self.root)

    def test_blocking_issue_cannot_be_hidden_by_a_zero_counter(self):
        self.audit["issues"] = ["Error real"]
        self.save_contract()
        with self.assertRaisesRegex(ValueError, "bloqueantes"):
            verify_contract(self.root)

    def test_warning_counter_cannot_hide_a_warning(self):
        self.audit["warningCount"] = 0
        self.save_contract()
        with self.assertRaisesRegex(ValueError, "avisos"):
            verify_contract(self.root)

    def test_missing_and_zero_must_match_their_coverage(self):
        for point in ([0, None, None, 0, 0, 0], [None, None, None, 1, 0, 0]):
            with self.subTest(point=point):
                self.exports["reports"]["store"]["38101"]["series"]["tplh"] = [point]
                self.save_contract()
                with self.assertRaisesRegex(ValueError, "cobertura no coinciden"):
                    verify_contract(self.root)

    def test_incomplete_series_and_scope_are_blocking(self):
        self.exports["reports"]["store"]["38101"]["series"]["tplh"] = []
        self.save_contract()
        with self.assertRaisesRegex(ValueError, "todos los meses"):
            verify_contract(self.root)
        del self.exports["reports"]["store"]["38101"]
        self.save_contract()
        with self.assertRaisesRegex(ValueError, "alcances"):
            verify_contract(self.root)

    def test_nonfinite_json_is_rejected(self):
        self.exports["reports"]["store"]["38101"]["series"]["tplh"][0][0] = float("nan")
        self.save_contract()
        with self.assertRaisesRegex(ValueError, "no finito"):
            verify_contract(self.root)

    def test_source_escape_is_rejected(self):
        self.audit["sources"]["profile"]["file"] = "../outside.txt"
        self.save_contract()
        with self.assertRaisesRegex(ValueError, "Ruta de motor"):
            verify_contract(self.root)

    def test_exact_artifact_is_valid_and_current(self):
        info = verify_artifact(self.root, self.artifact())
        self.assertEqual(info["files"], len(FILES) + len(DATA) + len(ASSETS) + 1)
        self.assertFalse(info["rawEnginesPublished"])

    def test_raw_engine_extra_file_or_missing_file_blocks_artifact(self):
        output = self.artifact()
        extra = self.put("dist/data/engines/raw.csv", "raw")
        with self.assertRaisesRegex(ValueError, "archivos extra"):
            verify_artifact(self.root, output)
        extra.unlink()
        (output / "index.html").unlink()
        with self.assertRaisesRegex(ValueError, "incompleto"):
            verify_artifact(self.root, output)

    def test_changed_artifact_is_blocking(self):
        output = self.artifact()
        self.put("dist/data/dashboard.json", "{}")
        with self.assertRaisesRegex(ValueError, "no coincide"):
            verify_artifact(self.root, output)

    def test_failed_command_stops_following_steps_and_cannot_report_green(self):
        failure = subprocess.CompletedProcess([], 1, "fallo real", "")
        with patch("validate_project.shutil.which", return_value="node"), \
                patch("validate_project.subprocess.check_output", return_value="v24.19.0"), \
                patch("validate_project.subprocess.run", return_value=failure) as run, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            report = run_pipeline(self.root, self.root / "dist")
        self.assertEqual(report["status"], "ROJO")
        self.assertEqual(report["steps"][1]["status"], "ROJO")
        self.assertTrue(all(s["status"] == "NO EJECUTADO" for s in report["steps"][2:]))
        self.assertEqual(run.call_count, 1)

    def test_zero_executed_tests_cannot_report_green(self):
        def command(args, **kwargs):
            if "scripts/cleanup_obsolete.py" in args:
                return subprocess.CompletedProcess(args, 0, "{}", "")
            return subprocess.CompletedProcess(args, 0, "", "Ran 0 tests\nOK")
        with patch("validate_project.shutil.which", return_value="node"), \
                patch("validate_project.subprocess.check_output", return_value="v24.19.0"), \
                patch("validate_project.subprocess.run", side_effect=command), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            report = run_pipeline(self.root, self.root / "dist")
        self.assertEqual(report["status"], "ROJO")
        self.assertEqual(report["steps"][7]["status"], "ROJO")
        self.assertEqual(report["steps"][8]["status"], "NO EJECUTADO")

    def test_report_path_cannot_overwrite_a_source_file(self):
        source = self.put("keep.py", "original")
        result = subprocess.run([sys.executable, str(ROOT / "scripts/validate_project.py"), "--root", str(self.root),
                                 "--report", str(source)], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(source.read_text(), "original")

    def test_report_replacement_is_atomic_on_write_failure(self):
        target = Path(self.temporary.name) / "report.json"
        target.write_text("previous")
        with patch("validate_project.os.replace", side_effect=OSError("injected")), self.assertRaises(OSError):
            write_json(target, {"status": "VERDE"})
        self.assertEqual(target.read_text(), "previous")


if __name__ == "__main__":
    unittest.main()
