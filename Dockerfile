# The server's ISP DNS cannot reach Docker Hub directly. This proxy reference is
# pinned to Docker Hub's official linux/amd64 Python 3.12.13 manifest digest.
FROM docker.m.daocloud.io/library/python@sha256:72d3d75f2639ab82b34b29390ad3d6e0827c775befee94edda8e9976818f488d

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

WORKDIR /app

RUN sed -i \
        -e 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g' \
        -e 's|http://deb.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        fontconfig \
        libfreetype6 \
        fonts-noto-cjk \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system bot \
    && useradd --system --gid bot --home-dir /app bot \
    && mkdir -p /app/data/petpet /app/data/economy

# Use the faster mirror only for Python packages; keeping the base ENV above
# unchanged preserves the cached system-dependency layer on the deployment host.
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir \
        "nonebot2[fastapi]>=2.4.4,<3.0.0" \
        "nonebot-adapter-onebot>=2.4.6,<3.0.0" \
        "httpx>=0.27.0,<1.0.0" \
        "aiosqlite>=0.20.0,<1.0.0" \
        "python-dotenv>=1.0.0,<2.0.0" \
        "Pillow==10.4.0" \
        "playwright>=1.55.0,<2.0.0" \
        "yt-dlp>=2026.8.19" \
        "edge-tts>=7.2.7,<8.0.0" \
        "jieba>=0.42.1,<1.0.0" \
        "wordcloud>=1.9.4,<2.0.0" \
        "bbcode>=1.1.0,<2.0.0" \
        "fonttools>=4.0.0,<5.0.0" \
        "loguru>=0.6.0,<1.0.0" \
        "matplotlib>=3.0.0,<4.0.0" \
        "numpy>=1.20.0,<2.0.0" \
    && pip install --no-cache-dir --no-deps \
        nonebot-plugin-imageutils==0.1.17 \
        nonebot-plugin-petpet==0.3.21

RUN NODE_OPTIONS=--dns-result-order=ipv4first \
    PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.playwright.dev \
    python -m playwright install --with-deps chromium

# nonebot-plugin-imageutils imports cv2 at startup. Keep this pinned to the
# version used by the local test environment so pip does not backtrack through
# large OpenCV wheels during deployment.
RUN pip install --no-cache-dir --no-deps "opencv-python-headless==4.11.0.86"

COPY src ./src
COPY bot.py ./bot.py
COPY assets/petpet ./data/petpet

RUN pip install --no-cache-dir --no-deps . \
    && mkdir -p /app/data/media /app/data/wordcloud /app/work/media-downloads \
    && chown -R bot:bot /app /ms-playwright

USER bot
EXPOSE 8080

CMD ["python", "bot.py"]
