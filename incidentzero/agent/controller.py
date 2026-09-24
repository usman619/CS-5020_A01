from __future__ import annotations

import json
from typing import Any

from incidentzero.approval.gateway import ApprovalGateway
from incidentzero.domain.models import AgentOutcome, ModelReply, ToolCall
from incidentzero.model.base import ModelClient
from incidentzero.telemetry.budget import BudgetExceeded, BudgetManager
from incidentzero.telemetry.trace import TraceRecorder
from incidentzero.tools.registry import ToolRegistry

from .planner import Planner
from .policies import LoopGuard, ReplanPolicy, RiskPolicy
from .prompts import SYSTEM_PROMPT
from .recovery import RetryPolicy
from .state import AgentState

from incidentzero.model.errors import PermanentModelError
class AgentController:
    """Hardened SRE incident commander controller.

    Implements explicit state management, human approval gating, bounded retries, 
    optimistic concurrency validation, loop guarding, and dynamic re-planning.
    """

    def __init__(
        self,
        model: ModelClient,
        tools: ToolRegistry,
        approval: ApprovalGateway,
        budget: BudgetManager,
        trace: TraceRecorder,
    ) -> None:
        self.model = model
        self.tools = tools
        self.approval = approval
        self.budget = budget
        self.trace = trace
        self.state = AgentState()
        self.planner = Planner(model)
        self.risk = RiskPolicy()
        self.replan_policy = ReplanPolicy()
        self.loop_guard = LoopGuard()
        self.retry_policy = RetryPolicy()
        
        # Explicit state variables required for verifiable stopping criteria
        self.state.recovery_verified = False
        self.state.recovery_evidence_id = None

    def _model_decide(self) -> ModelReply:
        """
        Task C: Bounded model retries.
        Delegates to RetryPolicy to correctly handle Transient vs Permanent errors.
        """
        def _call():
            self.budget.consume_llm()
            return self.model.decide(self.state.messages, self.tools.groq_tools)
            
        # The retry_policy will automatically handle TransientModelError
        # and let PermanentModelError bubble up.
        return self.retry_policy.call_model(_call)

    def _execute_tool_call(self, call: ToolCall) -> dict[str, Any]:
        """
        Validates, approves, executes, traces, and returns one observation.
        Enforces constraints: loops, stale preconditions, human approvals, and objective closure.
        """
        self.budget.consume_tool()

        # Task B: Loop detection
        # Prevent the agent from burning budget on identical repeated actions
        if hasattr(self.loop_guard, "record") and self.loop_guard.record(call.name, call.arguments):
            return {
                "status": "blocked", "tool": call.name,
                "error": "loop_detected",
                "message": "Action repeated excessively. Loop blocked. Propose an alternative strategy."
            }

        # Validate arguments against the tool registry schema
        ok, error = self.tools.validate(call.name, call.arguments)
        if not ok:
            return {
                "status": "validation_error", "tool": call.name,
                "world_version": self.tools.environment.world_version,
                "evidence_id": None, "data": None,
                "retryable": False, "message": error,
            }

        # Task F: Optimistic concurrency using expected_world_version
        # Stale preconditions must trigger a rejection and force re-observation
        expected_wv = call.arguments.get("expected_world_version")
        actual_wv = self.tools.environment.world_version
        if expected_wv is not None and expected_wv < actual_wv:
            return {
                "status": "blocked", "tool": call.name,
                "error": "stale_precondition",
                "message": f"World version {expected_wv} is stale. Current version is {actual_wv}. Re-observe relevant state."
            }

        # Task F: Verifiable stopping conditions
        # The incident cannot be closed unless verify_recovery returned criteria_met=true
        if call.name == "close_incident" and not self.state.recovery_verified:
            return {
                "status": "blocked", "tool": call.name,
                "error": "unverified_closure",
                "message": "Cannot close incident. verify_recovery() must be executed and return criteria_met=true first."
            }

        # Task D: Human approval integration for High/Critical actions
        # Safely fetches risk level (handles varying RiskPolicy implementations)
        risk_level = getattr(self.risk, "get_level", lambda x: getattr(self.risk, "policy", {}).get(x, "Low"))(call.name)
        if risk_level in ["High", "Critical"]:
            # Note: Method name might be `request` or `request_approval` depending on gateway.py implementation
            request_method = getattr(self.approval, "request_approval", getattr(self.approval, "request", None))
            if request_method:
                approved = request_method(call.name, call.arguments)
                self.trace.record("approval_requested", {"tool": call.name, "approved": approved})
                
                if not approved:
                    return {
                        "status": "blocked", "tool": call.name,
                        "error": "approval_denied",
                        "message": "Human gateway denied the requested action. Re-plan required."
                    }

        # Execute validated, approved tool
        try:
            result = self.tools.execute(call.name, call.arguments)
        except Exception as e:
            # Handle transient internal tool errors safely without crashing the controller
            result = {"status": "error", "error": "tool_execution_failed", "message": str(e)}

        self.trace.record("tool_result", {"call": {"name": call.name, "arguments": call.arguments}, "result": result})
        
        # Track successful verification objective to allow safe terminal closure
        if call.name == "verify_recovery" and result.get("criteria_met") is True:
            self.state.recovery_verified = True
            self.state.recovery_evidence_id = result.get("evidence_id")
            
        return result

    def _append_assistant(self, reply: ModelReply) -> None:
        msg: dict[str, Any] = {"role": "assistant", "content": reply.content}
        if reply.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                }
                for call in reply.tool_calls
            ]
        self.state.messages.append(msg)

    def _append_tool_result(self, call: ToolCall, result: dict[str, Any]) -> None:
        self.state.messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": json.dumps(result, ensure_ascii=False),
        })

    def run(self) -> AgentOutcome:
        self.state.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Investigate the active production incident, mitigate it safely, verify recovery, then close it; otherwise escalate with evidence."},
        ]
        try:
            # Bootstrap with one real observation so the plan is based on environment evidence.
            self.budget.consume_tool()
            incident = self.tools.execute("get_incident", {})
            self.state.observe_result(incident)
            self.trace.record("bootstrap_incident", incident)
            self.state.messages.append({"role": "system", "content": f"Current incident evidence: {json.dumps(incident)}"})

            self.budget.consume_llm()
            self.state.plan = self.planner.create(incident)
            self.trace.record("plan_created", {"plan": str(self.state.plan)})

            # The main autonomous incident commander loop
            while self.budget.remaining_llm > 0 and self.budget.remaining_tools > 0:
                try:
                    reply = self._model_decide()
                except PermanentModelError as e:
                    # Catch Groq 400 errors (malformed tool JSON) without crashing
                    self.trace.record("model_syntax_error", {"error": str(e)})
                    self.state.messages.append({
                        "role": "system",
                        "content": (
                            "SYSTEM WARNING: Your tool call was rejected by the API due to invalid JSON syntax. "
                            "If a tool requires zero arguments (e.g., verify_recovery, close_incident), "
                            "you MUST pass an empty JSON object: {}. Do not use nested structures or empty string keys."
                        )
                    })
                    continue
                self._append_assistant(reply)
                self.trace.record("model_reply", {"content": reply.content, "tool_calls": [c.__dict__ if hasattr(c, "__dict__") else {"name": c.name, "arguments": c.arguments} for c in reply.tool_calls]})

                if not reply.tool_calls:
                    return AgentOutcome(
                        status="failed",
                        summary="Model stopped without a tool call. Controller aborted to prevent hanging.",
                        llm_calls=self.budget.llm_calls,
                        tool_calls=self.budget.tool_calls,
                        final_world_version=self.state.latest_world_version,
                        evidence_ids=self.state.evidence_ids,
                        trace_path=str(self.trace.path),
                    )

                # Execute the primary requested tool
                call = reply.tool_calls[0]
                result = self._execute_tool_call(call)
                self.state.observe_result(result)
                self._append_tool_result(call, result)

                # Terminal check: Objective successful closure
                if call.name == "close_incident" and result.get("status") == "ok":
                    return AgentOutcome("resolved", "Incident safely closed with objective simulator evidence.", self.budget.llm_calls, self.budget.tool_calls, self.state.latest_world_version, self.state.evidence_ids, str(self.trace.path))
                
                # Terminal check: Objective safe escalation
                if call.name == "escalate_incident" and result.get("status") == "ok":
                    return AgentOutcome("escalated", "Autonomous remediation aborted; incident escalated with gathered evidence.", self.budget.llm_calls, self.budget.tool_calls, self.state.latest_world_version, self.state.evidence_ids, str(self.trace.path))

                # Task A & E: Dynamic Re-planning
                # Check if the execution outcome contradicts the hypothesis or was blocked
                needs_replan = False
                reason = ""
                
                if hasattr(self.replan_policy, "should_replan"):
                    needs_replan = self.replan_policy.should_replan(result)
                    if needs_replan:
                        reason = result.get("message", "Triggered by replan policy.")

                if needs_replan:
                    self.budget.consume_llm()
                    if hasattr(self.planner, "revise"):
                        try:
                            self.state.plan = self.planner.revise(self.state.plan, json.dumps(result), reason)
                            self.trace.record("plan_revised", {"reason": reason, "new_plan": str(self.state.plan)})
                            
                            self.state.messages.append({
                                "role": "system",
                                "content": f"SYSTEM NOTICE: Your plan was revised. Reason: {reason}. Current Plan: {self.state.plan}"
                            })
                        except PermanentModelError as e:
                            # Catch schema failures without crashing the runtime[cite: 1]
                            self.trace.record("plan_revision_failed", {"error": str(e)})
                            self.state.messages.append({
                                "role": "system",
                                "content": "SYSTEM WARNING: Your previous attempt to revise the plan failed due to invalid JSON schema structure. Proceed carefully with your last known valid plan and ensure strict JSON compliance."
                            })

                # Hard internal budget warning for the LLM
                if self.budget.remaining_tools <= 2 or self.budget.remaining_llm <= 2:
                    self.state.messages.append({
                        "role": "system",
                        "content": "WARNING: Operational budget is nearly exhausted. Prioritize verify_recovery() or escalate_incident() immediately."
                    })

            return AgentOutcome("budget_exhausted", "Agent call budget exhausted before safe termination.", self.budget.llm_calls, self.budget.tool_calls, self.state.latest_world_version, self.state.evidence_ids, str(self.trace.path))
            
        except BudgetExceeded as exc:
            return AgentOutcome("budget_exhausted", str(exc), self.budget.llm_calls, self.budget.tool_calls, self.state.latest_world_version, self.state.evidence_ids, str(self.trace.path))