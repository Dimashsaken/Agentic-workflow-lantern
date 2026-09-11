FROM python:3.12-slim@sha256:2fe5997d249a808b8eeea52c58a1dbffbba28754dc11699ef5c029f2d818ce79
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && apt-get -o Acquire::https::Timeout=20 -o Acquire::Retries=1 update && apt-get -o Acquire::https::Timeout=20 -o Acquire::Retries=1 install -y --no-install-recommends iproute2 nftables procps && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["python3"]
