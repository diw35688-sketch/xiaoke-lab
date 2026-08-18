# Live2D 模型工作区

这里存放由当前形象图生成的 Live2D 建模素材。

## 文件

| 文件 | 说明 |
|---|---|
| `assistant_portrait_transparent.png` | 原始透明立绘 |
| `assistant_portrait.psd` | 已拆成 15 层的 PSD，可直接导入 Live2D Cubism Editor |

## 用 Live2D Cubism Editor 打开

1. 下载并安装 Live2D Cubism Editor（官网：https://www.live2d.com/）
2. 打开 Cubism Editor
3. 新建模型项目，选择 `assistant_portrait.psd`
4. 检查图层命名，项目已按 Cubism 规范命名：
   - Hair_Back / Hair_Front
   - Body / Neck / Face
   - Eye_L / Eye_R / Brow_L / Brow_R
   - Nose / Mouth
   - Arm_L / Arm_R / Leg_L / Leg_R
   - Accessory
5. 在 Cubism Editor 中：
   - 给每个部件创建网格（Mesh）
   - 设置变形器（Deformer）
   - 配置参数：眼睛眨眼、嘴巴张合、头左右转、身体呼吸
6. 导出模型：
   ```
   .moc3
   .model3.json
   textures/
   physics3.json（可选）
   motions/（可选）
   ```

## 导出后

把导出文件夹放到本项目的 `web/frontend/live2d/`，告诉我，我负责在网页里接入并替换现在的 PNG 伪 Live2D。
