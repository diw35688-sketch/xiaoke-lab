# 一键启动与转交指南（Windows）

这份指南给第一次接触本项目的人。最短结论：**把完整项目文件夹放到任意可写目录，安装 Python 3.11，然后双击 `start.bat`。** 项目不再依赖开发者电脑上的固定路径。

## 1. 你需要准备什么

- Windows 10/11，64 位；
- Python 3.11（安装时勾选 `Add python.exe to PATH`）；
- 可联网：首次运行要安装 Python 依赖、下载 SenseVoice 模型；
- 一个兼容 OpenAI 接口的大模型 API 密钥；
- Chrome 或 Edge（使用网页麦克风时允许权限）。

> 为什么推荐 Python 3.11：本项目的音频和模型依赖包含二进制扩展。统一版本能减少“包装上了，但解释器不兼容”的问题。不要把别人电脑上的 `.venv` 一起复制过去；虚拟环境是本机生成物。

## 2. 新用户首次启动

1. 获取源码后，解压到有写权限的目录，例如 `D:\Projects\ai107`。目录可以改名，也可以包含空格。
2. 双击项目根目录的 `start.bat`。
3. 首次运行会自动创建 `.venv`、安装两份依赖、下载 ASR 模型，并生成本机配置。所需时间取决于网络和电脑性能。
4. 终端显示访问地址后，用电脑打开 `http://127.0.0.1:8000`；手机访问可扫描终端二维码。
5. 在网页设置里填写模型接口地址、模型名和 API 密钥。密钥写在本机 `web/settings.json` 或 `.env`，这两类文件均被 Git 忽略，不应发给别人。

以后再次使用，只需双击 `start.bat`。

## 3. 启动前只做体检

体检不会下载模型，也不会启动 Web 服务：

```powershell
.\.venv\Scripts\python.exe .\scripts\start_best.py --doctor
```

输出中的 `[OK]` 表示已经就绪，`[--]` 表示首次启动仍需准备，不等于项目损坏。重点看第一行“仓库目录”：它应当等于你当前存放项目的位置，而不是开发者的用户目录。

## 4. 常见问题

### 双击后提示找不到 Python

安装 64 位 Python 3.11，勾选 `Add python.exe to PATH`，关闭旧终端后重新双击。用下面命令确认：

```powershell
py -3.11 --version
```

### 首次安装或模型下载失败

保持终端窗口不关，先看最后一条报错是网络、磁盘空间还是权限。项目默认使用清华 PyPI 镜像；模型来自 ModelScope。可重新双击，已完成的下载和环境会复用。

### 网页打不开或端口被占用

正常地址是 `http://127.0.0.1:8000`。若出现 `address already in use`，表示 8000 端口已有程序占用；先关闭上一次项目终端，再启动一次。

### 手机打不开或麦克风不可用

局域网模式要求手机和电脑连接同一 Wi-Fi，Windows 防火墙首次询问时允许“专用网络”。手机浏览器通常要求 HTTPS 才开放麦克风；启动器会尽量生成本机自签名证书，首次访问可能需要手动信任。公网隧道会把访问流量交给 Cloudflare，使用前应理解所在单位的数据合规要求。

### 密钥能不能打包发给别人

不能。`.env`、`web/.env`、`web/settings.json` 都是本机配置，其中可能含密钥。让每位使用者填写自己的密钥。

## 5. 开发者交付前检查

```powershell
# 路径与启动条件体检
.\.venv\Scripts\python.exe .\scripts\start_best.py --doctor

# 启动器专项测试
.\.venv\Scripts\python.exe -B -m unittest tests.test_portable_launcher -v

# 完整回归（时间更长）
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

发送源码时不要包含 `.env`、`.venv`、录音、数据库、证书和运行结果。开发者可运行 `scripts/windows/package_source.bat` 生成排除这些本机数据的源码压缩包；`scripts/windows/build_exe.bat` 用来制作免 Python 发行包，不是普通用户的首次启动入口。

根目录只保留普通用户入口 `start.bat`。开发者命令集中在 `scripts/windows/`，已弃用入口保存在 `scripts/legacy_launchers/`，历史交接和诊断快照保存在 `docs/history/`。

## 6. 这套一键启动的专业原理

- `%~dp0`：Windows 批处理参数展开，得到当前 `.bat` 自己所在的盘符和目录，所以项目搬家后仍能找到脚本。
- `Path(__file__).resolve()`：Python 根据当前源码文件反推仓库根目录，不依赖用户名或盘符。
- 虚拟环境（virtual environment）：把本项目依赖隔离在 `.venv`，避免与电脑上其他 Python 项目互相污染。
- 本地配置（local configuration）：密钥和机器相关路径留在被 Git 忽略的文件中；仓库只提供无密钥的 `.env.example`。

## 7. 当前证据边界

自动测试能证明批处理不再包含个人绝对路径，且 `--doctor` 能从非仓库工作目录反推出真实仓库位置。它不能证明另一台电脑的网络、声卡、浏览器权限、API 密钥和真实麦克风均可用；这些仍需在目标电脑按第 2 节做一次实际验收。
