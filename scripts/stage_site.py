#!/usr/bin/env python3
"""Prepara un artefacto mínimo de GitHub Pages sin publicar motores crudos."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

FILES = ("index.html", "styles.css", "operational.css", "app.js", "exports.js", "exports.css", "manifest.webmanifest", "sw.js")
DATA = ("dashboard.json", "audit.json", "exports.json")
ASSETS = ("icon.svg", "icon-192.png", "icon-512.png", "vendor/pdf-lib-1.17.1.min.js", "vendor/pdf-lib-LICENSE.txt", "vendor/jszip-3.10.1.min.js", "vendor/jszip-LICENSE.txt")


def copy_file(root: Path, staged: Path, relative: Path) -> None:
    source = root / relative
    if not source.is_file() or source.is_symlink(): raise ValueError(f"Archivo requerido inválido: {relative}")
    destination = staged / relative; destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def stage(root: Path, output: Path) -> None:
    if output.is_symlink(): raise ValueError("La salida no puede ser un enlace simbólico.")
    root = root.resolve(); output = output.resolve()
    protected = [root / name for name in ("data", "assets", "scripts", "tests", ".git", ".github")]
    if (root not in output.parents or any(path == output or path in output.parents or output in path.parents for path in protected)
            or (output.exists() and not output.is_dir())):
        raise ValueError("La salida debe ser una carpeta segura dentro del proyecto.")
    with tempfile.TemporaryDirectory(prefix="perfil-stage-", dir=root) as temporary:
        staged = Path(temporary) / "site"; staged.mkdir()
        for name in FILES: copy_file(root, staged, Path(name))
        for name in DATA: copy_file(root, staged, Path("data") / name)
        for name in ASSETS: copy_file(root, staged, Path("assets") / name)
        data = json.loads((staged / "data/dashboard.json").read_text(encoding="utf-8"))
        audit = json.loads((staged / "data/audit.json").read_text(encoding="utf-8"))
        exports = json.loads((staged / "data/exports.json").read_text(encoding="utf-8"))
        if (data.get("schemaVersion") != 2 or audit.get("schemaVersion") != 2 or audit.get("issueCount") != 0
                or not data.get("generatedAt") or data["generatedAt"] != audit.get("generatedAt")):
            raise ValueError("Dashboard y auditoría deben pertenecer a la misma construcción válida.")
        if (exports.get("schemaVersion") != 1 or exports.get("generatedAt") != data["generatedAt"]
                or exports.get("directoryPolicy") != "open-only-v1"):
            raise ValueError("Exportaciones y dashboard deben pertenecer a la misma construcción válida.")
        (staged / ".nojekyll").touch()
        backup = Path(temporary) / "backup"
        if output.exists(): os.replace(output, backup)
        try: os.replace(staged, output)
        except BaseException:
            if backup.exists() and not output.exists(): os.replace(backup, output)
            raise
        else:
            if backup.exists(): shutil.rmtree(backup)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1]); parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args(); root=args.root.resolve(); output=args.output if args.output.is_absolute() else root/args.output
    try: stage(root, output)
    except (OSError, ValueError) as error: raise SystemExit(f"Preparación cancelada: {error}") from error
    print(f"Sitio preparado: {output.resolve()}")


if __name__ == "__main__": main()
