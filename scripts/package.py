"""Package existing KiCad jobset exports for each assembly/coating combination."""

from datetime import datetime, timezone
from fnmatch import fnmatchcase
import json
import os
from pathlib import Path
import re
import sys
from zipfile import ZIP_DEFLATED, ZipFile


def files_in(directory):
    return sorted(path for path in directory.rglob("*") if path.is_file())


def child_directory(parent, name, required=False):
    matches = [p for p in parent.iterdir() if p.is_dir() and p.name.casefold() == name]
    if len(matches) > 1 or (required and not matches):
        raise ValueError(f"Expected exactly one {name}/ directory in {parent}")
    return matches[0] if matches else None


def is_coat_gerber(path):
    return "coat" in path.name.casefold() and path.suffix.casefold() in {
        ".gbr", ".ger", ".gerber"
    }


def build_packages(root, revision, exclude_patterns="", timestamp=None):
    root = Path(root).resolve()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", revision):
        raise ValueError("Release tag must be a hardware revision without slashes")
    prod_dirs = sorted(p for p in root.iterdir()
                       if p.is_dir() and p.name.casefold().endswith("-prod"))
    if len(prod_dirs) > 1:
        prod_dirs = [p for p in prod_dirs if revision.casefold() in p.name.casefold()]
    if len(prod_dirs) != 1:
        raise ValueError(f"Expected exactly one *-prod directory for revision {revision}")
    prod = prod_dirs[0]
    project = prod.name[:-5].upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]*", project):
        raise ValueError(f"Invalid project name in production folder: {prod.name}")
    print(f"Production folder: {prod.name}; project: {project}; revision: {revision}")

    pcb = child_directory(prod, "pcb", required=True)
    assembly = child_directory(prod, "assembly", required=True)
    coating = child_directory(prod, "coating")
    variants = sorted(p for p in assembly.iterdir() if p.is_dir())
    if not variants:
        raise ValueError("No variant directories found in assembly/")
    seen = set()
    patterns = exclude_patterns.casefold().split()

    def excluded(path):
        relative = "./" + path.relative_to(root).as_posix()
        return any(fnmatchcase(relative.casefold(), pattern) for pattern in patterns)

    def selected(paths):
        return [p for p in paths if not excluded(p)]

    pcb_files = files_in(pcb)
    coat_files = [p for p in pcb_files if is_coat_gerber(p)]
    common = selected([p for p in pcb_files if not is_coat_gerber(p)])
    if not any(p.suffix.casefold() in {".gbr", ".ger", ".gerber"} for p in common):
        raise ValueError("No PCB Gerbers remain after exclusions")
    odb_files = [p for p in prod.iterdir() if p.is_file()
                 and p.name.casefold() == f"{project}-{revision}-odb++.zip".casefold()]
    common += selected(odb_files)
    if not odb_files:
        print("ODB++ export absent; packages will contain no ODB++ archive")

    coating_files = selected(files_in(coating)) if coating else []
    if coat_files and not coating_files:
        raise ValueError("Coat Gerbers found, but coating/ is missing or empty after exclusions")
    has_coating = bool(coat_files)
    print(f"Coat Gerbers: {len(coat_files)}; coating packages: {has_coating}")

    # Validate every variant before writing any package.
    variant_files = []
    for variant in variants:
        letter = variant.name.upper()
        if not re.fullmatch(r"[A-Z]", letter) or letter in seen:
            raise ValueError(f"Variant directories must have unique single-letter names: {variant}")
        seen.add(letter)
        paths = selected(files_in(variant))
        expected_bom = f"{project}-{revision}{letter}_BOM.csv".casefold()
        if not any(p.name.casefold() == expected_bom for p in paths):
            raise ValueError(f"Missing BOM for revision {revision}, variant {letter}: {expected_bom}")
        variant_files.append((letter, paths))

    # A Gerber job index must not advertise the removed coating layers.
    content_overrides = {}
    for path in common:
        if path.suffix.casefold() == ".gbrjob":
            data = json.loads(path.read_text())
            entries = data.get("FilesAttributes", [])
            data["FilesAttributes"] = [entry for entry in entries
                                       if not is_coat_gerber(Path(entry["Path"]))]
            content_overrides[path] = (json.dumps(data, indent=2) + "\n").encode()

    timestamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    output = root / "ZIP"
    output.mkdir(exist_ok=True)
    # The upload step uses ZIP/*.zip; stale packages must not get uploaded.
    for old in output.glob("*-ems.zip"):
        old.unlink()
    if list(output.glob("*.zip")):
        raise ValueError("Unexpected ZIP files in output directory ZIP/")

    packages = []
    for letter, paths in variant_files:
        for coated in ([False, True] if has_coating else [False]):
            suffix = letter + ("Z" if coated else "")
            package = output / f"{project}-{revision}{suffix}-{timestamp}-ems.zip"
            included = common + paths + (coating_files if coated else [])
            with ZipFile(package, "w", compression=ZIP_DEFLATED) as archive:
                for path in included:
                    # Preserve the production folder and assembly/<variant>/ paths.
                    name = path.relative_to(root).as_posix()
                    if path in content_overrides:
                        archive.writestr(name, content_overrides[path])
                    else:
                        archive.write(path, name)
            print(f"Created {package.name} ({len(included)} files)")
            packages.append(package)
    return packages


if __name__ == "__main__":
    try:
        build_packages(Path.cwd(), os.environ["REVISION"], os.environ.get("EXCLUDE_PATTERNS", ""))
    except (ValueError, OSError, KeyError) as error:
        print(f"::error::{error}", file=sys.stderr)
        sys.exit(1)
