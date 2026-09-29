# ── 构建阶段：安装 ASR 模型依赖 ──
FROM python:3.11-slim AS base

# 系统依赖（sounddevice/soundfile 需要的音频库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用 Docker 层缓存）
COPY requirements.txt ./requirements.txt
COPY web/requirements.txt ./web/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r web/requirements.txt

# 复制源码
COPY . .

# 设置环境
ENV PYTHONPATH=/app/web
ENV PYTHONUNBUFFERED=1

# 数据库和上传目录（容器运行时挂载 volume 持久化）
RUN mkdir -p /app/web/data /app/web/uploads /app/logs
VOLUME ["/app/web/data", "/app/web/uploads", "/app/logs"]

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

# 启动（容器内用 HTTP，前面放反向代理处理 TLS）
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "web"]
