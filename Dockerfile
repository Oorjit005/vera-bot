FROM python:3.12-slim
ENV PYTHONUTF8=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
# $PORT is respected when set (Render and most PaaS hosts inject it); falls
# back to 8080 for Hugging Face Spaces / local Docker runs.
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --timeout-keep-alive 75"]
