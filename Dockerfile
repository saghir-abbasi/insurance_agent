FROM python:3.12

LABEL maintainer="insurance_agent"

WORKDIR /workspace

RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Use token to clone private repo
RUN --mount=type=secret,id=GITHUB_TOKEN,mode=0444,required=true \
 git clone https://$(cat /run/secrets/GITHUB_TOKEN)@github.com/saghir-abbasi/insurance_agent.git /workspace

RUN pip install uv
RUN uv sync --frozen

RUN useradd --create-home --home-dir /home/appuser appuser \
    && chown -R appuser:appuser /workspace

USER appuser

# Build the local Chroma vector store from data/final_expense_faq.md at
# image-build time. `uv run ingest` also downloads the fastembed model
# (~110MB), so the first runtime call is fast.
RUN uv run ingest

EXPOSE 7860

# The browser call page (/app) opens its WebSocket on whatever host served it,
# so no DOMAIN_URL override is needed for the port.
CMD ["uv", "run", "uvicorn", "src.insurance_agent.main:app", "--host", "0.0.0.0", "--port", "7860"]
