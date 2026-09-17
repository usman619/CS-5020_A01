from __future__ import annotations

import time
import random
from collections.abc import Callable
from typing import TypeVar

from incidentzero.model.errors import TransientModelError

T = TypeVar("T")


class RetryPolicy:
    def __init__(self, max_attempts: int = 3, sleeper: Callable[[float], None] = time.sleep) -> None:
        self.max_attempts = max_attempts
        self.sleeper = sleeper

    def call_model(self, fn: Callable[[], T]) -> T:
        """
        Task C: Bounded model retries.
        Executes the provided model function with bounded exponential backoff.
        Only retries TransientModelError. Permanent errors bubble up immediately.
        """
        base_delay = 1.0

        for attempt in range(self.max_attempts):
            try:
                # Attempt to execute the model call
                return fn()
                
            except TransientModelError as e:
                # If we have exhausted the configured retry budget, bubble up the error
                # to prevent infinite loops and respect the internal resource budget.
                if attempt == self.max_attempts - 1:
                    raise e
                
                # Calculate exponential backoff: base_delay * (2 ^ attempt)
                # Adding a small random jitter prevents "thundering herd" issues 
                # against the Groq API provider.
                delay = (base_delay * (2 ** attempt)) + random.uniform(0.1, 0.5)
                
                # Use the injected sleeper so tests can mock it and run instantly
                self.sleeper(delay)
                
            # Note: We deliberately do NOT catch PermanentModelError, standard Exceptions,
            # or validation errors here. Those are logically fatal to the current execution
            # path and must bubble up to the controller to trigger a re-plan or failure.