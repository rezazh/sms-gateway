FROM docker.arvancloud.ir/python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# نصب dependencies سیستمی
RUN apt-get update && apt-get install -y \
    postgresql-client \
    netcat-traditional \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# کپی requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# کپی کد پروژه
COPY . .

# ساخت پوشه logs
RUN mkdir -p logs

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]