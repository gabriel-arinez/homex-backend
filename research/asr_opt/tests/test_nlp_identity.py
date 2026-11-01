"""Synthetic identity contract checks; no private corpus or inference."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.asr_opt.nlp_identity import (
    REGISTRY,
    identity,
    validate_matrix,
    validate_metadata,
    verify_installed,
)


class NlpIdentityTests(unittest.TestCase):
    def test_all_pinned_identities_are_complete(self):
        for selector in json.loads(REGISTRY.read_text()):
            expected = identity(selector)
            validate_metadata(expected, selector)
            self.assertEqual(expected["schema_version"], "1.0")
            self.assertEqual(expected["mode"], "RULES_ONLY")
            self.assertEqual(len(expected["wheel_sha256"]), 64)

    def test_crossed_versions_hashes_and_contracts_rejected(self):
        for selector in ["historical-018", "corrective-019-mixed"]:
            expected = identity(selector)
            for field, value in [
                ("version", "unknown"),
                ("rules", "wrong"),
                ("wheel_sha256", "0" * 64),
                ("schema_version", "2.0"),
                ("mode", "NER"),
            ]:
                invalid = {**expected, field: value}
                with self.assertRaises(ValueError):
                    validate_metadata(invalid, selector)
            for field in expected:
                invalid = copy.deepcopy(expected)
                del invalid[field]
                with self.assertRaises(ValueError):
                    validate_metadata(invalid, selector)
        for a, b in [
            ("historical-018", "corrective-019-mixed"),
            ("corrective-019-mixed", "historical-018"),
        ]:
            with self.assertRaises(ValueError):
                validate_metadata(identity(a), b)
        with self.assertRaises(ValueError):
            identity("unknown")

    def test_legacy_is_explicit_and_never_claims_wheel_attestation(self):
        old = identity("historical-018")
        matrix = {
            "nlp": old["version"],
            "rules": old["rules"],
            "mode": "RULES_ONLY",
            "projection_version": "PRF04_2",
            "db_read_only": True,
        }
        snapshot = json.dumps(matrix, sort_keys=True)
        with self.assertRaises(ValueError):
            validate_matrix(matrix, "historical-018")
        self.assertEqual(
            validate_matrix(matrix, "historical-018", legacy=True),
            "LEGACY_METADATA_ONLY_NOT_WHEEL_ATTESTED",
        )
        self.assertEqual(snapshot, json.dumps(matrix, sort_keys=True))
        for selector in ["historical-018", "corrective-019-mixed"]:
            expected = identity(selector)
            current = {
                **matrix,
                "nlp": expected["version"],
                "rules": expected["rules"],
                "nlp_identity": expected,
            }
            self.assertEqual(validate_matrix(current, selector), "PINNED_IDENTITY")
        with self.assertRaises(ValueError):
            validate_matrix(matrix, "corrective-019-mixed", legacy=True)

    def test_missing_and_wrong_wheel_never_accept_declaration(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "artifact.whl"
            with self.assertRaises(FileNotFoundError):
                verify_installed("historical-018", path)
            path.write_bytes(b"not the pinned wheel")
            with self.assertRaises(ValueError):
                verify_installed("historical-018", path)

    def test_mismatched_installed_version_rejected(self):
        from research.asr_opt.nlp_identity import historical_wheel

        with patch("research.asr_opt.nlp_identity.distribution") as dist:
            dist.return_value.version = "0.1.19"
            with self.assertRaises(ValueError):
                verify_installed("historical-018", historical_wheel())

    def test_installed_bytes_checked_not_only_package_metadata(self):
        from research.asr_opt.nlp_identity import historical_wheel

        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "fake.py"
            path.write_bytes(b"tampered")
            with patch("research.asr_opt.nlp_identity.distribution") as dist:
                dist.return_value.version = "0.1.18"
                dist.return_value.locate_file.return_value = path
                with self.assertRaisesRegex(ValueError, "Bytes NLP"):
                    verify_installed("historical-018", historical_wheel())

    def test_report_runtime_identity_and_historical_opt_in(self):
        from research.asr_opt.nlp_identity import validate_acoustic_report

        for selector in ["historical-018", "corrective-019-mixed"]:
            expected = identity(selector)
            report = {
                "nlp_identity": expected,
                "versions": {
                    "faster-whisper": "1.2.1",
                    "ctranslate2": "4.8.2",
                    "homex-nlp": expected["version"],
                },
            }
            before = json.dumps(report, sort_keys=True)
            self.assertEqual(validate_acoustic_report(report)[0], expected)
            self.assertEqual(before, json.dumps(report, sort_keys=True))
            report["versions"]["homex-nlp"] = "0.1.19" if selector == "historical-018" else "0.1.18"
            with self.assertRaises(ValueError):
                validate_acoustic_report(report)
        legacy = {
            "versions": {"faster-whisper": "1.2.1", "ctranslate2": "4.8.2", "homex-nlp": "0.1.18"}
        }
        with self.assertRaises(ValueError):
            validate_acoustic_report(legacy)
        self.assertEqual(
            validate_acoustic_report(legacy, legacy=True)[1],
            "LEGACY_METADATA_ONLY_NOT_WHEEL_ATTESTED",
        )

    def test_missing_installed_dependency_has_clear_error(self):
        from importlib.metadata import PackageNotFoundError

        from research.asr_opt.nlp_identity import historical_wheel

        with patch(
            "research.asr_opt.nlp_identity.distribution",
            side_effect=PackageNotFoundError("homex-nlp"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Falta dependencia homex-nlp"):
                verify_installed("historical-018", historical_wheel())
