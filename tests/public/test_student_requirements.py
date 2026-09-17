import pytest

from incidentzero.agent.policies import LoopGuard, ReplanPolicy
from incidentzero.agent.recovery import RetryPolicy
from incidentzero.model.errors import PermanentModelError, TransientModelError

from unittest.mock import MagicMock
from incidentzero.agent.controller import AgentController
from incidentzero.model.scripted import ScriptedModelClient
from incidentzero.domain.models import ToolCall, ModelReply
from incidentzero.telemetry.budget import BudgetManager
from incidentzero.telemetry.trace import TraceRecorder

@pytest.mark.student
def test_replan_policy_recognizes_stale_world():
    policy = ReplanPolicy()
    assert policy.should_replan({"status": "stale_precondition", "retryable": True}) is True


@pytest.mark.student
def test_replan_policy_recognizes_approval_denial():
    policy = ReplanPolicy()
    assert policy.should_replan({"status": "approval_denied", "retryable": False}) is True


@pytest.mark.student
def test_loop_guard_detects_exact_repeat():
    guard = LoopGuard(max_same_action_repeats=2)
    args = {"service": "checkout-service", "replicas": 4}
    assert guard.record("scale_service", args) is False
    assert guard.record("scale_service", args) is False
    assert guard.record("scale_service", args) is True


@pytest.mark.student
def test_retry_policy_retries_transient_only():
    calls = {"n": 0}
    sleeps = []
    retry = RetryPolicy(max_attempts=3, sleeper=lambda s: sleeps.append(s))

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientModelError("429")
        return "ok"

    assert retry.call_model(flaky) == "ok"
    assert calls["n"] == 3

    def permanent():
        raise PermanentModelError("bad request")

    with pytest.raises(PermanentModelError):
        retry.call_model(permanent)

#--------------------- Additional 10 Test Cases ---------------------
DUMMY_PLAN = {
    "hypothesis": "Test hypothesis",
    "rationale_summary": "Test rationale",
    "steps": [{"step_id": "S1", "objective": "Test objective", "success_signal": "Test signal"}]
}

@pytest.fixture
def base_controller_setup():
    tools = MagicMock()
    tools.validate.return_value = (True, "")
    tools.environment.world_version = 1
    tools.execute.return_value = {"status": "ok", "incident_id": "INC-123"}
    
    approval = MagicMock()
    budget = BudgetManager(max_llm_calls=14, max_tool_calls=28)
    trace = TraceRecorder(path="dummy_path.jsonl")
    
    return tools, approval, budget, trace

@pytest.mark.student
def test_high_risk_action_blocked_on_approval_denial(base_controller_setup):
    tools, approval, budget, trace = base_controller_setup
    
    mock_model = ScriptedModelClient(
        decisions=[
            ModelReply(content="Executing failover.", tool_calls=[ToolCall(id="call_1", name="failover_database", arguments={})]),
            ModelReply(content="Escalating.", tool_calls=[ToolCall(id="call_2", name="escalate_incident", arguments={})])
        ],
        structured_outputs=[DUMMY_PLAN, DUMMY_PLAN] 
    )
    
    approval.request_approval.return_value = False
    controller = AgentController(mock_model, tools, approval, budget, trace)
    
    # Only the failover action should trigger the critical boundary
    controller.risk.get_level = MagicMock(side_effect=lambda tool: "Critical" if tool == "failover_database" else "Low")
    
    controller.run()
    
    # Assert
    # call_count is 2: 'get_incident' (bootstrap) + 'escalate_incident' (terminal fallback)
    assert tools.execute.call_count == 2
    
    # Explicitly prove that the high-risk action never reached the simulator boundary[cite: 1]
    executed_tools = [call.args[0] for call in tools.execute.call_args_list]
    assert "failover_database" not in executed_tools
    assert "escalate_incident" in executed_tools
    
    messages_str = str(controller.state.messages)
    assert "approval_denied" in messages_str

@pytest.mark.student
def test_low_risk_action_bypasses_approval(base_controller_setup):
    tools, approval, budget, trace = base_controller_setup
    
    mock_model = ScriptedModelClient(
        decisions=[
            ModelReply(content="Getting metrics.", tool_calls=[ToolCall(id="call_1", name="get_metrics", arguments={"service": "checkout-service"})]),
            ModelReply(content="Escalating.", tool_calls=[ToolCall(id="call_2", name="escalate_incident", arguments={})])
        ],
        structured_outputs=[DUMMY_PLAN]
    )
    
    controller = AgentController(mock_model, tools, approval, budget, trace)
    controller.risk.get_level = MagicMock(return_value="Low")
    
    controller.run()
    
    # Assert
    approval.request_approval.assert_not_called()
    tools.execute.assert_any_call("get_metrics", {"service": "checkout-service"})

@pytest.mark.student
def test_stale_precondition_forces_replan(base_controller_setup):
    tools, approval, budget, trace = base_controller_setup
    
    mock_model = ScriptedModelClient(
        decisions=[
            ModelReply(content="Scaling.", tool_calls=[ToolCall(id="call_1", name="scale_service", arguments={"expected_world_version": 1})]),
            ModelReply(content="Escalating.", tool_calls=[ToolCall(id="call_2", name="escalate_incident", arguments={})])
        ],
        structured_outputs=[DUMMY_PLAN, DUMMY_PLAN]
    )
    
    tools.environment.world_version = 2
    
    controller = AgentController(mock_model, tools, approval, budget, trace)
    controller.run()
    
    # Assert
    messages_str = str(controller.state.messages)
    assert "stale_precondition" in messages_str

@pytest.mark.student
def test_premature_close_rejected_without_verification(base_controller_setup):
    tools, approval, budget, trace = base_controller_setup
    
    mock_model = ScriptedModelClient(
        decisions=[
            ModelReply(content="Closing prematurely.", tool_calls=[ToolCall(id="call_1", name="close_incident", arguments={})]),
            ModelReply(content="Escalating.", tool_calls=[ToolCall(id="call_2", name="escalate_incident", arguments={})])
        ],
        structured_outputs=[DUMMY_PLAN, DUMMY_PLAN]
    )
    
    controller = AgentController(mock_model, tools, approval, budget, trace)
    controller.run()
    
    # Assert
    messages_str = str(controller.state.messages)
    assert "unverified_closure" in messages_str or "Cannot close incident" in messages_str

@pytest.mark.student
def test_failed_verification_triggers_replan(base_controller_setup):
    tools, approval, budget, trace = base_controller_setup
    
    mock_model = ScriptedModelClient(
        decisions=[
            ModelReply(content="Verifying.", tool_calls=[ToolCall(id="call_1", name="verify_recovery", arguments={})]),
            ModelReply(content="Escalating.", tool_calls=[ToolCall(id="call_2", name="escalate_incident", arguments={})])
        ],
        structured_outputs=[DUMMY_PLAN, DUMMY_PLAN]
    )
    
    # Sequence: 1. bootstrap, 2. failed verify, 3. successful escalate
    tools.execute.side_effect = [
        {"status": "ok", "incident_id": "INC-123"},
        # Added "name" here so the ReplanPolicy can identify what tool failed
        {"status": "ok", "criteria_met": False, "name": "verify_recovery"}, 
        {"status": "ok"} 
    ]
    
    controller = AgentController(mock_model, tools, approval, budget, trace)
    controller.planner.revise = MagicMock(return_value="Revised Plan")
    
    controller.run()
    
    # Assert
    controller.planner.revise.assert_called_once()

# --------------------------------------------------------------------
from incidentzero.model.errors import TransientModelError, PermanentModelError

@pytest.mark.student
def test_loop_guard_blocks_redundant_execution(base_controller_setup):
    tools, approval, budget, trace = base_controller_setup
    
    # Arrange: Agent stubbornly tries to scale the service three times in a row
    mock_model = ScriptedModelClient(
        decisions=[
            ModelReply(content="Scaling", tool_calls=[ToolCall(id="c1", name="scale_service", arguments={"replicas": 4})]),
            ModelReply(content="Scaling again", tool_calls=[ToolCall(id="c2", name="scale_service", arguments={"replicas": 4})]),
            ModelReply(content="Scaling third time", tool_calls=[ToolCall(id="c3", name="scale_service", arguments={"replicas": 4})]),
            ModelReply(content="Escalating.", tool_calls=[ToolCall(id="c4", name="escalate_incident", arguments={})])
        ],
        structured_outputs=[DUMMY_PLAN, DUMMY_PLAN]
    )
    
    controller = AgentController(mock_model, tools, approval, budget, trace)
    controller.risk.get_level = MagicMock(return_value="Low")
    
    # Act
    controller.run()
    
    # Assert: The loop guard should intercept the 3rd identical attempt
    messages_str = str(controller.state.messages)
    assert "loop_detected" in messages_str or "Action repeated excessively" in messages_str

@pytest.mark.student
def test_invalid_tool_name_returns_error_to_model(base_controller_setup):
    tools, approval, budget, trace = base_controller_setup
    
    # Arrange: Agent hallucinates a tool
    mock_model = ScriptedModelClient(
        decisions=[
            ModelReply(content="Using magic tool.", tool_calls=[ToolCall(id="c1", name="magic_fix", arguments={})]),
            ModelReply(content="Escalating.", tool_calls=[ToolCall(id="c2", name="escalate_incident", arguments={})])
        ],
        structured_outputs=[DUMMY_PLAN, DUMMY_PLAN]
    )
    
    # Mock the tool validation boundary to reject it[cite: 1]
    tools.validate.side_effect = lambda name, args: (False, f"Unknown tool: {name}") if name == "magic_fix" else (True, "")
    
    controller = AgentController(mock_model, tools, approval, budget, trace)
    
    # Act
    controller.run()
    
    # Assert: Controller catches the validation failure gracefully
    messages_str = str(controller.state.messages)
    assert "validation_error" in messages_str
    assert "Unknown tool" in messages_str

@pytest.mark.student
def test_transient_model_error_retries_and_recovers(base_controller_setup):
    tools, approval, budget, trace = base_controller_setup
    
    mock_model = ScriptedModelClient(
        decisions=[
            ModelReply(content="Escalating.", tool_calls=[ToolCall(id="c1", name="escalate_incident", arguments={})])
        ],
        structured_outputs=[DUMMY_PLAN]
    )
    
    # Arrange: Simulate HTTP 429 Too Many Requests on the first two calls, success on the third
    mock_model.decide = MagicMock(side_effect=[
        TransientModelError("429 Too Many Requests"),
        TransientModelError("503 Service Unavailable"),
        ModelReply(content="Escalating.", tool_calls=[ToolCall(id="c1", name="escalate_incident", arguments={})])
    ])
    
    controller = AgentController(mock_model, tools, approval, budget, trace)
    
    # Act
    controller.run()
    
    # Assert: The retry loop absorbed the failures and succeeded on the 3rd try
    assert mock_model.decide.call_count == 3
    assert budget.llm_calls >= 3 # Proves budget was consumed on failed retries[cite: 1]

@pytest.mark.student
def test_budget_exhaustion_forces_safe_termination(base_controller_setup):
    tools, approval, budget, trace = base_controller_setup
    
    # Arrange: An agent that never calls a terminal tool
    mock_model = ScriptedModelClient(
        decisions=[
            ModelReply(content="Metrics.", tool_calls=[ToolCall(id="c1", name="get_metrics", arguments={})]),
            ModelReply(content="Logs.", tool_calls=[ToolCall(id="c2", name="get_logs", arguments={})]),
            ModelReply(content="More logs.", tool_calls=[ToolCall(id="c3", name="get_logs", arguments={})])
        ],
        structured_outputs=[DUMMY_PLAN]
    )
    
    # Severely restrict the internal resource budget[cite: 1]
    restricted_budget = BudgetManager(max_llm_calls=2, max_tool_calls=5)
    
    controller = AgentController(mock_model, tools, approval, restricted_budget, trace)
    controller.risk.get_level = MagicMock(return_value="Low")
    
    # Act
    outcome = controller.run()
    
    # Assert: Safely terminates instead of looping forever or crashing
    assert outcome.status == "budget_exhausted"
    assert "exhausted" in outcome.summary

@pytest.mark.student
def test_schema_failure_caught_during_replanning(base_controller_setup):
    tools, approval, budget, trace = base_controller_setup
    
    # Arrange: Agent fails verification, triggering a replan[cite: 1]
    mock_model = ScriptedModelClient(
        decisions=[
            ModelReply(content="Verifying.", tool_calls=[ToolCall(id="c1", name="verify_recovery", arguments={})]),
            ModelReply(content="Escalating.", tool_calls=[ToolCall(id="c2", name="escalate_incident", arguments={})])
        ],
        structured_outputs=[DUMMY_PLAN]
    )
    
    tools.execute.side_effect = [
        {"status": "ok", "incident_id": "INC-123"},
        {"status": "ok", "criteria_met": False, "name": "verify_recovery"}, 
        {"status": "ok"} 
    ]
    
    controller = AgentController(mock_model, tools, approval, budget, trace)
    
    # Mock the planner to throw a schema exception when it attempts to revise
    controller.planner.revise = MagicMock(side_effect=PermanentModelError("json_validate_failed"))
    
    # Act
    controller.run()
    
    # Assert: The controller catches the schema exception and injects a warning rather than crashing
    messages_str = str(controller.state.messages)
    assert "WARNING: Your previous attempt to revise the plan failed" in messages_str