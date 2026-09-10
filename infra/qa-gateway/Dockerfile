# Build separately; BASE_IMAGE must be a reviewed immutable sandbox image ID.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
USER root
RUN python3.12 -m venv /opt/gateway
COPY infra/qa-gateway/requirements.lock /opt/gateway/requirements.lock
RUN --mount=type=cache,target=/root/.cache/pip PIP_CACHE_DIR=/root/.cache/pip /opt/gateway/bin/pip install --timeout 120 --retries 3 --require-hashes --only-binary=:all: -r /opt/gateway/requirements.lock
COPY infra/qa-gateway/policy.py infra/qa-gateway/entrypoint.py /opt/gateway/
COPY tools/azure-runner/qa_transport.py /opt/gateway/qa_transport.py
USER 1000:1000
ENTRYPOINT ["/opt/gateway/bin/python", "/opt/gateway/entrypoint.py"]
