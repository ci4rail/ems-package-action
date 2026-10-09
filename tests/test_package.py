import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile


ACTION_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package", ACTION_ROOT / "scripts/package.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prod = self.root / "IOU16-prod"
        self.write("IOU16-prod/pcb/IOU16-01-Gerber/IOU16-F_Cu.gbr")
        self.write("IOU16-prod/pcb/IOU16-01-Gerber/IOU16.drl")
        self.write("IOU16-prod/pcb/pcb-datasheet.pdf")
        for variant in ("A", "B"):
            self.write(f"IOU16-prod/assembly/{variant}/BOMs/IOU16-01{variant}_BOM.csv")
            self.write(f"IOU16-prod/assembly/{variant}/BOMs/IOU16-01{variant}_BOM_parts.csv")
            self.write(f"IOU16-prod/assembly/{variant}/IOU16-01{variant}-position-top")
        self.write("IOU16-prod/documentation/IOU16-01A-circuit.pdf")
        self.write("IOU16-prod/documentation/IOU16-01-erc.rpt")
        self.write("IOU16-prod/internal/cost.csv")
        self.write("IOU16-kicad/project.kicad_sch")
        self.write("README.md")

    def write(self, name, content="fixture"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def coats(self):
        self.write("IOU16-prod/pcb/IOU16-01-Gerber/IOU16-F_CCoat.gbr")
        self.write("IOU16-prod/pcb/IOU16-01-Gerber/IOU16-B_CCoatKOut.GBR")
        self.write("IOU16-prod/coating/IOU16-01-coating-top.pdf")
        self.write("IOU16-prod/coating/IOU16-01-coating-bottom.pdf")
        self.write("IOU16-prod/pcb/IOU16-01-Gerber/IOU16-job.gbrjob", json.dumps({
            "FilesAttributes": [{"Path": "IOU16-F_Cu.gbr"}, {"Path": "IOU16-F_CCoat.gbr"}]
        }))

    def build(self, patterns=""):
        return package.build_packages(self.root, "01", patterns, "202610081200")

    def test_four_packages_are_isolated_and_coats_removed(self):
        self.coats()
        paths = self.build()
        self.assertEqual([p.name for p in paths], [
            f"IOU16-01{suffix}-202610081200-ems.zip" for suffix in ("A", "AZ", "B", "BZ")
        ])
        for path, variant, coated in zip(paths, ("A", "A", "B", "B"), (False, True, False, True)):
            with ZipFile(path) as archive:
                names = archive.namelist()
                self.assertTrue(any(f"/assembly/{variant}/" in name for name in names))
                other = "B" if variant == "A" else "A"
                self.assertFalse(any(f"/assembly/{other}/" in name for name in names))
                self.assertFalse(any("coat" in name.lower() and name.lower().endswith(".gbr") for name in names))
                self.assertEqual(any("/coating/" in name for name in names), coated)
                self.assertFalse(any("documentation" in name or "internal" in name for name in names))
                self.assertTrue(all(name.startswith("IOU16-prod/") for name in names))
                job = json.loads(archive.read("IOU16-prod/pcb/IOU16-01-Gerber/IOU16-job.gbrjob"))
                self.assertEqual(job["FilesAttributes"], [{"Path": "IOU16-F_Cu.gbr"}])

    def test_no_coat_gerbers_means_only_uncoated_packages(self):
        self.write("IOU16-prod/coating/unused.pdf")
        paths = self.build()
        self.assertEqual(len(paths), 2)
        for p in paths:
            with ZipFile(p) as archive:
                self.assertFalse(any("/coating/" in name for name in archive.namelist()))

    def test_optional_odb_included_only_for_matching_revision(self):
        self.write("IOU16-prod/IOU16-01-odb++.zip")
        self.write("IOU16-prod/IOU16-00-odb++.zip")
        for p in self.build():
            with ZipFile(p) as archive:
                self.assertIn("IOU16-prod/IOU16-01-odb++.zip", archive.namelist())
                self.assertNotIn("IOU16-prod/IOU16-00-odb++.zip", archive.namelist())

    def test_case_insensitive_exclusions(self):
        self.coats()
        for p in self.build("*BOM_PARTS.CSV"):
            with ZipFile(p) as archive:
                self.assertFalse(any("_BOM_parts.csv" in name for name in archive.namelist()))

    def test_wrong_release_revision_fails_before_packaging(self):
        with self.assertRaisesRegex(ValueError, "Missing BOM"):
            package.build_packages(self.root, "02")
        self.assertFalse((self.root / "ZIP").exists())

    def test_missing_coating_fails(self):
        self.write("IOU16-prod/pcb/IOU16-01-Gerber/IOU16-F_CCoat.gbr")
        with self.assertRaisesRegex(ValueError, "coating/ is missing"):
            self.build()

    def test_missing_or_excluded_bom_fails(self):
        with self.assertRaisesRegex(ValueError, "Missing BOM"):
            self.build("*_BOM.csv")

    def test_ambiguous_production_folders_fail(self):
        self.write("Other-prod/pcb/other.gbr")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.build()

    def test_rerun_removes_stale_packages(self):
        self.coats()
        self.build()
        for p in (self.prod / "pcb").rglob("*"):
            if package.is_coat_gerber(p):
                p.unlink()
        self.build()
        self.assertEqual(len(list((self.root / "ZIP").glob("*.zip"))), 2)

    def test_action_script_runs_from_hardware_repo(self):
        result = subprocess.run(["python3", str(ACTION_ROOT / "scripts/package.py")],
                                cwd=self.root, env={**os.environ, "REVISION": "01", "EXCLUDE_PATTERNS": ""},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(list((self.root / "ZIP").glob("*.zip"))), 2)


if __name__ == "__main__":
    unittest.main()
