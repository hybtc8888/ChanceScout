import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import demand_leads as leads


def observation(**overrides):
    value = copy.deepcopy(json.loads((ROOT / "examples/demand-leads.example.json").read_text(encoding="utf-8"))[0])
    value.update(fictional=False)
    value.update(overrides)
    return value


def seo(**overrides):
    row = dict(keyword="test keyword", provider="Example", market="US", period="2026-10", currency="USD",
               retrieval="direct", source_url="https://example.invalid/metrics", volume=390, global_volume=2800,
               kd=39, cpc=3.02, note="Fictional measured metrics for unit tests.")
    row.update(overrides)
    return row


class DemandLeadTests(unittest.TestCase):
    def test_cluster_deduplicates_retains_notes_and_updates_evidence(self):
        first, _ = leads.merge([], [observation(user_note="keep me")], "2026-10-25T00:00:00Z")
        same, batch = leads.merge(first, [observation()], "2026-10-26T00:00:00Z")
        self.assertEqual(len(same), 1)
        self.assertEqual(batch[0]["change"], "unchanged")
        self.assertEqual(batch[0]["first_seen_at"], first[0]["first_seen_at"])
        self.assertEqual(batch[0]["user_note"], "keep me")
        changed = observation()
        changed["evidence"].append(dict(changed["evidence"][0], url="https://example.invalid/another-comment"))
        _, batch = leads.merge(same, [changed], "2026-10-27T00:00:00Z")
        self.assertEqual(batch[0]["change"], "updated")
        self.assertEqual(len(batch[0]["evidence"]), 2)

    def test_missing_metrics_are_not_zero_and_snapshot_is_labeled(self):
        _, batch = leads.merge([], [observation(seo=[seo(retrieval="author_screenshot"),
                        seo(retrieval="unavailable", volume=None, global_volume=None, kd=None, cpc=None)])], "2026-10-27T00:00:00Z")
        report = leads.render(batch, "2026-10-27T00:00:00Z")
        self.assertIn("作者截图，未独立复现", report)
        self.assertIn("市场月搜索量 390；全球月搜索量 2800", report)
        self.assertIn("市场月搜索量 未取得", report)

    def test_bad_metrics_and_global_local_mix_are_rejected(self):
        for row in [seo(kd=101), seo(cpc=-1), seo(volume=3.5), seo(volume=True), seo(kd=float("nan")),
                    seo(retrieval="unavailable"), seo(market="global"), seo(cpc=3, currency=None), seo(period=None)]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                leads.validate([observation(seo=[row])])

    def test_no_semantic_verification_is_claimed_for_seller_willingness(self):
        seller = observation(disposition="discarded", assessment="The quoted willingness is the seller's own.")
        seller["evidence"][0].update(speaker="seller", signal="willingness")
        with tempfile.TemporaryDirectory() as tmp:
            receipt = leads.ingest([seller], tmp)
            self.assertEqual(receipt["research"], 0)
            self.assertEqual(receipt["discarded"], 1)
            self.assertFalse(receipt["facts_verified_by_tool"])
            self.assertIn("The quoted willingness is the seller", Path(receipt["report"]).read_text(encoding="utf-8"))

    def test_failed_ingest_does_not_write_and_workspaces_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = leads.ingest([observation()], tmp)
            before = Path(first["history"]).read_bytes()
            for invalid in [observation(seo=[seo(retrieval="unavailable")]), observation(fictional=True)]:
                with self.assertRaises(ValueError):
                    leads.ingest([invalid], tmp)
                self.assertEqual(Path(first["history"]).read_bytes(), before)
            with leads.storage.workspace_lock(Path(tmp)), self.assertRaises(ValueError):
                leads.ingest([observation()], tmp)
            self.assertFalse((Path(tmp) / "opportunities.jsonl").exists())

    def test_duplicate_cluster_requires_consolidation_and_urls_are_safe(self):
        with self.assertRaises(ValueError):
            leads.validate([observation(), observation()])
        value = observation()
        value["evidence"][0]["url"] = "javascript:alert(1)"
        with self.assertRaises(ValueError):
            leads.validate([value])

    def test_second_run_reports_only_current_batch_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = leads.ingest([observation(), observation(canonical_key="other", title="Older cluster")], tmp)
            second = leads.ingest([observation()], tmp)
            self.assertNotEqual(first["report"], second["report"])
            self.assertEqual(second["history_count"], 2)
            self.assertEqual(second["unchanged"], 1)
            self.assertNotIn("Older cluster", Path(second["report"]).read_text(encoding="utf-8"))

    def test_cli_demo_in_unicode_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(ROOT / "scripts/demand_leads.py"), "demo",
                                     "--workspace", str(Path(tmp) / "需求线索")], capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertTrue(receipt["fictional"])
            self.assertIn("虚构", Path(receipt["report"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
