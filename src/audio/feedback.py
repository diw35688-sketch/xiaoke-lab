"""音频反馈：唤醒提示音与事件提示音。

提示音不是 TTS 朗读，只负责让用户知道“该看屏幕了”。
具体音色由 Windows winsound 提供，测试中可注入 Fake。
"""

import winsound

# 事件提示音只覆盖需要用户注意的消息类型。
# 普通 record_ack（成功记录）不发声，避免逐段打扰。
_EVENT_TONE_FLAGS = {
    "clarification": winsound.MB_ICONQUESTION,
    "confirmation_ack": winsound.MB_ICONASTERISK,
    "no_action_feedback": winsound.MB_ICONASTERISK,
    "answer_hint": winsound.MB_ICONASTERISK,
    "deny_result": winsound.MB_ICONEXCLAMATION,
    "warning": winsound.MB_ICONEXCLAMATION,
    "system_issue": winsound.MB_ICONHAND,
}


def play_wake_tone():
    winsound.MessageBeep(
        winsound.MB_OK
    )


def play_event_tone(kind: str) -> None:
    """按消息类型播放提示音；未登记类型不发声。"""

    flag = _EVENT_TONE_FLAGS.get(kind)
    if flag is not None:
        winsound.MessageBeep(flag)
