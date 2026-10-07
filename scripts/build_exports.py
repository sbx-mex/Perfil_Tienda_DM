#!/usr/bin/env python3
"""Compila series auditadas por tienda, DM y región para las descargas del sitio."""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from pathlib import Path

BUSINESS = [
    dict(id="sales", pillar="Negocio", title="Venta ejecutiva", actual="sales", reference="salesBudget", referenceKind="ppto", format="millions", direction="higher", ytd="sum"),
    dict(id="adt", pillar="Negocio", title="ADT", actual="adt", reference="adtAa", referenceKind="aa", format="number", direction="higher", ytd="average"),
    dict(id="aws", pillar="Negocio", title="AWS", actual="aws", reference=None, format="currency", direction="higher", ytd="average"),
    dict(id="ticket", pillar="Negocio", title="Ticket promedio", actual="ticket", reference="ticketAa", secondaryReference="ticketBudget", referenceKind="aa", format="currency1", direction="higher", ytd="average"),
    dict(id="omt-diff", pillar="Negocio", title="OMT vs AA", actual="omtDiff", reference=None, format="number", direction="higher", ytd="average", isDiffOnly=True),
]

def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def aggregate(values, mode="average"):
    clean = [v for v in values if numeric(v)]
    return (sum(clean) if mode == "sum" else sum(clean) / len(clean)) if clean else None

def compile_exports(data, audit):
    if (data.get("schemaVersion") != 2 or audit.get("schemaVersion") != 2
            or audit.get("issueCount") != 0 or not data.get("generatedAt")
            or data["generatedAt"] != audit.get("generatedAt")
            or data.get("directoryPolicy") != "open-only-v1"
            or not data.get("directory")
            or any(row.get("status") != "Abierta" for row in data["directory"])):
        raise ValueError("La exportación requiere un dashboard auditado, vigente y de tiendas Abierta.")
    fields = ("id", "pillar", "title", "actual", "reference", "referenceKind", "format", "direction", "ytd", "isDiffOnly", "secondaryReference")
    metrics = [{**{k: g[k] for k in fields if k in g}, "source": "profile"} for g in data["graphs"]]
    productivity = next(g for g in metrics if g["id"] == "productividad")
    productivity["title"] = "IPLH"
    metrics.insert(metrics.index(productivity) + 1, {**productivity, "id": "tplh", "title": "TPLH", "actual": "TPLH", "reference": "TPLH AA"})
    metrics.extend({**g, "source": "business"} for g in BUSINESS)
    indices = {key: i for i, key in enumerate(data["metricHeaders"])}
    scopes = {"store": {}, "dm": {}, "region": {}}
    for row in data["directory"]:
        scopes["store"][row["cc"]] = [row]
        for scope in ("dm", "region"):
            if row.get(scope): scopes[scope].setdefault(row[scope], []).append(row)
    reports = {scope: {} for scope in scopes}
    for scope, groups in scopes.items():
        for selection, stores in groups.items():
            series = {}
            for graph in metrics:
                output = []
                keys = [graph.get("actual"), graph.get("reference"), graph.get("secondaryReference")]
                for month in data["months"]:
                    rows = [data[graph["source"]].get(s["cc"], {}).get(str(month["id"])) for s in stores]
                    values = []
                    for key in keys:
                        values.append([r.get(key) if graph["source"] == "business" else r[indices[key]]
                                       for r in rows if r is not None] if key else [])
                    mode = "sum" if graph["id"] == "sales" else "average"
                    output.append([*[aggregate(v, mode) for v in values], *[sum(numeric(x) for x in v) for v in values]])
                series[graph["id"]] = output
            partners = [data["partners"].get(s["cc"], {}) for s in stores]
            def total(key): return aggregate([p.get(key) for p in partners], "sum")
            age_count, tenure_count = total("ageCount"), total("tenureCount")
            headcount = total("headcount")
            team = {"headcount": headcount, "coveredStores": sum(numeric(p.get("headcount")) for p in partners),
                    "avgAge": total("ageTotal") / age_count if age_count else None,
                    "avgTenureMonths": total("tenureTotalMonths") / tenure_count if tenure_count else None}
            reports[scope][selection] = {"label": f'{selection} · {stores[0]["store"]}' if scope == "store" else selection,
                                        "storeCount": len(stores), "series": series, "team": team}
    return {"schemaVersion": 1, "generatedAt": data["generatedAt"], "directoryPolicy": "open-only-v1",
            "months": data["months"], "metrics": metrics, "engineInfo": data["engineInfo"],
            "warningCount": audit.get("warningCount", 0), "reports": reports}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(); root = args.root
    output = compile_exports(json.loads((root / "data/dashboard.json").read_text(encoding="utf-8")),
                             json.loads((root / "data/audit.json").read_text(encoding="utf-8")))
    destination = root / "data/exports.json"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent, delete=False) as temporary:
        name = temporary.name
        try:
            json.dump(output, temporary, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            temporary.flush(); os.fsync(temporary.fileno())
        except BaseException:
            os.unlink(name); raise
    try: os.replace(name, destination)
    finally:
        if os.path.exists(name): os.unlink(name)
    print(f"Exportaciones compiladas: {sum(len(v) for v in output['reports'].values())} alcances")

if __name__ == "__main__": main()
