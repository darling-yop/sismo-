"""Compare AVL and plain BST behavior for identical insertion orders."""

import random

from core.avl import AVL
from core.bst import BST


def build(keys):
    avl, bst = AVL(), BST()
    for key in keys:
        avl.insert(key)
        bst.insert(key)
    return avl, bst


def tree_stats(tree, keys):
    comparisons = sum(tree.find(key)[1] for key in keys)
    return {"size": tree.size,
            "root": tree.root.key.as_tuple() if tree.root else None,
            "height": tree.height(), "max_depth": tree.height(),
            "leaves": tree.leaf_count(), "search_comparisons": comparisons,
            "search_average": comparisons / len(keys) if keys else 0.0}


def compare(keys):
    keys = list(keys)
    avl, bst = build(keys)
    return {"avl": tree_stats(avl, keys), "bst": tree_stats(bst, keys)}


def insertion_orders(keys, seed=1):
    keys = list(keys)
    shuffled = list(keys)
    random.Random(seed).shuffle(shuffled)
    return {"original": keys, "ascending": sorted(keys),
            "descending": sorted(keys, reverse=True), "random": shuffled}