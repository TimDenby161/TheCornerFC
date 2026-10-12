"""Which module in thecornerfc/publish may import which, so the split of export.py can't grow
an import cycle. export.py runs the export and imports every site_* module; none imports it back.
"""
import ast
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLISH = ROOT / "thecornerfc" / "publish"

# module: the publish modules it may import (anywhere in the file, top level or inside a function)
ALLOWED = {
    "tables": set(),
    "site_files": set(),
    "site_matches": {"site_files"},
    "site_record": {"site_files", "site_matches"},
    "site_players": {"site_files"},
    "site_clubs": {"site_files", "tables"},
    "site_fantasy": {"site_files"},
    "export": {"tables", "site_files", "site_matches", "site_record", "site_players", "site_clubs", "site_fantasy"},
}


def publish_imports(path, top_level_only=False):
    """The publish modules a file imports, by name."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in (tree.body if top_level_only else ast.walk(tree)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 1 and not module:                       # from . import tables
                found |= {alias.name for alias in node.names}
            elif node.level == 1:                                    # from .site_files import x
                found.add(module.split(".")[0])
            elif module.startswith("thecornerfc.publish"):           # absolute
                rest = module[len("thecornerfc.publish"):].lstrip(".")
                found |= {rest.split(".")[0]} if rest else {alias.name for alias in node.names}
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("thecornerfc.publish."):
                    found.add(alias.name.split(".")[2])
    return {name for name in found if (PUBLISH / f"{name}.py").exists()}


class PublishImportTests(unittest.TestCase):
    def modules(self):
        return {path.stem: path for path in sorted(PUBLISH.glob("*.py"))}

    def test_every_publish_module_is_listed(self):
        self.assertEqual(set(self.modules()) - set(ALLOWED), set(), "say in ALLOWED what a new module may import")

    def test_each_module_imports_only_what_it_may(self):
        for name, path in self.modules().items():
            self.assertLessEqual(publish_imports(path), ALLOWED[name], name)

    def test_nothing_in_publish_imports_export(self):
        for name, path in self.modules().items():
            self.assertNotIn("export", publish_imports(path), name)

    def test_the_allowed_order_has_no_cycle(self):
        seen, done = set(), set()

        def visit(name, trail):
            self.assertNotIn(name, seen - done, " -> ".join((*trail, name)))
            if name in done:
                return
            seen.add(name)
            for needed in sorted(ALLOWED[name]):
                visit(needed, (*trail, name))
            done.add(name)

        for name in ALLOWED:
            visit(name, ())

    def test_each_module_imports_on_its_own(self):
        # in a fresh interpreter, so no sibling has been loaded first to hide a cycle
        for name in self.modules():
            result = subprocess.run([sys.executable, "-c", f"import thecornerfc.publish.{name}"],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"{name}: {result.stderr[-600:]}")


if __name__ == "__main__":
    unittest.main()
