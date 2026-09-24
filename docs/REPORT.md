# Engineering Report - Assignment 1

## 1. Architecture
The system architecture is designed as a modular, agentic feedback loop centered around a core Orchestrator. This Orchestrator manages the lifecycle of a task from inception to completion, maintaining a strict separation between reasoning and execution.

### Runtime and Orchestration
The runtime environment consists of a stateless execution engine that interfaces with a Long-Term Memory (LTM) module. Each request initializes a session context that captures the global objective. The Orchestrator utilizes a "Reason-Act" (ReAct) pattern, where the Large Language Model (LLM) generates a thought, selects a tool, and awaits the observation before proceeding.

### Planner and State Management
The Planner is a high-level component that decomposes the primary objective into a Directed Acyclic Graph (DAG) of sub-tasks. The State is maintained as a JSON object containing:
*   **Current Plan:** The sequence of intended actions.
*   **Execution History:** A log of tool inputs and outputs.
*   **World State Model:** A simplified representation of the environment (e.g. file structures or API states) derived from observations.

### Validation and Approval
Before any tool execution, a Validation layer checks the LLM output against a predefined schema. If an action is classified as "High-Risk" (e.g., system configuration changes or data deletion), the system enters an "Approval Pending" state, halting execution until a human operator or a high-confidence supervisor model provides a signature.

### Retry and Tracing
The system employs an exponential backoff strategy for transient failures. Each step is logged via an integrated tracing provider. Traces capture the raw prompt, the model's completion, tool latency, and token consumption, allowing for post-hoc analysis of "hallucination loops" or inefficient planning.

### Simulator Boundary
The Simulator Boundary acts as an abstraction layer. The agent logic does not interact directly with the OS or external APIs. Instead, it interacts with a "World Interface" that can be swapped between a production environment and a sandboxed simulator. This ensures that the agent's internal reasoning remains consistent regardless of the underlying infrastructure.
## 2. Planning and re-planning strategy
The planning strategy follows a "Lazy Commitment" model. While a global plan is generated at the start, the agent is encouraged to refine its trajectory based on real-time environmental feedback.
## 3. Failure handling
- **Malformed Model Output:** Schema/tool errors trigger "System Feedback" asking the LLM for a correction.
- **Transient Failures:** Retried in three tiers (Initial, 2s, 10s).
- **Stale World Version:** Resource changes prompt a "Refresh and Re-plan" cycle.
- **Approval Denial:** Denied requests act as hard constraints, requiring an alternative path or reporting the task as "Impossible."
- **Budget Exhaustion:** Hitting cost or time limits triggers a "Graceful Exit" with saved state and progress summary.


## 4. Safety and stopping
### Approval Actions
To ensure system integrity, the following actions strictly require manual or supervisor approval:

- **Destructive Operations:** rm, delete_table, format_disk.
- **External Communication:** send_email, post_webhook.
- **Resource Escalation:** Modifying IAM roles or increasing instance sizes.

### Proof of Recovery
Recovery is not assumed; it must be proven. After a failure, the agent is required to perform a "Validation Action" (e.g., a ls or grep check) to confirm that the environment has returned to a stable state or that the corrective action was successful. A task is only marked "Recovered" when the observation matches the recovery criteria defined in the planner.

## 5. Evaluation
### Scenarios:
**public-a:**
```Json
{
  "student_id": "25I-7605",
  "scenario": "public-a",
  "incident": {
    "status": "ok",
    "tool": "get_incident",
    "world_version": 1,
    "evidence_id": "EV-0001",
    "data": {
      "incident_id": "INC-898630",
      "title": "Checkout errors increased after a production change",
      "severity": "SEV-1",
      "customer_impact": "Checkout completion rate is below the 99% service objective; customer-facing errors are active.",
      "suspected_service": "payment-service",
      "operator_note": "A dashboard note suggests a recent traffic increase may be involved.",
      "objective": "Restore checkout success >=99%, p95 <=800ms, and critical services to healthy state."
    }
  },
  "note": "Root cause is intentionally not printed. Investigate through tools."
}
```
**Outcome**
```Json
{
  "status": "escalated",
  "summary": "Autonomous remediation aborted; incident escalated with gathered evidence.",
  "llm_calls": 12,
  "tool_calls": 12,
  "final_world_version": 5,
  "evidence_ids": [
    "EV-0001",
    "EV-0002",
    "EV-0003",
    "EV-0004",
    "EV-0005",
    "EV-0006",
    "EV-0007",
    "EV-0008",
    "EV-0009",
    "EV-0010",
    "EV-0011",
    "EV-0012"
  ],
  "trace_path": "traces/25I-7605_public-a.jsonl"
}
```
**public-b:**
```Json
{
  "student_id": "25I-7605",
  "scenario": "public-b",
  "incident": {
    "status": "ok",
    "tool": "get_incident",
    "world_version": 1,
    "evidence_id": "EV-0001",
    "data": {
      "incident_id": "INC-501756",
      "title": "Inventory requests are timing out intermittently",
      "severity": "SEV-1",
      "customer_impact": "Checkout completion rate is below the 99% service objective; customer-facing errors are active.",
      "suspected_service": "order-service",
      "operator_note": "Alert correlation tentatively points to checkout-service.",
      "objective": "Restore checkout success >=99%, p95 <=800ms, and critical services to healthy state."
    }
  },
  "note": "Root cause is intentionally not printed. Investigate through tools."
}
```
**Outcome**
```Json
{
  "status": "budget_exhausted",
  "summary": "LLM-call budget exhausted",
  "llm_calls": 14,
  "tool_calls": 12,
  "final_world_version": 3,
  "evidence_ids": [
    "EV-0001",
    "EV-0002",
    "EV-0003",
    "EV-0004",
    "EV-0005",
    "EV-0006",
    "EV-0007",
    "EV-0008",
    "EV-0009",
    "EV-0010",
    "EV-0011"
  ],
  "trace_path": "traces/25I-7605_public-b.jsonl"
}
```

**public-c:**
```Json
{
  "student_id": "25I-7605",
  "scenario": "public-c",
  "incident": {
    "status": "ok",
    "tool": "get_incident",
    "world_version": 1,
    "evidence_id": "EV-0001",
    "data": {
      "incident_id": "INC-602239",
      "title": "Cart sessions show inconsistent state after cache schema migration",
      "severity": "SEV-2",
      "customer_impact": "Checkout completion rate is below the 99% service objective; customer-facing errors are active.",
      "suspected_service": "payment-service",
      "operator_note": "The incident ticket contains no confirmed root cause.",
      "objective": "Restore checkout success >=99%, p95 <=800ms, and critical services to healthy state."
    }
  },
  "note": "Root cause is intentionally not printed. Investigate through tools."
}
```
**Outcome**
```Json
{
  "status": "budget_exhausted",
  "summary": "Agent call budget exhausted before safe termination.",
  "llm_calls": 14,
  "tool_calls": 11,
  "final_world_version": 3,
  "evidence_ids": [
    "EV-0001",
    "EV-0002",
    "EV-0003",
    "EV-0004",
    "EV-0005",
    "EV-0006",
    "EV-0007",
    "EV-0008"
  ],
  "trace_path": "traces/25I-7605_public-c.jsonl"
}
```

**Table: Summary of the Agent's latest execution logs**

| Scenario | Outcome Status | LLM Calls | Tool Calls | Final World Version | Evidence Collected | Trace Path |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **public-a** | Escalated | 12 | 12 | 5 | 12 items | `traces/25I-7605_public-a.jsonl` |
| **public-b** | Budget Exhausted | 14 | 12 | 3 | 11 items | `traces/25I-7605_public-b.jsonl` |
| **public-c** | Budget Exhausted | 14 | 11 | 3 | 8 items | `traces/25I-7605_public-c.jsonl` |

## 6. Three failure traces
Based on the execution logs, here are three instances where the agent's initial plan or action encountered a failure, along with how it adapted and recovered.

### Trace 1: Insufficient Remediation and Escalation (public-a)
*   **Initial Action:** After identifying that `checkout-service` was unhealthy following a recent rollout, the agent attempted to fix the issue by using `restart_service` and subsequently using `scale_service` to increase replicas to 2.
*   **Failure:** Neither the restart nor the scaling resolved the underlying root cause, as the service continued to experience high error rates and latency.
*   **Learning:** The agent recognized that the `checkout-service` remained unhealthy despite its interventions and determined that the root cause was unknown and could not be resolved using the available safe actions.
*   **Recovery:** Instead of entering a destructive loop, the agent gracefully aborted the autonomous remediation and used the `escalate_incident` tool, successfully handing off six pieces of collected evidence for further human investigation.

### Trace 2: Transient Telemetry Failure (public-b)
*   **Initial Action:** While investigating intermittent timeouts, the agent called `get_metrics` for the `checkout-service`.
*   **Failure:** The tool execution was rejected with a `transient_error` due to a "Simulated telemetry backend timeout for get_metrics."
*   **Learning:** The agent correctly interpreted the feedback that this was a retryable, transient infrastructure issue rather than a permanent failure or hallucinated tool.
*   **Recovery:** The agent waited and re-issued the identical `get_metrics` tool call on the subsequent turn, which successfully returned the error rate and CPU metrics for the service.

### Trace 3: Stale Precondition on Cache Execution (public-c)
*   **Initial Action:** The agent attempted to execute the `clear_cache` tool on `redis-cache` using `expected_world_version: 1`.
*   **Failure:** The system blocked the action, returning a `stale_precondition` error because the actual world version had incremented to 2 ("World changed after your observation. Re-observe before taking this action.").
*   **Learning:** The agent realized it was operating on an outdated snapshot of the environment and needed to refresh its state before modifying the cache.
*   **Recovery:** The agent performed a re-observation by calling `get_service_health` for `redis-cache`. After updating its internal state, it re-issued the `clear_cache` command with the correct `expected_world_version: 2`, which executed successfully.

## 7. Limitations
**1. Context Window Decay:** As the execution history grows, the agent occasionally loses track of the initial constraints, leading to "Plan Drift."<br>

**2. Latency Bottlenecks:** The sequential nature of the ReAct loop means that complex tasks involving many small tool calls take a significant amount of wall-clock time.<br>

**3. Recursive Logic Traps:** In cases with stale state, the agent sometimes enters a loop of retrying the same incorrect action because the "Environmental Feedback" is not sufficiently descriptive to break the hallucination.

