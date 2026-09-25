FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first for layer caching
COPY pyproject.toml .

# Install dependencies
RUN uv pip install --system \
    langgraph==0.2.55 langchain-openai==0.2.5 langchain==0.3.7 \
    fastapi==0.115.4 "uvicorn[standard]==0.32.1" \
    pydantic==2.9.2 pydantic-settings==2.6.1 \
    python-jose cryptography asyncpg==0.30.0 \
    qdrant-client==1.12.0 openai pdfplumber==0.11.4 \
    pyyaml==6.0.2 tenacity==9.0.0 structlog==24.4.0 \
    python-dotenv==1.0.1 httpx==0.27.2 supabase==2.9.1

# Copy source
COPY . .

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]