# Lambda container image (AWS base image ships the Runtime Interface Emulator).
# The handler is chosen per service via `command` in compose.yaml.
# Dependencies are installed from uv.lock (runtime group only), so the image matches CI.
FROM public.ecr.aws/lambda/python:3.12

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/requirements.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt
COPY src/invoice_extraction ${LAMBDA_TASK_ROOT}/invoice_extraction

CMD ["invoice_extraction.entrypoints.api_handler.handler"]
