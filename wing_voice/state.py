from __future__ import annotations
import time

class AssistantState:
    """Single pending action and last verified change; intentionally no command queue."""
    def __init__(self, undo_max_age=300):
        self.busy = False
        self.pending = None
        self.last_change = None
        self.undo_max_age = undo_max_age

    def propose(self, action):
        if self.pending is not None:
            raise RuntimeError("A confirmation is already pending")
        self.pending = action
        return action

    def cancel(self):
        self.pending = None

    def confirmed(self):
        action = self.pending
        self.pending = None
        return action

    def record_verified_change(self, target, before, after, reverse_action):
        self.last_change = {
            "target": target, "before": before, "after": after,
            "reverseAction": reverse_action, "verifiedAt": time.time(),
        }

    def undo_candidate(self):
        if not self.last_change:
            return None
        if time.time() - self.last_change["verifiedAt"] > self.undo_max_age:
            return None
        if not self.last_change.get("reverseAction"):
            return None
        return self.last_change
