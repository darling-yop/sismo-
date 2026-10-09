import unittest

from core.tree_key import TreeKey


class TestTreeKey(unittest.TestCase):
    """Examples from section 5 of the assignment, against the node (3, 5.2, 10)."""

    def setUp(self):
        self.node = TreeKey(3, 5.2, 10)

    def test_lower_priority_goes_left(self):
        # priority 2 < 3, even though 5.8 > 5.2
        self.assertTrue(TreeKey(2, 5.8, 20) < self.node)

    def test_same_priority_higher_magnitude_goes_right(self):
        self.assertTrue(TreeKey(3, 6.1, 30) > self.node)

    def test_same_priority_and_magnitude_lower_id_goes_left(self):
        self.assertTrue(TreeKey(3, 5.2, 5) < self.node)

    def test_same_priority_and_magnitude_higher_id_goes_right(self):
        self.assertTrue(TreeKey(3, 5.2, 25) > self.node)

    def test_equal_keys(self):
        self.assertTrue(TreeKey(3, 5.2, 10) == self.node)
        self.assertFalse(TreeKey(3, 5.2, 11) == self.node)


if __name__ == "__main__":
    unittest.main()
