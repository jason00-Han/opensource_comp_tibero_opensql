FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir ./services/api ./cli
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
