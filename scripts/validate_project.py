#!/usr/bin/env python3
"""Ejecuta la carga completa. Sólo informa VERDE si todas las comprobaciones pasan."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from stage_site import ASSETS, DATA, FILES

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read_json(path: Path) -> dict:
    def reject(value):
        raise ValueError(f"Número JSON no finito: {value}")
    result = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)
    if not isinstance(result, dict):
        raise ValueError(f"Se esperaba un objeto JSON: {path.name}")
    return result


def verify_contract(root: Path) -> dict:
    data = read_json(root / "data/dashboard.json")
    audit = read_json(root / "data/audit.json")
    exports = read_json(root / "data/exports.json")
    if (data.get("schemaVersion") != 2 or audit.get("schemaVersion") != 2
            or exports.get("schemaVersion") != 1 or not data.get("generatedAt")
            or data["generatedAt"] != audit.get("generatedAt")
            or data["generatedAt"] != exports.get("generatedAt")
            or data.get("directoryPolicy") != "open-only-v1"
            or exports.get("directoryPolicy") != "open-only-v1"):
        raise ValueError("Dashboard, auditoría y exportaciones no corresponden a la misma carga.")
    if audit.get("issueCount") != 0 or audit.get("issues") != []:
        raise ValueError("La auditoría contiene errores bloqueantes.")
    warnings = audit.get("warnings")
    if not isinstance(warnings, list) or audit.get("warningCount") != len(warnings) or exports.get("warningCount") != len(warnings):
        raise ValueError("Los avisos de origen están incompletos o no coinciden.")
    months = data.get("months")
    if not isinstance(months, list) or not months or months != exports.get("months"):
        raise ValueError("Periodos incompletos o distintos entre dashboard y exportaciones.")
    ids = [month["id"] for month in months]
    if ids != sorted(set(ids)) or any(type(value) is not int or not 1 <= value <= 12 for value in ids):
        raise ValueError("Periodos duplicados, desordenados o fuera del rango 1–12.")
    if any(not re.fullmatch(r"20\d{4}", str(m["period"])) or int(m["period"][-2:]) != m["id"] for m in months):
        raise ValueError("El mes no coincide con su periodo YYYYMM.")
    directory = data.get("directory")
    if not isinstance(directory, list) or not directory or any(s.get("status") != "Abierta" or not s.get("cc") for s in directory):
        raise ValueError("El directorio debe contener sólo tiendas abiertas con CeCo.")
    cecos = {s["cc"] for s in directory}
    if len(cecos) != len(directory) or audit.get("directory", {}).get("validStores") != len(directory):
        raise ValueError("CeCos duplicados o conteo de tiendas inconsistente.")
    for engine in ("profile", "business", "mix", "partners"):
        if not isinstance(data.get(engine), dict) or not set(data[engine]).issubset(cecos):
            raise ValueError(f"Motor fuera del directorio vigente: {engine}")
    sources = audit.get("sources")
    required = {"directory", "profile", "business_aa", "business_real", "partners", "mix_manifest"}
    if not isinstance(sources, dict) or not required.issubset(sources):
        raise ValueError("Faltan huellas de los motores auditados.")
    engines = (root / "data/engines").resolve()
    for name, source in sources.items():
        relative = Path(source["file"])
        path = engines / relative
        if relative.is_absolute() or ".." in relative.parts or path.is_symlink() or engines not in path.resolve().parents:
            raise ValueError(f"Ruta de motor inválida: {name}")
        if not path.is_file() or path.stat().st_size != source["bytes"] or digest(path) != source["sha256"]:
            raise ValueError(f"Motor cambiado después de construir los datos: {name}")
    metrics = exports.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("Faltan indicadores exportables.")
    metric_ids = {metric["id"] for metric in metrics}
    if len(metric_ids) != len(metrics):
        raise ValueError("Indicadores exportables duplicados.")
    reports = exports.get("reports", {})
    if set(reports) != {"store", "dm", "region"}:
        raise ValueError("Falta un alcance de exportación.")
    counts = {}
    for scope in ("store", "dm", "region"):
        groups = {}
        for store in directory:
            key = store["cc"] if scope == "store" else store.get(scope)
            if key:
                groups[key] = groups.get(key, 0) + 1
        if set(reports[scope]) != set(groups):
            raise ValueError(f"Los alcances de {scope} no coinciden con el directorio.")
        counts[scope] = len(groups)
        for selection, report in reports[scope].items():
            if report.get("storeCount") != groups[selection] or set(report.get("series", {})) != metric_ids:
                raise ValueError(f"Cobertura o indicadores incompletos: {scope}/{selection}")
            for metric, series in report["series"].items():
                if len(series) != len(months):
                    raise ValueError(f"Serie sin todos los meses: {scope}/{selection}/{metric}")
                for point in series:
                    if not isinstance(point, list) or len(point) != 6:
                        raise ValueError(f"Punto de serie incompleto: {metric}")
                    for value, count in zip(point[:3], point[3:]):
                        if type(count) is not int or not 0 <= count <= groups[selection]:
                            raise ValueError(f"Conteo de cobertura inválido: {metric}")
                        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                            raise ValueError(f"Valor no numérico o no finito: {metric}")
                        if (value is None) != (count == 0):
                            raise ValueError(f"Dato faltante y cobertura no coinciden: {metric}")
    return {"generatedAt": data["generatedAt"], "stores": len(directory), "months": ids,
            "profileRows": audit["profile"]["rows"], "scopes": counts,
            "sourceCount": len(sources), "issueCount": 0, "warningCount": len(warnings), "warnings": warnings}


def verify_artifact(root: Path, output: Path) -> dict:
    output = output.resolve()
    protected = [root / name for name in ("data", "assets", "scripts", "tests", ".git", ".github")]
    if (root not in output.parents or any(p == output or p in output.parents or output in p.parents for p in protected)):
        raise ValueError("Ruta de artefacto fuera de alcance.")
    expected = {*FILES, *(f"data/{name}" for name in DATA), *(f"assets/{name}" for name in ASSETS), ".nojekyll"}
    entries = list(output.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ValueError("El artefacto contiene enlaces simbólicos.")
    actual = {path.relative_to(output).as_posix() for path in entries if path.is_file()}
    if actual != expected or (output / "data/engines").exists():
        raise ValueError(f"Artefacto incompleto o con archivos extra: faltan {sorted(expected-actual)}, sobran {sorted(actual-expected)}")
    if (output / ".nojekyll").stat().st_size:
        raise ValueError("El marcador .nojekyll debe estar vacío.")
    for relative in expected - {".nojekyll"}:
        if digest(output / relative) != digest(root / relative):
            raise ValueError(f"El artefacto no coincide con el archivo validado: {relative}")
    return {"files": len(expected), "bytes": sum((output / name).stat().st_size for name in expected), "rawEnginesPublished": False}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            json.dump(payload, file, ensure_ascii=False, allow_nan=False, indent=2)
            file.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def run_pipeline(root: Path, output: Path) -> dict:
    report = {"schemaVersion": 1, "startedAt": datetime.now(UTC).isoformat(), "status": "ROJO", "steps": []}
    steps = [
        ("entorno", None),
        ("dependencias", [sys.executable, "-m", "pip", "check"]),
        ("limpieza", [sys.executable, "scripts/cleanup_obsolete.py", "--apply", "--check-clean"]),
        ("tamano_archivos", [sys.executable, "scripts/check_file_sizes.py"]),
        ("carga_python", [sys.executable, "scripts/build_data.py"]),
        ("exportaciones", [sys.executable, "scripts/build_exports.py"]),
        ("contrato_y_huellas", None),
        ("pruebas_funcionales", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"]),
        ("preparar_sitio", [sys.executable, "scripts/stage_site.py", "--output", str(output)]),
        ("artefacto", None),
    ]
    for index, (name, command) in enumerate(steps):
        start = time.monotonic()
        result = {"name": name, "status": "ROJO"}
        report["steps"].append(result)
        print(f"[{index+1}/{len(steps)}] {name}…", flush=True)
        try:
            if name == "entorno":
                if sys.version_info < (3, 12) or not shutil.which("node"):
                    raise ValueError("Se requieren Python 3.12 o superior y Node.js 22 o superior.")
                version = subprocess.check_output(["node", "--version"], text=True).strip()
                if int(version.lstrip("v").split(".")[0]) < 22:
                    raise ValueError("Se requiere Node.js 22 o superior para las pruebas funcionales.")
                report["runtime"] = {"python": sys.version.split()[0], "node": version}
            elif name == "contrato_y_huellas":
                report["data"] = verify_contract(root)
            elif name == "artefacto":
                report["artifact"] = verify_artifact(root, output)
            else:
                completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=1200)
                log = completed.stdout + completed.stderr
                if completed.returncode:
                    print(log, flush=True)
                    raise ValueError(f"Código de salida {completed.returncode}: {name}")
                if name == "limpieza":
                    report["cleanup"] = json.loads(completed.stdout)
                if name == "pruebas_funcionales":
                    match = re.search(r"Ran (\d+) tests?", log)
                    if not match or int(match[1]) == 0:
                        raise ValueError("No se ejecutaron las pruebas funcionales.")
                    report["tests"] = {"python": int(match[1]), "failures": 0}
                if name in {"carga_python", "exportaciones", "pruebas_funcionales"}:
                    print(log.strip(), flush=True)
            result["status"] = "VERDE"
            print(f"VERDE: {name}", flush=True)
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            result["error"] = str(error)
            report["steps"].extend({"name": n, "status": "NO EJECUTADO"} for n, _ in steps[index+1:])
            print(f"ROJO: {name}: {error}", file=sys.stderr, flush=True)
            break
        finally:
            result["seconds"] = round(time.monotonic() - start, 3)
    if all(step["status"] == "VERDE" for step in report["steps"]):
        report["status"] = "VERDE"
    report["finishedAt"] = datetime.now(UTC).isoformat()
    return report


def append_summary(report: dict, path: Path) -> None:
    lines = [f"## Validación Python: {report['status']}", "", "| Comprobación | Resultado |", "|---|---|"]
    lines.extend(f"| {s['name']} | {s['status']} |" for s in report["steps"])
    if "data" in report:
        info = report["data"]
        lines += ["", f"Tiendas: {info['stores']}. Meses: {', '.join(map(str, info['months']))}. Errores bloqueantes: {info['issueCount']}."]
        lines += ["", f"Avisos de origen: {info['warningCount']}."]
        lines.extend(f"- {warning}" for warning in info["warnings"])
    if "tests" in report:
        lines += ["", f"Pruebas Python: {report['tests']['python']}. Fallas: {report['tests']['failures']}."]
    with path.open("a", encoding="utf-8") as target:
        target.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=Path("dist"))
    parser.add_argument("--report", type=Path, help="Reporte JSON fuera del repositorio.")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.report and (args.report.resolve() == root or root in args.report.resolve().parents):
        parser.error("El reporte debe guardarse fuera del repositorio para no sobrescribir fuentes.")
    output = args.output if args.output.is_absolute() else root / args.output
    report = run_pipeline(root, output)
    if args.report:
        write_json(args.report, report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        append_summary(report, Path(os.environ["GITHUB_STEP_SUMMARY"]))
    print(f"RESULTADO: {report['status']}", flush=True)
    return 0 if report["status"] == "VERDE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
