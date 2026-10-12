"""The model files whose bytes are part of each model version's identity.

source_digests() (thecornerfc/evidence/model_versions.py) hashes these files into the
configuration a model version is registered with, so a changed byte in one of them, even in a
comment, is a new model version on the next run. This test fails when one changes, so that it
only ever happens on purpose.

After a deliberate model change (guide/model-versions.md, "Changing a fingerprinted file"):
put the new hash from the failure message in FINGERPRINTS, in the same commit as the change.
"""
import ast
import hashlib
import unittest
from collections import defaultdict
from pathlib import Path

from thecornerfc.evidence.model_versions import source_digests

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "thecornerfc"

# file name: (where it lives, sha256 of its bytes)
FINGERPRINTS = {
    "availability.py": ("models", "5629af0b4356d07373a7e5927642f125302af6ba357122cc7adb79dffaab5eeb"),
    "betting.py": ("models", "5d0e0ce6a6c854532133e8da90af54077a16486a144ce3e5cf1f5180388f606b"),
    "fantasy.py": ("fantasy_games", "9d1125ba32a30be4aa7eac34bbb8581ae2d4bbab844c33a9ed5c7d377dcfc1be"),
    "fantasy_snapshots.py": ("fantasy_games", "b89e40622ab401459875bce446f7c771d33a9ef616b8ee05ca5e315eca4696ee"),
    "injuries.py": ("models", "3d96c474df0b6d7980484f9d874e0bbca9ee1a3fc65060f68466f770b6e9f35f"),
    "lineup_snapshots.py": ("evidence", "25cc36cb99773158a45d523ba1b159cd65f802d61e36c1bedb8c965bd829a0ba"),
    "match_snapshots.py": ("evidence", "c4ce9c7df94d9c9f9f030c9dbb14ef2e0c558548ebeb2b3fba20de7b921ca566"),
    "national_lineups.py": ("models", "64cb75452ccc4958b6a423b3de5ff9753ef1fb8b8870eb2eec39a615d8a41d99"),
    "national_predictions.py": ("models", "2fc2db665b77c9196eff33513453289c661669fef3e600ade78401f06e4a1a7f"),
    "nations.py": ("models", "57b803e6546c12bba962619659bf635d8161ff542da611197a5da7f62b70dce9"),
    "paper_evidence.py": ("evidence", "606da6f0c20f9a94837cea89635c853abae916b60e80935883a1dda92ed7178a"),
    "player_history.py": ("evidence", "cc3481b2aa6d8c553c01b3685724dfaa18d1e7508dd4e1da42acaf8fa38836d0"),
    "player_ratings.py": ("models", "01914fea926d946632b5b14bf2d7a8dcef8479b3510fa7393b71fa8cc3bde5be"),
    "positions.py": ("models", "9b048895007339ed68de0dadb2e1736f3aa8d0bd7a29ab4c6965d3e4f42a0dde"),
    "predictions.py": ("models", "462dd8ca22d49df66c1716d12cf68665ee8f8a3eeb9104be98dccab1cc1601a0"),
    "ranking.py": ("models", "2694a1777da8d4353960a4a130ba71c758bb5da6a76989ab506f8e1c29fb0832"),
}


def fingerprinted_names():
    """Every file name the package passes to source_digests(), read from the source."""
    names = set()
    for path in PACKAGE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            called = getattr(node, "func", None)
            if isinstance(node, ast.Call) and getattr(called, "id", getattr(called, "attr", None)) == "source_digests":
                for arg in node.args:
                    names |= {n.value for n in ast.walk(arg) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    return names


class ModelFingerprintTests(unittest.TestCase):
    def test_no_fingerprinted_file_has_changed(self):
        now = source_digests(sorted(FINGERPRINTS))
        changed = {name: digest for name, digest in now.items() if digest != FINGERPRINTS[name][1]}
        self.assertFalse(changed, (
            "These model files have changed, so their models will register a NEW VERSION on the "
            "next run and their evidence starts again. If that is intended, put these hashes in "
            f"FINGERPRINTS in the same commit (guide/model-versions.md): {changed}. If not, undo the edit."))

    def test_the_table_lists_exactly_the_files_the_package_fingerprints(self):
        # a file newly passed to source_digests() must be added here, and one dropped removed
        self.assertEqual(fingerprinted_names(), set(FINGERPRINTS))

    def test_each_name_is_found_where_the_table_says(self):
        # source_digests finds a file by its bare name: a same-named file elsewhere would be
        # hashed in its place
        for name, (folder, digest) in FINGERPRINTS.items():
            path = PACKAGE / folder / name
            self.assertTrue(path.is_file(), path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, name)

    def test_every_python_file_name_in_the_package_is_unique(self):
        found = defaultdict(list)
        for path in PACKAGE.rglob("*.py"):
            found[path.name].append(str(path.relative_to(ROOT)))
        twice = {name: paths for name, paths in found.items() if len(paths) > 1 and name != "__init__.py"}
        self.assertFalse(twice, "source_digests() finds model files by bare name: rename one of each pair")

    def test_the_files_are_stored_with_unix_line_endings(self):
        # a checkout that rewrote line endings would change every hash
        for name, (folder, _) in FINGERPRINTS.items():
            self.assertNotIn(b"\r\n", (PACKAGE / folder / name).read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
