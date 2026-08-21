# The server's ISP DNS cannot reach Docker Hub directly. This proxy reference is
# pinned to Docker Hub's official linux/amd64 Python 3.12.13 manifest digest.
FROM docker.m.daocloud.io/library/python@sha256:72d3d75f2639ab82b34b29390ad3d6e0827c775befee94edda8e9976818f488d

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
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
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system bot \
    && useradd --system --gid bot --home-dir /app bot \
    && mkdir -p /app/data/petpet

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir \
        "nonebot2[fastapi]>=2.4.4,<3.0.0" \
        "nonebot-adapter-onebot>=2.4.6,<3.0.0" \
        "httpx>=0.27.0,<1.0.0" \
        "python-dotenv>=1.0.0,<2.0.0" \
        "Pillow==10.4.0" \
        "bbcode>=1.1.0,<2.0.0" \
        "fonttools>=4.0.0,<5.0.0" \
        "loguru>=0.6.0,<1.0.0" \
        "matplotlib>=3.0.0,<4.0.0" \
        "numpy>=1.20.0,<2.0.0" \
        "opencv-python-headless>=4.0.0,<5.0.0" \
    && pip install --no-cache-dir --no-deps \
        nonebot-plugin-imageutils==0.1.17 \
        nonebot-plugin-petpet==0.3.21

COPY src ./src
COPY bot.py ./bot.py
COPY assets/petpet ./data/petpet

RUN pip install --no-cache-dir --no-deps . \
    && chown -R bot:bot /app

USER bot
EXPOSE 8080

CMD ["python", "bot.py"]

