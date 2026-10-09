import unittest

from domain.models import Zone
from domain.priority import compute_priority, is_populated

ZONES = [
    Zone("Centro", 100.0, 100.0, 200.0, 200.0, True),
    Zone("Rural", 200.0, 100.0, 300.0, 200.0, False),  # shares the border x=200
]


class TestPopulatedZone(unittest.TestCase):
    def test_inside_populated(self):
        self.assertTrue(is_populated(150.0, 150.0, ZONES))

    def test_inside_unpopulated(self):
        self.assertFalse(is_populated(250.0, 150.0, ZONES))

    def test_on_border_of_populated_zone(self):
        self.assertTrue(is_populated(100.0, 150.0, ZONES))

    def test_on_border_shared_by_two_zones_is_populated(self):
        self.assertTrue(is_populated(200.0, 150.0, ZONES))

    def test_outside_every_zone(self):
        self.assertFalse(is_populated(500.0, 500.0, ZONES))


class TestPriority(unittest.TestCase):
    def test_limit_m45_h30_populated_is_3(self):
        self.assertEqual(compute_priority(4.5, 30.0, True), 3)

    def test_same_event_not_populated_is_2(self):
        self.assertEqual(compute_priority(4.5, 30.0, False), 2)

    def test_m60_is_always_3(self):
        self.assertEqual(compute_priority(6.0, 700.0, False), 3)

    def test_just_below_limits(self):
        self.assertEqual(compute_priority(5.9, 30.0, False), 2)
        self.assertEqual(compute_priority(4.5, 30.1, True), 2)
        self.assertEqual(compute_priority(4.4, 1.0, True), 1)

    def test_negative_magnitude_is_low(self):
        self.assertEqual(compute_priority(-2.0, 0.0, True), 1)


if __name__ == "__main__":
    unittest.main()
