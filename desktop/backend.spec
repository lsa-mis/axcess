from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata


root = Path(SPECPATH).resolve().parent
source = root / "src"
audit_source = source / "audit"

datas = [
    (str(audit_source / "db" / "migrations"), "audit/db/migrations"),
    (str(audit_source / "rules"), "audit/rules"),
    (str(audit_source / "analyzer" / "vlm" / "prompts"), "audit/analyzer/vlm/prompts"),
    (str(audit_source / "web" / "frontend" / "dist"), "audit/web/frontend/dist"),
    (str(audit_source / "web" / "frontend" / "public"), "audit/web/frontend/public"),
    (str(audit_source / "alfa_runner"), "audit/alfa_runner"),
]
datas += copy_metadata("yoyo-migrations")

hiddenimports = collect_submodules("uvicorn") + collect_submodules("yoyo")

a = Analysis(
    [str(root / "desktop" / "backend_entry.py")],
    pathex=[str(source)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "mypy", "ruff"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="axcess-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="axcess-server",
)
