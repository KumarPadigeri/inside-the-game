# Backend API for Inside the Game (FastAPI + Microsoft Agent Framework).
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml ./
RUN mkdir inside_the_game && touch inside_the_game/__init__.py \
    && pip install --no-cache-dir . \
    && pip uninstall -y inside-the-game

COPY inside_the_game ./inside_the_game

# Run as a non-root user.
RUN useradd --create-home app
USER app

EXPOSE 8000
CMD ["uvicorn", "inside_the_game.api:app", "--host", "0.0.0.0", "--port", "8000"]
