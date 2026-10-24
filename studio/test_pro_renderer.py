"""Meaningful failure-gate tests; the real render is a separate integration check."""
import copy
import tempfile
import unittest
from pathlib import Path
import pro_renderer as pro


class ProductionGates(unittest.TestCase):
    def setUp(self):
        self.manifest = pro.read("studio/manifests/2026-10-24-fire-piping-behind-scenes.json")
        self.catalog = pro.read("studio/asset-library.json")

    def test_reviewed_manifest_and_source_integrity(self):
        pro.validate(self.manifest, self.catalog)

    def test_new_owner_footage_is_supported_but_ai_is_not_mislabelled(self):
        self.catalog["assets"][self.manifest["assetId"]]["sourceType"] = "owner-original"
        pro.validate(self.manifest, self.catalog)
        self.catalog["assets"][self.manifest["assetId"]]["sourceType"] = "ai-illustration"
        with self.assertRaisesRegex(ValueError, "Unreviewed"):
            pro.validate(self.manifest, self.catalog)

    def test_amc_caption_rejected_for_installation_footage(self):
        self.manifest["shots"][0]["lines"] = ["Your AMC inspection", "completed today"]
        with self.assertRaisesRegex(ValueError, "copy is not approved"):
            pro.validate(self.manifest, self.catalog)

    def test_unreviewed_crop_and_unreviewed_time_rejected(self):
        for update in ({"crop": [626,800,0,0]}, {"start": 0}):
            manifest = copy.deepcopy(self.manifest)
            manifest["shots"][0].update(update)
            with self.assertRaises(ValueError):
                pro.validate(manifest, self.catalog)

    def test_unsupported_offer_rejected(self):
        self.manifest["caption"] = "Book a free inspection today!"
        with self.assertRaisesRegex(ValueError, "Post caption"):
            pro.validate(self.manifest, self.catalog)

    def test_changed_source_or_logo_rejected(self):
        for target in ("source", "logo"):
            catalog = copy.deepcopy(self.catalog)
            if target == "source":
                catalog["assets"][self.manifest["assetId"]]["sha256"] = "bad"
            else:
                catalog["logoSha256"] = "bad"
            with self.assertRaises(ValueError):
                pro.validate(self.manifest, catalog)

    def test_no_external_paths(self):
        with self.assertRaisesRegex(ValueError, "inside"):
            pro.local("../../private-file")

    def test_duplicate_fingerprint_ignores_changed_slot_date(self):
        second = copy.deepcopy(self.manifest)
        second["slot"] = "2026-10-26-same-edit"
        self.assertEqual(pro.fingerprint(self.manifest), pro.fingerprint(second))

    def test_duplicate_slot_and_ambiguous_publication_block(self):
        original_root = pro.ROOT
        with tempfile.TemporaryDirectory() as temporary:
            try:
                pro.ROOT = Path(temporary)
                for status in ("posted", "publishing", "publication_unknown", "failed"):
                    pro.write("marketing/publication-log.json", {"entries":[{"campaignId": self.manifest["slot"], "status":status}]})
                    with self.assertRaisesRegex(ValueError, "reconcile"):
                        pro.duplicate_check(self.manifest)
            finally:
                pro.ROOT = original_root


if __name__ == "__main__":
    unittest.main()
