# 贡献指南 / Contributing

感谢你对小科实验助手的兴趣！以下是参与贡献的方式。

## 开发环境

```bash
# 1. 克隆仓库
git clone https://github.com/diw35688-sketch/xiaoke-lab.git
cd xiaoke-lab

# 2. 创建虚拟环境并安装依赖（Windows）
#    方式 A：双击 start.bat（自动创建 .venv 并安装）
#    方式 B：手动安装
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r web/requirements.txt
pip install pytest

# 3. 配置 LLM API Key
#    复制 .env.example 为 .env，填入你的 API Key
copy .env.example .env
#    或启动后在网页端「设置」页面填写

# 4. 运行测试
python -m pytest tests/ -q

# 5. 启动服务
python scripts/start_best.py
```

## 代码规范

- **Python**: 遵循 PEP 8，新增函数尽量加类型标注
- **前端**: 原生 JS，不引入构建工具
- **测试**: 新功能请附带测试；运行 `python -m pytest tests/ -q` 确认全绿
- **日志**: 使用 `logging` 模块，不要用 `print()`
- **提交信息**: 中文或英文均可，格式参考 `feat: / fix: / docs: / refactor: / test:`

## 项目结构

```
src/          ASR、LLM、核心数据结构
web/          FastAPI 服务端 + 前端
  agent/      Agent 工具循环（核心调度）
  api/        FastAPI 路由
  database/   SQLite 持久化
  frontend/   原生 JS 前端
tests/        测试（1500+ 用例）
scripts/      启动脚本、评测工具
data/         协议库、试剂安全库（静态数据）
```

## 报告 Bug

请在 [Issues](https://github.com/diw35688-sketch/xiaoke-lab/issues) 中提交：
- 复现步骤
- 期望行为 vs 实际行为
- 操作系统和 Python 版本

## 许可

贡献的代码遵循项目的 [Apache License 2.0](LICENSE)。
