from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from build_data import build, clean_cc, month_from_profile, year_from_period  # noqa: E402


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(); folder=Path(cls.temporary.name)
        cls.payload,cls.audit=build(ROOT,folder/"dashboard.json",folder/"audit.json")

    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    def test_real_coverage(self):
        stores=len(self.payload["directory"])
        self.assertGreater(stores,0)
        for engine in ("profile","business","partners","mix"):
            self.assertGreater(self.audit[engine]["matchedStores"],0,engine)
            self.assertLessEqual(self.audit[engine]["matchedStores"],stores,engine)

    def test_month_contract(self):
        months=self.payload["months"]
        ids=[month["id"] for month in months]
        self.assertEqual(ids,sorted(set(ids)))
        self.assertTrue(ids)
        self.assertTrue(all(1<=month<=12 for month in ids))
        expected_year=max(int(year) for year in self.audit["business"]["years"])
        self.assertEqual([month["period"] for month in months],[f"{expected_year}{month:02d}" for month in ids])
        self.assertEqual(self.audit["profile"]["monthHeader"],"MES_NUM")
        self.assertTrue(set(self.audit["profile"]["months"]).issubset(set(ids)))
        self.assertTrue(all(value>0 for value in self.audit["profile"]["months"].values()))

    def test_month_parser_is_future_proof(self):
        for raw,expected in ((1,1),(12,12),(202601,1),("202612",12),("1_ene",1),("7_jul",7)):
            self.assertEqual(month_from_profile(raw),expected,raw)
        self.assertIsNone(month_from_profile(13))
        self.assertEqual(year_from_period("202701"),2027)
        self.assertIsNone(year_from_period("Enero"))

    def test_new_cecos_are_normalized_without_catalogs(self):
        for raw,expected in ((43205,"43205"),("CC-43205","43205"),("205","00205")):
            self.assertEqual(clean_cc(raw),expected)

    def test_minus_100_is_blank(self):
        self.assertGreater(sum(self.audit["profile"]["minus100Blanked"].values()),0)
        headers=self.payload["metricHeaders"]
        for cc,months in self.payload["profile"].items():
            for values in months.values():
                for header in ("VMT","VMT AA","OMT","OMT AA"):
                    self.assertNotEqual(values[headers.index(header)],-1,cc)

    def test_dt_is_seconds(self):
        index=self.payload["metricHeaders"].index("DT Time")
        values=[row[index] for months in self.payload["profile"].values() for row in months.values() if row[index] is not None]
        self.assertTrue(values)
        self.assertTrue(all(20<=value<=1800 for value in values))
        self.assertIn(75.0,values)  # 01:15 = un minuto con quince segundos

    def test_only_verified_keys_are_emitted(self):
        valid_cc={item["cc"] for item in self.payload["directory"]}
        for name in ("profile","business","mix","partners"):
            self.assertTrue(set(self.payload[name]).issubset(valid_cc),name)

    def test_mix_parts_match_manifest_and_fit_github(self):
        manifest=json.loads((ROOT/"data/engines/mix/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(sum(part["rows"] for part in manifest["parts"]),manifest["rows"])
        self.assertEqual(self.audit["mix"]["sourceRows"],manifest["rows"])
        for part in manifest["parts"]:
            path=ROOT/"data/engines/mix"/part["file"]
            self.assertTrue(path.is_file())
            self.assertLess(path.stat().st_size,25_000_000)

    def test_every_project_file_is_under_25mb(self):
        oversized=[path for path in ROOT.rglob("*") if path.is_file() and "dist" not in path.parts and path.stat().st_size>=25_000_000]
        self.assertEqual(oversized,[])

    def test_static_javascript_is_valid(self):
        for name in ("app.js", "sw.js"):
            completed=subprocess.run(["node","--check",str(ROOT/name)],capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stderr)

    def test_html_uses_local_assets_only(self):
        class Collector(HTMLParser):
            def __init__(self): super().__init__(); self.urls=[]
            def handle_starttag(self,tag,attrs):
                values=dict(attrs)
                if tag in {"script","link","img"}: self.urls.append(values.get("src") or values.get("href") or "")
        collector=Collector(); collector.feed((ROOT/"index.html").read_text(encoding="utf-8"))
        self.assertTrue(collector.urls)
        self.assertTrue(all(not url.startswith(("http://","https://","//")) for url in collector.urls),collector.urls)

    def test_simple_navigation_is_complete(self):
        html=(ROOT/"index.html").read_text(encoding="utf-8")
        for obsolete in ("quick-nav","qualityButton","printButton","periodSelect","instructions-panel","PILAR 01","<span>01</span>"):
            self.assertNotIn(obsolete,html)
        for label in ("Partner","Cliente","Negocio","Tendencia","Brecha"):
            self.assertIn(label,html)

    def test_ticket_supports_aa_and_budget(self):
        rows=[row for months in self.payload["business"].values() for row in months.values()]
        self.assertTrue(any(row.get("ticket") is not None for row in rows))
        self.assertTrue(any(row.get("ticketAa") is not None for row in rows))
        for header,key in (("Ticket Prom Ppto","ticketBudget"),("Var Ticket vs Ppto (%)","ticketBudgetVariance")):
            if header not in self.audit["business"]["realHeaders"]:
                self.assertIn(header,self.audit["business"]["optionalMissingHeaders"])
                self.assertTrue(all(row.get(key) is None for row in rows))
            else:
                self.assertTrue(any(row.get(key) is not None for row in rows))
        app=(ROOT/"app.js").read_text(encoding="utf-8")
        self.assertIn("secondaryReference:'ticketBudget'",app)

    def test_vmt_and_omt_are_business_metrics(self):
        graphs=[graph for graph in self.payload["graphs"] if graph["title"].upper() in {"VMT","OMT"}]
        self.assertGreaterEqual(len(graphs),2)
        self.assertTrue(all(graph["pillar"]=="Negocio" for graph in graphs))

    def test_cleanup_covers_all_known_root_legacy_files(self):
        manifest=json.loads((ROOT/"scripts/obsolete-files.json").read_text(encoding="utf-8"))
        expected={"data.js","Store_Master_Audit.csv","README.txt","manifest.json","apple-touch-icon.png","icon-192.png","icon-512.png","icon.svg","style.css","data/engines/Base_Mix.csv"}
        self.assertEqual(set(manifest["obsoleteFiles"]),expected)
        workflow=(ROOT/".github/workflows/cleanup-obsolete.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_run:",workflow)
        self.assertIn("Validar y publicar Perfil de Tienda",workflow)

    def test_audit_has_no_blocking_issues(self):
        self.assertEqual(self.audit["issueCount"],0)
        self.assertEqual(self.audit["warningCount"],len(self.audit["warnings"]))


if __name__=="__main__": unittest.main()
