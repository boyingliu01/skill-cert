"""Deadline enforcement — hard global timeout for the evaluation pipeline.

Provides the ``Deadline`` dataclass that tracks elapsed time via
``time.monotonic()`` and exposes properties for remaining time, expiration
checks, and adaptive timeouts.

Usage::

    deadline = Deadline(max_total_time=3600.0)
    while not deadline.expired:
        ...
    if deadline.must_stop(grace_period=5.0):
        # wind down gracefully
        ...
    timeout = deadline.adapter_timeout(default=120)

Also provides ``PhaseTimer`` — a lightweight helper for structured progress
logging at phase boundaries within the evaluation pipeline.
"""

import logging
import math
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Deadline:
    """Hard deadline with monotonic time tracking.

    Parameters
    ----------
    start_time :
        Epoch from :func:`time.monotonic` (set automatically).
    max_total_time :
        Maximum wall-clock time in seconds.  ``float("inf")`` means no
        limit (default).

    Properties
    ----------
    elapsed
        Seconds since *start_time* (readonly).
    remaining
        Seconds until expiry (capped at 0).
    expired
        ``True`` when *remaining* ≤ 0.
    """

    start_time: float = field(default_factory=time.monotonic)
    max_total_time: float = float("inf")

    @property
    def elapsed(self) -> float:
        """Seconds elapsed since the deadline was created."""
        return time.monotonic() - self.start_time

    @property
    def remaining(self) -> float:
        """Seconds remaining before the deadline, clamped to 0."""
        if not math.isfinite(self.max_total_time):
            return float("inf")
        return max(0.0, self.max_total_time - self.elapsed)

    @property
    def expired(self) -> bool:
        """``True`` when *remaining* ≤ 0."""
        return self.remaining <= 0.0

    def must_stop(self, grace_period: float = 5.0) -> bool:
        """Return ``True`` if *remaining* ≤ *grace_period*.

        Use this to decide whether to start a new long-running operation.
        """
        return self.remaining <= grace_period

    def adapter_timeout(self, default: float = 120.0) -> float:
        """Return an adaptive timeout for a single LLM adapter call.

        The returned value is ``min(default, max(5, ceil(remaining)))``
        when *remaining* is finite, or *default* when there is no hard
        deadline.

        The 5-second floor prevents spurious network-level timeouts.
        """
        if not math.isfinite(self.remaining):
            return default
        return min(default, max(5.0, math.ceil(self.remaining)))

    def __repr__(self) -> str:
        return (
            f"Deadline(start_time={self.start_time:.2f}, "
            f"max_total_time={self.max_total_time:.0f}s, "
            f"elapsed={self.elapsed:.1f}s, "
            f"remaining={self.remaining:.1f}s, "
            f"expired={self.expired})"
        )


class PhaseTimer:
    """Lightweight structured progress logger for evaluation phases.

    Tracks elapsed time, item completion count, and optional deadline
    countdown.  Uses ``logger.info()`` for detailed progress messages.

    Parameters
    ----------
    phase_name :
        Short human-readable name for the phase (e.g. ``"testgen"``).
    item_count :
        Total number of items expected in this phase.
    deadline :
        Optional :class:`Deadline` to include remaining-time in messages.
    """

    def __init__(
        self,
        phase_name: str,
        item_count: int = 0,
        deadline: Deadline | None = None,
    ):
        self.phase_name = phase_name
        self.start_time = time.monotonic()
        self.item_count = item_count
        self.items_completed = 0
        self.deadline = deadline

    def log_progress(self, label: str = "") -> str:
        """Log and return a progress message string.

        Format (without deadline)::

            [phase] [N/M] label — X.Xs elapsed

        Format (with deadline)::

            [phase] [N/M] label — X.Xs elapsed, deadline: Ys remaining
        """
        elapsed = time.monotonic() - self.start_time
        count_part = f"[{self.items_completed}/{self.item_count}]" if self.item_count > 0 else ""
        msg = f"[{self.phase_name}]"
        if count_part:
            msg += f" {count_part}"
        if label:
            msg += f" {label}"
        msg += f" — {elapsed:.1f}s elapsed"
        if self.deadline is not None:
            remaining = self.deadline.remaining
            if math.isfinite(remaining):
                msg += f", deadline: {remaining:.0f}s remaining"
            else:
                msg += ", deadline: no limit"
        logger.info(msg)
        return msg
