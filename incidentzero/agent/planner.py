from __future__ import annotations

from typing import Any

from incidentzero.domain.models import AgentPlan, PlanStep
from incidentzero.model.base import ModelClient


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "hypothesis": {"type": "string"},
        "rationale_summary": {"type": "string"},
        "steps": {
            "type": "array",
            "minItems": 2,
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "step_id": {"type": "string"},
                    "objective": {"type": "string"},
                    "success_signal": {"type": "string"},
                },
                "required": ["step_id", "objective", "success_signal"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["hypothesis", "rationale_summary", "steps"],
    "additionalProperties": False,
}


class Planner:
    def __init__(self, model: ModelClient) -> None:
        self.model = model

    def create(self, incident_observation: dict[str, Any], context: list[dict[str, Any]] | None = None) -> AgentPlan:
        """Create an explicit initial plan.

        Improved to ensure the model grounds its initial hypothesis purely on 
        the provided observation rather than assumptions.
        """
        messages = [
            {
                "role": "system", 
                "content": "You are an autonomous SRE Incident Commander. Create a structured investigation and remediation plan. Do NOT blindly trust the ticket's suspected root cause; rely on objective evidence."
            },
            {
                "role": "user", 
                "content": f"Incident observation: {incident_observation}"
            },
        ]
        
        # Append any existing context (e.g., system warnings) if provided
        if context:
            messages.extend(context)

        raw = self.model.structured(messages, "incident_plan", PLAN_SCHEMA)
        steps = [PlanStep(**row) for row in raw["steps"]]
        
        plan = AgentPlan(
            hypothesis=raw["hypothesis"], 
            steps=steps, 
            rationale_summary=raw["rationale_summary"]
        )
        # Initialize revision tracking
        plan.revision = 1
        return plan

    def revise(self, current: AgentPlan, trigger: dict[str, Any], state_summary: str) -> AgentPlan:
        """
        Task E: Plan Revision.
        Generates a new plan based on new evidence or failure triggers, ensuring the previous failed hypothesis is not blindly repeated.
        """
        messages = [
            {
                "role": "system", 
                "content": (
                    "You are an autonomous SRE Incident Commander updating an investigation plan. "
                    "The previous plan failed or was denied. Create a REVISED plan. "
                    "DO NOT repeat the exact same hypothesis. You must incorporate the new evidence.\n\n"
                    "CRITICAL JSON FORMATTING: The 'steps' array must contain flat objects ONLY. "
                    "Do NOT wrap step objects in an empty string key (e.g. {\"\": {...}} is forbidden). "
                    "Each item must be exactly: {\"step_id\": \"S1\", \"objective\": \"...\", \"success_signal\": \"...\"}"
                )
            },
            {
                "role": "user", 
                "content": f"""
                Previous Hypothesis (INVALIDATED): {current.hypothesis}
                Previous Rationale: {current.rationale_summary}
                
                Failure/Trigger Event: {trigger}
                Current Valid Evidence: {state_summary}
                
                Generate a revised structured plan with a NEW hypothesis. Retain relevant investigation steps if they are still useful, but alter the core remediation strategy based on the trigger.
                """
            },
        ]

        # Request a new structured plan from the model
        raw = self.model.structured(messages, "revised_incident_plan", PLAN_SCHEMA)
        
        # Construct the revised steps
        steps = [PlanStep(**row) for row in raw["steps"]]
        
        # Create the new plan object
        revised_plan = AgentPlan(
            hypothesis=raw["hypothesis"], 
            steps=steps, 
            rationale_summary=raw["rationale_summary"]
        )
        
        # Task E constraint: Explicitly increment the revision version to track plan evolution
        revised_plan.revision = getattr(current, "revision", 1) + 1
        
        return revised_plan