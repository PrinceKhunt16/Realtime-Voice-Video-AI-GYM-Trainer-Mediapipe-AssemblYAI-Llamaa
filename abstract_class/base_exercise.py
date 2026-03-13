"""Base class for all exercise detectors."""

from abc import ABC, abstractmethod
from typing import Any


class BaseExercise(ABC):
    """Abstract base class for exercise pose detectors.

    Each subclass should implement:
      - process(landmarks) → dict of metrics
      - reset()           → clear state and rep count
    """

    def __init__(self):
        self.reps: int = 0
        self.stage: str | None = None  # e.g. "up" / "down"

    @abstractmethod
    def process(self, landmarks: Any) -> dict:
        """Analyse pose landmarks for one frame and return a metrics dict."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset rep count and internal state."""
        pass
