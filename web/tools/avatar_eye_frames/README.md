# 72方向眼睛帧生成包

## 输出规格

- 角色画布：`1086x1448` RGBA PNG
- 方向帧：72张，每5度一张
- 中心帧：1张
- 坐标：`000=右`、`090=下`、`180=左`、`270=上`
- 最终目录：`frontend/assets/eye_frames/`

## 生成顺序

1. `look_center.png`
2. 八个锚点：`000/045/090/135/180/225/270/315`
3. 每两个锚点之间按5度插帧
4. 运行 `validate_frames.py`
5. 将全部73帧复制到 `frontend/assets/eye_frames/`

每次生成必须同时提交：角色母版、眼睛身份裁剪、对应的`target_XXX.png`。中间帧额外提交相邻两个已批准锚点。不要以上一张中间帧作为唯一参考，避免累计漂移。

## 准备参考图

```powershell
python tools/avatar_eye_frames/prepare_generation_pack.py `
  --master frontend/assets/assistant_portrait_transparent.png `
  --out-dir tools/avatar_eye_frames/generated
```

## 校验

```powershell
python tools/avatar_eye_frames/validate_frames.py `
  --manifest tools/avatar_eye_frames/manifest.json `
  --frames-dir frontend/assets/eye_frames
```

校验项：文件齐全、1086x1448、RGBA、透明四角、非空alpha、所有可见像素位于眼睛安全框内。

## Codex中转状态

本次已尝试本机Codex自定义中转和官方登录通道：自定义通道返回401/404，官方通道请求超时。内置图像生成必须接收到实际图片附件，不能仅凭D盘路径读取参考图。待中转恢复或在对话中上传角色母版后，可直接使用`PROMPT_TEMPLATE.md`继续生成。
