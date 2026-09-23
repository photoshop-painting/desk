# تصویر اجرا روی Hugging Face Spaces (Docker SDK) و Render.
# تفاوتش با Dockerfile سرور: درگاه ۷۸۶۰ (قرار HF)، بدون volume، و اجرای برنامه با boot.sh
# که از متغیرهای محیطی، دو حساب را می‌سازد و دروازه را روشن می‌کند.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STATION_PORT=7860

# کتابخانهٔ سیستمیِ Tk (یک آیتمِ بررسیِ سلامت، tkinter) در تصویر slim نیست؛
# بدون آن بررسی سلامت روی میزبان ابری ۷ از ۸ را نشان می‌دهد.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libtcl8.6 libtk8.6 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# کاربر غیر ریشه (قرار خود HF) + پوشه‌های نوشتنی برنامه
RUN useradd -m -u 1000 desk \
 && mkdir -p /app/data /app/config /app/export \
 && chmod +x /app/boot.sh \
 && chown -R desk:desk /app
USER desk

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '7860') + '/login', timeout=4)"

CMD ["bash", "boot.sh"]
