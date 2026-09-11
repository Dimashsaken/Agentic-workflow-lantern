# Disabled gateway candidate; pinned official Python 3.12.14 slim-trixie, Linux amd64.
# No browser, Node/npm, product checkout or controller SDK is included.
FROM python:3.12-slim@sha256:2fe5997d249a808b8eeea52c58a1dbffbba28754dc11699ef5c029f2d818ce79
ENV HOME=/tmp
USER root
RUN python3.12 -m venv /opt/gateway
COPY infra/qa-gateway/build-tools.lock infra/qa-gateway/requirements.lock infra/qa-gateway/upstream.lock infra/qa-gateway/vendor_wheel.py /opt/gateway/
RUN --mount=type=cache,target=/root/.cache/pip \
    export PIP_CACHE_DIR=/root/.cache/pip && python3.12 -m pip install --require-hashes --only-binary=:all: -r /opt/gateway/build-tools.lock \
    && /opt/gateway/bin/pip install --require-hashes --only-binary=:all: -r /opt/gateway/build-tools.lock \
    && /opt/gateway/bin/pip download --timeout 120 --retries 3 --require-hashes --only-binary=:all: --no-deps \
      -r /opt/gateway/upstream.lock -d /opt/gateway/upstream \
    && /opt/gateway/bin/python /opt/gateway/vendor_wheel.py \
      /opt/gateway/upstream/mitmproxy-12.2.3-py3-none-any.whl \
      /opt/gateway/vendor/mitmproxy-12.2.3+lantern1-py3-none-any.whl > /opt/gateway/vendor-provenance.json \
    && /opt/gateway/bin/pip install --timeout 120 --retries 3 --require-hashes --only-binary=:all: \
      --find-links /opt/gateway/vendor -r /opt/gateway/requirements.lock \
    && /opt/gateway/bin/pip check \
    && /opt/gateway/bin/pip uninstall --yes pip \
    && python3.12 -m pip uninstall --yes pip \
    && python3.12 -c "import shutil; shutil.rmtree('/usr/local/lib/python3.12/ensurepip')"
COPY infra/qa-gateway/policy.py infra/qa-gateway/entrypoint.py /opt/gateway/
COPY tools/azure-runner/qa_transport.py /opt/gateway/qa_transport.py
USER 1000:1000
ENTRYPOINT ["/opt/gateway/bin/python", "/opt/gateway/entrypoint.py"]
