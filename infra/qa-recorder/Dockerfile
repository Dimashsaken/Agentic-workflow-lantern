# Build-time tools only. Runtime CA trust is confined to an ephemeral container home.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libnss3-tools \
    && dpkg-query -W > /opt/lantern/recorder-packages.txt \
    && rm -rf /var/lib/apt/lists/*
COPY tools/azure-runner/qa_recorder_worker.py /opt/lantern/qa_recorder_worker.py
COPY tools/azure-runner/qa_transport.py /opt/lantern/qa_transport.py
USER 1000:1000
ENTRYPOINT ["/opt/lantern/venv/bin/python", "/opt/lantern/qa_recorder_worker.py"]
