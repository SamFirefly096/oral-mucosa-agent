FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录挂载点
RUN mkdir -p /app/data /app/outputs /app/cases_photos

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/cases', data=b'')" || exit 1

EXPOSE 5000

# 默认使用 gunicorn 启动
CMD ["gunicorn", "wsgi:app", "-w", "4", "-b", "0.0.0.0:5000", "--access-logfile", "-", "--error-logfile", "-"]
