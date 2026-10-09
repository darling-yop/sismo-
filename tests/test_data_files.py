import json
import os
import unittest

from services.persistence import (PersistenceError, load_insertions, load_reports, load_topology)
from services.scenario import Scenario

DATA = "data"


def path(name):
    return os.path.join(DATA, name)


@unittest.skipUnless(os.path.isdir(DATA), "run from the repo root")
class DataFilesTest(unittest.TestCase):
    def test_insertion_files_and_ascending_worst_case(self):
        heights = {}
        for name in ("aleatoria", "ascendente", "descendente"):
            info = load_insertions(Scenario(), path(f"carga_inserciones_{name}.json"))
            heights[name] = (info["comparison"]["avl"]["height"], info["comparison"]["bst"]["height"])
        self.assertEqual(heights["ascendente"][1], 59)         # BST degenerates into a chain
        self.assertLessEqual(heights["ascendente"][0], 7)      # AVL stays logarithmic

    def test_topologies(self):
        normal, stress = Scenario(), Scenario()
        self.assertEqual(load_topology(normal, path("topologia_normal.json"))["mode"], "normal")
        self.assertEqual(load_topology(stress, path("topologia_estres.json"))["mode"], "stress")
        self.assertGreater(stress.catalog.avl.height(), 30)
        self.assertEqual(len(stress.catalog.active), 40)

    def test_inconsistent_topology_is_rejected(self):
        sc = Scenario()
        with self.assertRaises(PersistenceError) as ctx:
            load_topology(sc, path("topologia_inconsistente.json"))
        self.assertGreaterEqual(len(ctx.exception.problems), 2)
        self.assertEqual(len(sc.catalog.active), 0)

    def test_burst_covers_every_decision(self):
        sc = Scenario()
        load_topology(sc, path("estado_inicial_rafaga.json"))
        sc.enqueue_reports(load_reports(path("rafaga_mixta.json")))
        decisions = []
        while len(sc.queue):
            decisions.append(sc.step().decision)
        for needed in ("alta", "confirmado", "antiguo", "corregido", "conflicto", "invalido"):
            self.assertIn(needed, decisions)

    def test_files_are_valid_json(self):
        for name in os.listdir(DATA):
            if name.endswith(".json"):
                with open(path(name), encoding="utf-8") as handle:
                    json.load(handle)


if __name__ == "__main__":
    unittest.main()
