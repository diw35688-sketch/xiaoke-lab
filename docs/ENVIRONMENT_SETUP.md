# asr_demo 本地运行环境

最后整理：2026-08-25（路径无关的一键启动）

> 当前状态：基础解释器和 `.venv` 均为 Python 3.11.9。2026-08-12 曾在受限
> 沙箱内出现“拒绝访问/无法创建进程”，在允许执行项目解释器后验证正常，证明问题来自
> 执行权限而不是虚拟环境损坏。不要用系统 Python 3.14 直接加载 Python 3.11
> 虚拟环境中的 C 扩展依赖。

## 1. 统一版本

本项目当前统一使用：

```text
Python 3.11.9 64-bit
虚拟环境：`<项目目录>\.venv`
```

Python 3.14 环境仅保留在 `.venv-py314` 作为备用实验环境，不作为项目验收环境。

## 2. 恢复或创建环境

先安装或恢复 Python 3.11.9 64-bit，再在项目目录执行。不要用 Python 3.14
直接加载旧 `.venv\Lib\site-packages`，否则 `_cffi_backend` 等二进制扩展会不兼容。

```powershell
py -3.11 -m venv --upgrade .venv

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

不要把 `.venv`、模型缓存、真实 `.env` 或录音文件提交到 Git。

## 3. 配置 DeepSeek

复制 `.env.example` 为 `.env`，再填写本地 API Key。`.env` 已由 `.gitignore` 排除。

统一理解链是唯一默认路径（2026-08-14 起，shadow flag 已删除），非精确命令会调用一次统一理解模型；
`.env` 中不再需要任何 `UNIFIED_SHADOW_*` 开关。

面向新用户的一键启动、转交和排错入口统一见 `docs/ONE_CLICK_START_GUIDE.md`。本文件保留开发环境和正式测试说明。

## 4. 验证环境

```powershell
.\.venv\Scripts\python.exe --version

.\.venv\Scripts\python.exe -c `
    "import dotenv, sherpa_onnx, sounddevice, soundfile, funasr, modelscope, torch; print('imports OK')"

.\.venv\Scripts\python.exe -B -m unittest discover `
    -s tests `
    -v
```

2026-08-12 的当前已验证基线：

```text
核心依赖 import OK
src.main import OK
Ran 422 tests
OK
```

本次验证命令与结果：

```text
基础 Python：Python 3.11.9
.venv Python：Python 3.11.9
dotenv/sherpa_onnx/sounddevice/soundfile/funasr/modelscope/torch 导入成功
src.main 导入成功（冷启动约 113 秒）
Ran 422 tests in 1.562s — OK
```

注意：受限执行环境中的 `Access denied` 不应直接判定 `.venv` 损坏。先在获准的项目
执行边界中运行 `python --version`；只有解释器本身仍失败，才进入重建虚拟环境流程。

## 5. 模型缓存说明

SenseVoice 和 FunASR VAD 模型缓存在用户目录的 ModelScope 缓存中，不保存在项目仓库。
当前 `AutoModel` 使用模型名和 `master` 修订，启动时可能联网检查模型文件。
后续任务将固定模型修订并关闭不必要的更新检查，以支持更快、更稳定的离线启动。

## 6. 本机可用工具

本机已安装 LibreOffice，可用其无头模式（headless）做文档格式转换（如
docx/pptx → pdf），路径固定为：

```text
C:\Users\dahli\LibreOffice\program\soffice.exe
```

验证记录：2026-08-16 确认该文件存在（2026-07-23 安装）。
命令行转换示例（PowerShell）：

```powershell
& 'C:\Users\dahli\LibreOffice\program\soffice.exe' `
    --headless --convert-to pdf --outdir <输出目录> <输入文件>
```
