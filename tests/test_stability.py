from __future__ import annotations

import csv
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
from build_data import clean_cc, load_business, load_export_csv, year_from_period
from stage_site import ASSETS, DATA, FILES, stage


class StabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def write_csv(self, name, rows, encoding="utf-8-sig", delimiter=","):
        text = io.StringIO(newline="")
        text.write('Título del reporte\nFiltro: corte mensual\n')
        writer = csv.DictWriter(text, fieldnames=list(rows[0]), delimiter=delimiter)
        writer.writeheader(); writer.writerows(rows)
        path = self.root / name
        path.write_text(text.getvalue(), encoding=encoding, newline="")
        return path

    def business_paths(self, real_rows, aa_rows=None):
        if aa_rows is None: aa_rows = [{"Mes":"202601", "Tiendas":"38101", "ADT AA":"90", "OMT":"2"}]
        return {"business_real":self.write_csv("real.csv", real_rows), "business_aa":self.write_csv("aa.csv", aa_rows)}

    @staticmethod
    def real(period="202601", **extra):
        return {"Mes":period, "Tiendas":"38101", "ADT Real":"100", "Venta $":"1,100", "Var Ventas vs Ppto (%)":"10%",
                "AWS $":"275", "Ticket Prom Real":"110", "Ticket Prom AA":"100", "Var Ticket vs AA (%)":"10%", **extra}

    def test_export_encoding_order_and_multiline_fields(self):
        row = {"Tiendas":"38101", "Nota":"café, línea\nsegunda", " Mes ":"202601"}
        for encoding in ("utf-8-sig", "utf-16"):
            for delimiter in (",", ";", "\t"):
                with self.subTest(encoding=encoding, delimiter=delimiter):
                    path = self.write_csv("export.csv", [row], encoding, delimiter)
                    self.assertEqual(load_export_csv(path), [{"Tiendas":"38101", "Nota":row["Nota"], "Mes":"202601"}])

    def test_corrupt_csv_is_rejected(self):
        for text in ('Mes,Tiendas,Mes\n202601,38101,202601\n', 'Mes,Tiendas,ADT AA\n202601,38101\n'):
            path = self.root / "broken.csv"; path.write_text(text)
            with self.assertRaises(ValueError): load_export_csv(path)

    def test_quoted_preamble_does_not_choose_the_wrong_delimiter(self):
        path = self.root / "export.csv"
        path.write_text('"Título";"Corte mensual"\n"Mes";"Tiendas";"ADT AA"\n"202601";"38101";"90"\n')
        self.assertEqual(load_export_csv(path), [{"Mes":"202601", "Tiendas":"38101", "ADT AA":"90"}])

    def test_ticket_optional_references_are_blank_and_audited(self):
        warnings = []
        data, audit = load_business(self.business_paths([self.real()]), {"38101"}, warnings)
        row = data["38101"]["1"]
        self.assertEqual(row["ticket"], 110)
        self.assertEqual(row["ticketAa"], 100)
        self.assertEqual(row["salesBudget"], 1000)
        self.assertIsNone(row["ticketBudget"])
        self.assertIsNone(row["ticketBudgetVariance"])
        self.assertEqual(set(audit["optionalMissingHeaders"]), {"Ticket Prom Ppto", "Var Ticket vs Ppto (%)"})
        self.assertTrue(any("opcionales" in warning for warning in warnings))

    def test_ticket_budget_is_preserved_when_exported(self):
        row = self.real(**{"Ticket Prom Ppto":"105", "Var Ticket vs Ppto (%)":"4.76%"})
        data, audit = load_business(self.business_paths([row]), {"38101"}, [])
        self.assertEqual(data["38101"]["1"]["ticketBudget"], 105)
        self.assertAlmostEqual(data["38101"]["1"]["ticketBudgetVariance"], .0476)
        self.assertEqual(audit["optionalMissingHeaders"], [])

    def test_required_metric_still_blocks_bad_exports(self):
        row = self.real(); del row["Venta $"]
        with self.assertRaisesRegex(ValueError, "Venta"):
            load_business(self.business_paths([row]), {"38101"}, [])

    def test_years_are_not_combined_and_unknown_stores_cannot_select_year(self):
        old = self.real("202501", **{"Venta $":"10"})
        new = self.real("202601", **{"Venta $":"20"})
        unknown = self.real("202701", **{"Tiendas":"99999"})
        aa = [{"Mes":"202501", "Tiendas":"38101", "ADT AA":"80", "OMT":"1"}]
        data, audit = load_business(self.business_paths([old, new, unknown], aa), {"38101"}, [])
        self.assertEqual(audit["selectedYear"], 2026)
        self.assertEqual(data["38101"]["1"]["sales"], 20)
        self.assertNotIn("adtAa", data["38101"]["1"])
        self.assertEqual(audit["ignoredYears"], {2025:2})

    def test_duplicate_current_period_is_blocking(self):
        with self.assertRaisesRegex(ValueError, "duplicado"):
            load_business(self.business_paths([self.real(), self.real()]), {"38101"}, [])

    def test_invalid_codes_and_periods_cannot_alias_valid_stores(self):
        self.assertEqual(clean_cc("138101"), "")
        self.assertEqual(clean_cc("CC-38101"), "38101")
        self.assertIsNone(year_from_period("202699"))

    def site_fixture(self):
        for relative in [*FILES, *(f"data/{name}" for name in DATA), *(f"assets/{name}" for name in ASSETS)]:
            path = self.root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("fixture")
        data = {"schemaVersion":2, "generatedAt":"same"}
        audit = {"schemaVersion":2, "generatedAt":"same", "issueCount":0}
        (self.root / "data/dashboard.json").write_text(json.dumps(data))
        (self.root / "data/audit.json").write_text(json.dumps(audit))
        (self.root / "data/exports.json").write_text(json.dumps({"schemaVersion":1,"generatedAt":"same","directoryPolicy":"open-only-v1"}))

    def test_stage_protects_engines_and_source_directories(self):
        self.site_fixture()
        sentinel = self.root / "data/engines/source.csv"; sentinel.parent.mkdir(); sentinel.write_text("original")
        for target in (self.root, self.root / "data/engines", self.root / "scripts/new", self.root / ".github", self.root / "assets/nested"):
            with self.subTest(target=target), self.assertRaises(ValueError): stage(self.root, target)
        self.assertEqual(sentinel.read_text(), "original")

    def test_stage_is_minimal_and_preserves_unrelated_backups(self):
        self.site_fixture()
        unrelated = self.root / ".dist.backup"; unrelated.mkdir(); (unrelated / "keep").write_text("original")
        stage(self.root, self.root / "dist")
        self.assertTrue((self.root / "dist/.nojekyll").is_file())
        self.assertFalse((self.root / "dist/data/engines").exists())
        self.assertEqual((unrelated / "keep").read_text(), "original")

    def test_stage_rejects_mismatched_build_without_replacing_existing_site(self):
        self.site_fixture()
        target = self.root / "dist"; target.mkdir(); (target / "keep").write_text("last good")
        (self.root / "data/audit.json").write_text(json.dumps({"schemaVersion":2, "generatedAt":"different", "issueCount":0}))
        with self.assertRaisesRegex(ValueError, "misma construcción"): stage(self.root, target)
        self.assertEqual((target / "keep").read_text(), "last good")

    def test_stage_rolls_back_when_publication_move_fails(self):
        self.site_fixture()
        target = self.root / "dist"; target.mkdir(); (target / "keep").write_text("last good")
        import os
        real_replace = os.replace
        def fail_new_site(source, destination):
            if Path(source).name == "site": raise OSError("injected failure")
            return real_replace(source, destination)
        with patch("stage_site.os.replace", side_effect=fail_new_site), self.assertRaises(OSError): stage(self.root, target)
        self.assertEqual((target / "keep").read_text(), "last good")

    def test_javascript_failure_and_offline_behaviour(self):
        result = subprocess.run(["node", "--test", str(ROOT / "tests/stability.test.cjs")], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__": unittest.main()
