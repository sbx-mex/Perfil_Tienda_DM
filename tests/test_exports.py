import copy
import json
import sys
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_exports import aggregate, compile_exports

class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "data/dashboard.json").read_text(encoding="utf-8"))
        cls.audit = json.loads((ROOT / "data/audit.json").read_text(encoding="utf-8"))
        cls.exports = compile_exports(cls.data, cls.audit)

    def test_missing_is_distinct_from_zero_and_nonfinite_is_ignored(self):
        self.assertIsNone(aggregate([None, float("nan"), float("inf")]))
        self.assertEqual(aggregate([None, 0]), 0)
        self.assertEqual(aggregate([1, 3, None]), 2)

    def test_only_open_directory_scopes_and_no_personal_contact_fields(self):
        self.assertEqual(set(self.exports["reports"]["store"]), {s["cc"] for s in self.data["directory"]})
        self.assertEqual(set(self.exports["reports"]["dm"]), {s["dm"] for s in self.data["directory"] if s["dm"]})
        self.assertNotIn("Email", json.dumps(self.exports))

    def test_store_series_preserves_raw_metric_and_coverage(self):
        cc = self.data["directory"][0]["cc"]
        idx = self.data["metricHeaders"].index("Rolling RY")
        p = self.exports["reports"]["store"][cc]["series"]["rotacion"][0]
        self.assertEqual(p[0], self.data["profile"][cc]["1"][idx])
        self.assertEqual(p[3], 1)

    def test_dm_sales_sum_and_adt_simple_mean_match_the_dashboard(self):
        dm = self.data["directory"][0]["dm"]
        rows = [self.data["business"].get(s["cc"], {}).get("1", {}) for s in self.data["directory"] if s["dm"] == dm]
        report = self.exports["reports"]["dm"][dm]
        self.assertEqual(report["series"]["sales"][0][0], aggregate([r.get("sales") for r in rows], "sum"))
        self.assertEqual(report["series"]["adt"][0][0], aggregate([r.get("adt") for r in rows]))

    def test_team_uses_weighted_people_totals_and_reports_query_coverage(self):
        region = self.data["directory"][0]["region"]
        stores = [s for s in self.data["directory"] if s["region"] == region]
        team = self.exports["reports"]["region"][region]["team"]
        partners = [self.data["partners"].get(s["cc"], {}) for s in stores]
        self.assertEqual(team["headcount"], aggregate([p.get("headcount") for p in partners], "sum"))
        self.assertLessEqual(team["coveredStores"], len(stores))

    def test_mismatched_audit_or_closed_directory_blocks_compilation(self):
        audit = {**self.audit, "generatedAt":"other"}
        with self.assertRaises(ValueError): compile_exports(self.data, audit)
        data = copy.deepcopy(self.data); data["directory"][0]["status"] = "Cierre Temporal"
        with self.assertRaises(ValueError): compile_exports(data, self.audit)

    def test_all_three_pillars_and_both_productivity_options_are_in_contract(self):
        self.assertEqual({g["pillar"] for g in self.exports["metrics"]}, {"Partner","Cliente","Negocio"})
        graphs = {g["id"]:g for g in self.exports["metrics"]}
        self.assertEqual(graphs["tplh"]["actual"], "TPLH")
        self.assertEqual(graphs["rotacion"]["ytd"], "latest")
        self.assertEqual(graphs["sales"]["ytd"], "sum")

    def test_javascript_exports_contract_and_xlsx(self):
        result = subprocess.run(["node", "--test", str(ROOT / "tests/exports.test.cjs")], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == "__main__": unittest.main()
