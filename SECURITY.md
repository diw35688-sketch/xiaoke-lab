# 安全策略 / Security Policy

## 报告安全漏洞

如果你发现了安全漏洞，请**不要**在公开 Issue 中提交。

请发送邮件至项目维护者，或通过 [GitHub Security Advisory](https://github.com/diw35688-sketch/xiaoke-lab/security/advisories/new) 提交。

## 安全设计

### API Key 保护
- LLM API Key 仅存储在本地 `settings.json`（已加入 `.gitignore`）
- 数据库中不存储明文密钥
- 会话令牌只存 SHA-256 摘要，不存明文

### 口令散列
- PBKDF2-HMAC-SHA256，600,000 轮（OWASP 2023 推荐值）
- 使用 Python 标准库实现，无外部二进制依赖

### 网络安全
- 本地服务默认使用自签名 HTTPS 证书
- 内部接口（`/internal/*`）通过共享密钥保护，防止公网隧道越权
- 会话认证中间件拦截未登录请求

### 已知限制
- 本项目设计为**实验室本机部署**，不适合直接暴露到公网
- SQLite 是单文件数据库，不支持多实例水平扩展
- `domain.py` 使用进程级全局状态，不支持多进程并发实验
