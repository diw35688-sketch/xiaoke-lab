"""Single stateless entry point for playback permission evaluation."""

from __future__ import annotations

from src.core.playback_context import PlaybackContext
from src.core.playback_decision import PlaybackDecision
from src.core.playback_request import PlaybackRequest
from src.core.playback_rules import decide_playback


class PlaybackGate:
    """Expose playback rules without owning queues, clocks, or devices."""

    __slots__ = ()

    @staticmethod
    def evaluate(
        request: PlaybackRequest,
        context: PlaybackContext,
    ) -> PlaybackDecision:
        """Return the deterministic permission decision for one snapshot."""

        if not isinstance(request, PlaybackRequest):
            raise TypeError("request 必须是 PlaybackRequest。")
        if not isinstance(context, PlaybackContext):
            raise TypeError("context 必须是 PlaybackContext。")
        return decide_playback(request, context)
