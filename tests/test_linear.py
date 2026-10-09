import unittest

from core.fifo import Queue
from core.stack import Stack


class TestStack(unittest.TestCase):
    def test_lifo_order(self):
        stack = Stack()
        for value in (1, 2, 3):
            stack.push(value)
        self.assertEqual(stack.peek(), 3)
        self.assertEqual([stack.pop(), stack.pop(), stack.pop()], [3, 2, 1])
        self.assertTrue(stack.is_empty())

    def test_pop_empty_raises(self):
        with self.assertRaises(IndexError):
            Stack().pop()


class TestQueue(unittest.TestCase):
    def test_fifo_order(self):
        queue = Queue()
        for value in (1, 2, 3):
            queue.enqueue(value)
        self.assertEqual(queue.to_list(), [1, 2, 3])
        self.assertEqual([queue.dequeue(), queue.dequeue(), queue.dequeue()], [1, 2, 3])
        self.assertTrue(queue.is_empty())

    def test_reuse_after_empty(self):
        queue = Queue()
        queue.enqueue(1)
        queue.dequeue()
        queue.enqueue(2)
        self.assertEqual(queue.to_list(), [2])
        self.assertEqual(len(queue), 1)

    def test_dequeue_empty_raises(self):
        with self.assertRaises(IndexError):
            Queue().dequeue()


if __name__ == "__main__":
    unittest.main()