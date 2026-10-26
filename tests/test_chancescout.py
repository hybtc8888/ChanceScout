import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("chancescout", ROOT / "scripts/chancescout.py")
radar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(radar)


def observation(**overrides):
    value = copy.deepcopy(json.loads((ROOT / "examples/opportunities.example.json").read_text(encoding="utf-8"))[0])
    value.update(fictional=False, evidence_level="official_verified",
                 evidence=[{"url": value["source_urls"][0], "supports": ["deadline", "benefit"]}])
    value.update(overrides)
    return value


class HistoryTests(unittest.TestCase):
    def test_same_observation_deduplicates_and_keeps_first_seen(self):
        first, _ = radar.merge([], [observation()], "2026-10-25T09:00:00+08:00")
        second, batch = radar.merge(first, [observation()], "2026-10-26T09:00:00+08:00")
        self.assertEqual(len(second), 1)
        self.assertEqual(batch[0]["change"], "unchanged")
        self.assertEqual(batch[0]["first_seen_at"], first[0]["first_seen_at"])
        self.assertEqual(batch[0]["last_checked_at"], "2026-10-26T09:00:00+08:00")

    def test_rule_change_retains_notes_and_unobserved_projects(self):
        first, _ = radar.merge([], [observation(user_note="keep me"), observation(edition="another-round")], "2026-10-25T00:00:00Z")
        second, batch = radar.merge(first, [observation(deadline="new official window")], "2026-10-26T00:00:00Z")
        self.assertEqual(len(second), 2)
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0]["change"], "updated")
        self.assertEqual(batch[0]["user_note"], "keep me")

    def test_identity_normalization_and_imported_id(self):
        a = observation(organizer="Example  LAB")
        b = observation(organizer=" example lab ")
        self.assertEqual(radar.identity(a), radar.identity(b))
        self.assertNotEqual(radar.identity(a), radar.identity(dict(a, edition="new-year")))
        self.assertEqual(radar.identity(dict(a, id="imported-id")), "imported-id")

    def test_metadata_and_url_order_are_not_rule_changes(self):
        value = observation(source_urls=["https://example.invalid/a", "https://example.invalid/b"])
        first, _ = radar.merge([], [value], "2026-10-25T00:00:00Z")
        revised = dict(value, source_urls=list(reversed(value["source_urls"])), agent_note="read again")
        _, batch = radar.merge(first, [revised], "2026-10-26T00:00:00Z")
        self.assertEqual(batch[0]["change"], "unchanged")

    def test_omitted_optional_fields_keep_existing_values(self):
        first, _ = radar.merge([], [observation(recommended=False)], "2026-10-25T00:00:00Z")
        _, batch = radar.merge(first, [observation()], "2026-10-26T00:00:00Z")
        self.assertEqual(batch[0]["change"], "unchanged")
        self.assertFalse(batch[0]["recommended"])


class PersistenceTests(unittest.TestCase):
    def test_reports_use_only_this_batch_and_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = radar.ingest([observation(), observation(program="Old other project")], tmp)
            second = radar.ingest([observation()], tmp)
            self.assertNotEqual(first["report"], second["report"])
            self.assertEqual(second["history_count"], 2)
            self.assertEqual(second["observed"], 1)
            self.assertNotIn("Old other project", Path(second["report"]).read_text(encoding="utf-8"))

    def test_invalid_batch_does_not_change_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = radar.ingest([observation()], tmp)
            before = Path(receipt["history"]).read_bytes()
            with self.assertRaises(ValueError):
                radar.ingest([observation(status="probably")], tmp)
            self.assertEqual(Path(receipt["history"]).read_bytes(), before)

    def test_demo_is_marked_and_separate_from_real_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = radar.read_records(ROOT / "examples/opportunities.example.json")
            receipt = radar.ingest(data, tmp, demo=True)
            self.assertTrue(receipt["fictional"])
            self.assertIn("全部组织、机会、链接", Path(receipt["report"]).read_text(encoding="utf-8"))
            before = Path(receipt["history"]).read_bytes()
            with self.assertRaises(ValueError):
                radar.ingest([observation()], tmp)
            self.assertEqual(Path(receipt["history"]).read_bytes(), before)

    def test_cli_runs_in_unicode_directory(self):
        with tempfile.TemporaryDirectory(prefix="chancescout-") as tmp:
            result = subprocess.run([sys.executable, str(ROOT / "scripts/chancescout.py"), "demo", "--workspace", str(Path(tmp) / "机会记录")], capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertTrue(Path(receipt["report"]).is_file())

    def test_another_writer_cannot_modify_locked_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            with radar.workspace_lock(Path(tmp)):
                with self.assertRaises(ValueError):
                    radar.ingest([observation()], tmp)
            self.assertFalse((Path(tmp) / "opportunities.jsonl").exists())


class ValidationTests(unittest.TestCase):
    def test_bad_url_and_naive_check_time_are_rejected(self):
        for bad in [observation(source_urls=["javascript:alert(1)"]), observation(last_checked_at="2026-10-26T09:00:00")]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                radar.validate([bad])

    def test_unverified_or_restricted_items_are_not_main_opportunities(self):
        self.assertTrue(radar.is_main(observation()))
        self.assertFalse(radar.is_main(observation(evidence_level="unverified")))
        self.assertFalse(radar.is_main(observation(recommended=False)))
        self.assertFalse(radar.is_main(observation(status="closed")))

    def test_duplicate_batch_requires_one_canonical_observation(self):
        with self.assertRaises(ValueError):
            radar.validate([observation(), observation()])

    def test_render_does_not_insert_source_text_as_html(self):
        _, batch = radar.merge([], [observation(program='<img src=x onerror="x">')], "2026-10-26T00:00:00Z")
        text = radar.render(batch, "2026-10-26T00:00:00Z")
        self.assertNotIn("<img", text)
        self.assertIn("&lt;img", text)


if __name__ == "__main__":
    unittest.main()
