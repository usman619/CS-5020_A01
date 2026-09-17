from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from incidentzero.domain.models import RiskLevel


class RiskPolicy:
    def __init__(self, config_path: str | Path = "configs/risk_policy.json") -> None:
        self.mapping = json.loads(Path(config_path).read_text(encoding="utf-8"))

    def risk(self, tool_name: str) -> RiskLevel:
        return RiskLevel(self.mapping.get(tool_name, "critical"))

    def requires_human_approval(self, tool_name: str) -> bool:
        return self.risk(tool_name) in {RiskLevel.HIGH, RiskLevel.CRITICAL}


class ReplanPolicy:
    def should_replan(self, tool_result: dict) -> bool:
        #(A1): stale state, denied approval, non-retryable action failure,
        # contradictory evidence and verified non-recovery should not all be treated the same.
        """
        Returns True if the current plan must be abandoned.
        """
        status = tool_result.get("status")
        error = tool_result.get("error")
        
        # Check both keys to satisfy the test suite and controller logic
        if status in ["stale_precondition", "approval_denied"]:
            return True
        if error in ["stale_precondition", "approval_denied"]:
            return True
            
        # If verify_recovery ran but returned false, the hypothesis is likely wrong
        if tool_result.get("name") == "verify_recovery" and not tool_result.get("criteria_met", True):
            return True
            
        return False


class LoopGuard:
    def __init__(self, max_same_action_repeats: int = 2):
        # Match the initialization parameter expected by the test
        self.max_same_action_repeats = max_same_action_repeats
        self.action_history = {}

    def record(self, action_name: str, arguments: dict[str, Any]) -> bool:
        """Return True when the exact same action has repeated too often."""
        payload = json.dumps({"name": action_name, "args": arguments}, sort_keys=True)
        fingerprint = hashlib.md5(payload.encode()).hexdigest()

        self.action_history[fingerprint] = self.action_history.get(fingerprint, 0) + 1

        # Return TRUE if the execution count EXCEEDS the limit (Loop Detected)
        return self.action_history[fingerprint] > self.max_same_action_repeats
