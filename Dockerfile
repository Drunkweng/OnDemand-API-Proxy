FROM python:3.10-slim
# 安装pip依赖
WORKDIR /workspace
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 复制你的源码
COPY . .
# Space 必须监听 0.0.0.0:7860 或 3000，建议 7860！
ENV PORT=7860
EXPOSE 7860
CMD ["python", "openai_ondemand_adapter.py"]