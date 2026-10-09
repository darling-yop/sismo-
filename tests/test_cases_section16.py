import unittest

from scripts.run_cases import run


class Section16Test(unittest.TestCase):
    def test_all_cases_match_expected(self):
        rows = run()
        self.assertGreaterEqual(len(rows), 40)
        failed = [r for r in rows if not r["ok"]]
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
