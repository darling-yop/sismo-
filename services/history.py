"""Bounded undo history of independent pre-action state snapshots."""

from core.stack import Stack


class History:
    def __init__(self, limit=200):
        self.limit = limit
        self._stack = Stack()

    def push(self, label, before, summary="", metrics=None):
        self._stack.push({"label": label, "summary": summary,
                          "metrics": metrics or {}, "before": before})
        slack = max(10, self.limit // 4)
        if len(self._stack) > self.limit + slack:
            kept = self._stack.to_list()[-self.limit:]
            self._stack = Stack()
            for entry in kept:
                self._stack.push(entry)

    def pop(self):
        return self._stack.pop()

    def is_empty(self):
        return self._stack.is_empty()

    def __len__(self):
        return len(self._stack)

    def entries(self):
        """Return (label, summary) pairs from oldest to newest."""
        return [(entry["label"], entry["summary"]) for entry in self._stack.to_list()]

    def log(self):
        """Return action labels, summaries, and metric deltas."""
        return [{"label": entry["label"], "summary": entry["summary"],
                 "metrics": dict(entry["metrics"])}
                for entry in self._stack.to_list()]