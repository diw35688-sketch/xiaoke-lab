# Interruptible TTS Contract Implementation Plan

> **For Codex:** 本计划用于本轮“可打断TTS纯逻辑地基”的实现与验收；不接真实TTS、不碰声卡、不修改主循环。

**Goal:** 建立基于代数计数器的可打断TTS后端、播放结果和工厂契约。

**Architecture:** `CancelScope`维护可回绕的播报代数；`InterruptibleTTSPlayer`捕获代数并在每个音频块进入sink前检查是否过时。TTS后端通过`Protocol`按块生成`int16`单声道音频，默认注入空sink；工厂仅返回`NullTTSBackend`占位后端。

**Tech Stack:** Python 3.11、`dataclasses`、`typing.Protocol`、NumPy、标准库`unittest`。

---

### Task 1: 先建立行为测试

**Files:**
- Create: `tests/test_tts.py`

覆盖正常完成、逐块取消、取消后新播报、后端异常、空文本/零块、代数回绕、协议运行时检查和工厂选择。

### Task 2: 实现代数取消范围

**Files:**
- Create: `src/audio/cancel_scope.py`

使用32位代数计数器；明确单写者+多读者的GIL线程安全前提；不实现异步输出丢弃状态。

### Task 3: 实现TTS后端契约和空后端

**Files:**
- Create: `src/audio/tts_backend.py`
- Create: `src/audio/null_tts_backend.py`

后端只约定采样率和按块生成器；空后端不生成音频，作为联调占位。

### Task 4: 实现播放器和结果结构

**Files:**
- Create: `src/audio/tts_player.py`

播放器依赖注入后端、取消范围和sink；每块播放前检查代数；把后端或sink异常转为`FAILED`。

### Task 5: 实现工厂和配置

**Files:**
- Create: `src/audio/tts_factory.py`
- Modify: `src/config.py`
- Modify: `.env.example`

配置默认使用`null`，预留`TTS_ENABLED`开关；工厂未知名称在实例化前明确失败。

### Task 6: 回归与文档收尾

**Files:**
- Modify: `docs/PROJECT_TASK_CHECKLIST.md`
- Modify: `LEARNING_REVIEW_FROM_DEVELOPMENT.md`
- Modify: `docs/NEXT_SESSION_HANDOFF_2026-08-09.md`

运行TTS专项测试和全量`unittest discover`，检查中文字符未损坏并记录测试基线。
