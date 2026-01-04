# استفاده از پایتون نسخه 3.10 slim برای کاهش حجم ایمیج
FROM python:3.10-slim

# تنظیم متغیرهای محیطی پایتون
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# تنظیم دایرکتوری کاری
WORKDIR /app

# نصب پکیج‌های سیستمی مورد نیاز
# netcat برای entrypoint.sh لازم است تا منتظر دیتابیس بماند
# gcc و libpq-dev برای بیلد کردن پکیج‌های دیتابیس پایتون لازم هستند
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    netcat-openbsd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# کپی کردن فایل نیازمندی‌ها و نصب آن‌ها
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# کپی کردن کل پروژه به داخل کانتینر
COPY . /app/

# ایجاد پوشه‌های استاتیک و مدیا
RUN mkdir -p /app/staticfiles /app/media

# تنظیم پرمیشن اجرایی برای اسکریپت entrypoint
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# نقطه ورود کانتینر
ENTRYPOINT ["/app/entrypoint.sh"]