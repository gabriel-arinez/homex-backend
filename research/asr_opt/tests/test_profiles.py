import unittest

from research.asr_opt.profiles import PROFILES, kwargs


class ProfileTests(unittest.TestCase):
    def test_preregistered_single_factors_and_no_seeded_numbers(self):
        self.assertEqual(kwargs("baseline"), {"language": "es"})
        for profile in PROFILES:
            values = kwargs(profile)
            if profile != "baseline":
                self.assertEqual(len(values), 2)
            for key in ["initial_prompt", "hotwords"]:
                if key in values:
                    self.assertFalse(any(c.isdigit() for c in values[key]))
        with self.assertRaises(ValueError):
            kwargs("unregistered")
        mutated = kwargs("beam3")
        mutated["beam_size"] = 99
        self.assertEqual(kwargs("beam3")["beam_size"], 3)
