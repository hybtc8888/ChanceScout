import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import chancescout
import demand_leads


def fixtures(name):
    return json.loads((ROOT / f"examples/{name}.example.json").read_text(encoding="utf-8"))


def cli(*args, cwd=None):
    return subprocess.run([sys.executable, str(ROOT / "scripts/chancescout.py"), *map(str, args)],
                          cwd=cwd, capture_output=True, encoding="utf-8")


class UnifiedCliTests(unittest.TestCase):
    def test_both_formats_are_inferred_from_outside_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, kind in (("opportunities", "opportunity"), ("demand-leads", "demand")):
                result = cli("validate", ROOT / f"examples/{name}.example.json", cwd=tmp)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["kind"], kind)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_two_kinds_share_workspace_without_changing_other_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "records"
            result = cli("demo", "--workspace", work)
            self.assertEqual(result.returncode, 0, result.stderr)
            before = (work / "opportunities.jsonl").read_bytes()
            for _ in range(2):
                result = cli("demo", "--kind", "demand", "--workspace", work)
                self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["new"], 0)
            self.assertEqual(receipt["unchanged"], 2)
            self.assertEqual((work / "opportunities.jsonl").read_bytes(), before)
            self.assertTrue((work / "demand-leads.jsonl").exists())

    def test_mixed_batch_does_not_modify_existing_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "records"
            demand_leads.ingest(fixtures("demand-leads"), work, demo=True)
            before = (work / "demand-leads.jsonl").read_bytes()
            source = Path(tmp) / "mixed.json"
            source.write_text(json.dumps(fixtures("opportunities") + fixtures("demand-leads")), encoding="utf-8")
            result = cli("ingest", source, "--workspace", work)
            self.assertEqual(result.returncode, 2)
            self.assertIn("separate input batches", result.stderr)
            self.assertEqual((work / "demand-leads.jsonl").read_bytes(), before)

    def test_empty_demand_batch_can_be_explicit_and_unicode_jsonl_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.json"
            empty.write_text("[]", encoding="utf-8")
            result = cli("validate", empty, "--kind", "demand")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["kind"], "demand")
            source = Path(tmp) / "observations.jsonl"
            source.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in fixtures("demand-leads")), encoding="utf-8-sig")
            result = cli("validate", source)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["records"], 2)

    def test_task_details_and_product_evidence_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = demand_leads.ingest(fixtures("demand-leads"), tmp, demo=True)
            report = Path(receipt["report"]).read_text(encoding="utf-8")
            self.assertIn("产品需求 / reddit", report)
            self.assertIn("有偿任务 / xiaohongshu", report)
            self.assertIn("报价：虚构报价：60元/次", report)
            self.assertIn("地区：线上，不限地区", report)
            self.assertIn("方式：远程", report)

    def test_task_terms_are_material_updates_and_old_optional_fields_survive(self):
        value = fixtures("demand-leads")[1]
        first, _ = demand_leads.merge([], [value], "2026-10-25T00:00:00Z")
        revised = copy.deepcopy(value)
        revised["budget"] = "Changed quote"
        _, batch = demand_leads.merge(first, [revised], "2026-10-26T00:00:00Z")
        self.assertEqual(batch[0]["change"], "updated")
        omitted = {k: v for k, v in value.items() if k not in {"budget", "region", "work_mode", "deadline", "lead_type", "platform"}}
        _, batch = demand_leads.merge(first, [omitted], "2026-10-26T00:00:00Z")
        self.assertEqual(batch[0]["change"], "unchanged")
        self.assertEqual(batch[0]["region"], value["region"])

    def test_imported_demand_id_is_preserved_by_canonical_key(self):
        value = fixtures("demand-leads")[0]
        first, _ = demand_leads.merge([], [dict(value, id="imported-id", user_note="keep")], "2026-10-25T00:00:00Z")
        _, batch = demand_leads.merge(first, [value], "2026-10-26T00:00:00Z")
        self.assertEqual(batch[0]["id"], "imported-id")
        self.assertEqual(batch[0]["user_note"], "keep")
        self.assertEqual(batch[0]["change"], "unchanged")
        with self.assertRaises(ValueError):
            demand_leads.merge(first, [dict(value, id="conflicting-id")], "2026-10-26T00:00:00Z")

    def test_old_demand_records_without_type_still_load(self):
        value = fixtures("demand-leads")[0]
        legacy = {k: v for k, v in value.items() if k not in {"lead_type", "platform"}}
        with tempfile.TemporaryDirectory() as tmp:
            result = demand_leads.ingest([legacy], tmp)
            report = Path(result["report"]).read_text(encoding="utf-8")
            self.assertIn("未分类需求", report)
            self.assertEqual(result["history_count"], 1)


if __name__ == "__main__":
    unittest.main()
