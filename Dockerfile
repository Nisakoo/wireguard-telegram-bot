FROM python:3.12-slim-bookworm AS base

# Копируем uv из официального образа uv
FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.4.9 /uv /bin/uv

# Устанавливаем переменные окружения для uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app

# Копируем только lock-файлы для установки зависимостей
COPY uv.lock pyproject.toml /app/

# Используем кэш uv для ускорения установки зависимостей
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Копируем остальной исходный код
COPY . /app

# Снова синхронизируем зависимости с проектом (без dev-зависимостей)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Финальный образ
FROM base

RUN apt-get -y update \
    && apt-get -y upgrade \
    && apt-get -y install libcairo2

WORKDIR /app

# Копируем из builder только необходимые файлы
COPY --from=builder /app /app
COPY --from=builder /bin/uv /bin/uv

# Добавляем виртуальное окружение uv в PATH
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uv", "run", "main.py"]
