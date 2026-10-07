#!/usr/bin/env python3
"""Retira sólo legados enumerados, después de auditar las dependencias vigentes."""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import stat
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ALLOWED = {"data.js", "Store_Master_Audit.csv", "README.txt", "manifest.json", "apple-touch-icon.png", "icon-192.png", "icon-512.png", "icon.svg", "style.css", "data/engines/Base_Mix.csv"}
PROTECTED = {"index.html", "styles.css", "operational.css", "exports.css", "app.js", "exports.js", "sw.js", "manifest.webmanifest", "data/dashboard.json", "data/audit.json", "data/exports.json"}
SOURCE_FILES = {"index.html", "app.js", "exports.js", "sw.js", "styles.css", "operational.css", "exports.css", "manifest.webmanifest"}
EXTENSIONS = {".js", ".css", ".html", ".webmanifest", ".json", ".svg", ".png", ".csv", ".xlsx", ".txt"}


def safe_path(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative):
        raise ValueError(f"Ruta fuera de alcance: {relative}")
    path = root
    for part in relative.parts:
        path /= part
        if path.is_symlink(): raise ValueError(f"No se permiten enlaces simbólicos: {relative}")
    if root not in path.resolve().parents: raise ValueError(f"Ruta fuera del proyecto: {relative}")
    return path


def candidates(root: Path, manifest: Path) -> list[tuple[str, Path]]:
    payload = json.loads(safe_path(root, manifest).read_text(encoding="utf-8"))
    raw = payload.get("obsoleteFiles") if isinstance(payload, dict) else None
    if not isinstance(raw, list) or not raw or any(not isinstance(item, str) for item in raw):
        raise ValueError("Manifiesto inválido")
    if len(raw) != len(set(raw)) or len(raw) > 50: raise ValueError("Manifiesto duplicado o demasiado amplio")
    approved = []
    for item in raw:
        relative = Path(item)
        if relative.as_posix() != item or item in PROTECTED or item not in ALLOWED:
            raise ValueError(f"Ruta fuera de alcance: {item}")
        target = safe_path(root, relative)
        if target.exists() and not stat.S_ISREG(target.stat().st_mode):
            raise ValueError(f"El legado debe ser un archivo regular: {item}")
        approved.append((item, target))
    return approved


class HtmlReferences(HTMLParser):
    def __init__(self): super().__init__(); self.references = []
    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in {"src", "href", "poster"} and value: self.references.append(value)


def string_values(value):
    if isinstance(value, str): yield value
    elif isinstance(value, list):
        for item in value: yield from string_values(item)
    elif isinstance(value, dict):
        for item in value.values(): yield from string_values(item)


def local_reference(value: str, source: str) -> str | None:
    if any(char in value for char in ("\n", "\r", "${", "\\")): return None
    url = urlsplit(value)
    if url.scheme or url.netloc or not url.path: return None
    path = unquote(url.path)
    if Path(path).suffix.lower() not in EXTENSIONS: return None
    relative = Path(path.lstrip("/")) if path.startswith("/") else Path(source).parent / path
    parts = []
    for part in relative.parts:
        if part == "..":
            if not parts: return None
            parts.pop()
        elif part != ".": parts.append(part)
    return "/".join(parts)


def references(root: Path, approved: list[tuple[str, Path]]) -> tuple[list[str], list[str]]:
    obsolete = {name for name, _ in approved}; found = []; checked = []; queue = set(SOURCE_FILES)
    # La lista del artefacto también es una dependencia: leer constantes sin ejecutar código.
    stage = root / "scripts/stage_site.py"
    if stage.is_file():
        for node in ast.parse(stage.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name in {"FILES", "DATA", "ASSETS"}:
                    values = ast.literal_eval(node.value)
                    prefix = {"FILES":"", "DATA":"data/", "ASSETS":"assets/"}[name]
                    for value in values:
                        relative = prefix + value
                        if relative in obsolete: found.append(f"scripts/stage_site.py -> {relative}")
                        if Path(relative).suffix in {".html", ".js", ".css", ".webmanifest"}: queue.add(relative)
        checked.append("scripts/stage_site.py")
    while queue:
        source = sorted(queue)[0]; queue.remove(source)
        if source in checked: continue
        file = safe_path(root, Path(source))
        if not file.is_file(): continue
        checked.append(source)
        text = file.read_text(encoding="utf-8")
        if source.endswith(".html"):
            parser = HtmlReferences(); parser.feed(text); values = parser.references
        elif source.endswith(".webmanifest"):
            values = list(string_values(json.loads(text)))
        elif source.endswith(".css"):
            values = [a or b for a, b in re.findall(r'''url\(\s*["']?([^\s)'";]+)["']?\s*\)|@import\s+["']([^"']+)["']''', text)]
        else:
            values = [m.group(2) for m in re.finditer(r'''(["'`])((?:\\.|(?!\1).)*?)\1''', text)]
        for value in values:
            target = local_reference(value, source)
            if target in obsolete: found.append(f"{source} -> {target}")
            elif target and Path(target).suffix in {".html", ".js", ".css", ".webmanifest"}:
                queue.add(target)
    # Los motores son usados por Python; el archivo histórico de Mix nunca debe ser su fuente vigente.
    for source in ("scripts/build_data.py", "scripts/build_exports.py"):
        file = root / source
        if not file.is_file(): continue
        checked.append(source)
        def path_expression(node):
            if isinstance(node, ast.Name): return {"root":"", "ROOT":"", "engines":"data/engines"}.get(node.id)
            if isinstance(node, ast.Constant) and isinstance(node.value, str): return node.value
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                left, right = path_expression(node.left), path_expression(node.right)
                if left is not None and right is not None: return (Path(left) / right).as_posix()
            return None
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                target = path_expression(node)
                if target in obsolete: found.append(f"{source} -> {target}")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "/" in node.value and node.value in obsolete: found.append(f"{source} -> {node.value}")
    return sorted(set(found)), sorted(checked)


def write_report(path: Path | None, report: dict) -> None:
    if path is None: return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temporary = Path(file.name); json.dump(report, file, ensure_ascii=False, indent=2); file.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists(): temporary.unlink()


def clean(root: Path, manifest: Path, apply=False, report_path: Path | None = None) -> dict:
    root = root.resolve(); approved = candidates(root, manifest)
    found, checked = references(root, approved)
    if found: raise ValueError("Legados aún referenciados; no se borró nada: " + "; ".join(found))
    if report_path is not None and (report_path.resolve() == root or root in report_path.resolve().parents):
        raise ValueError("El reporte debe guardarse fuera del proyecto para no sobrescribir archivos vigentes")
    present = [name for name, target in approved if target.is_file()]
    report = {"schemaVersion":1, "mode":"apply" if apply else "audit", "approved":[name for name, _ in approved],
              "removed":[], "remaining":present, "missing":[name for name, target in approved if not target.exists()],
              "references":found, "checkedSources":checked}
    if not apply:
        write_report(report_path, report); return report
    with tempfile.TemporaryDirectory(prefix="perfil-cleanup-", dir=root) as temporary:
        moved = []
        try:
            for name, target in approved:
                if target.is_file():
                    safe_path(root, Path(name))
                    if not stat.S_ISREG(target.lstat().st_mode): raise ValueError(f"El legado cambió durante la auditoría: {name}")
                    backup = Path(temporary) / name; backup.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(target, backup); moved.append((target, backup)); report["removed"].append(name)
            report["remaining"] = [name for name, target in approved if target.exists()]
            if report["remaining"]: raise ValueError("Persisten archivos legados; se revierte la limpieza")
            write_report(report_path, report)
        except BaseException:
            for target, backup in reversed(moved):
                if not target.exists() and backup.exists(): os.replace(backup, target)
            raise
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, default=Path("scripts/obsolete-files.json"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--check-clean", action="store_true")
    parser.add_argument("--print-candidates", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(); root = args.root.resolve()
    try:
        if args.print_candidates:
            print("\n".join(name for name, _ in candidates(root, args.manifest))); return
        report = clean(root, args.manifest, args.apply, args.report)
        print(json.dumps(report, ensure_ascii=False))
        if args.check_clean and report["remaining"]: raise ValueError("Persisten archivos obsoletos")
    except (OSError, ValueError, SyntaxError) as error: raise SystemExit(f"Limpieza cancelada: {error}") from error


if __name__ == "__main__": main()
