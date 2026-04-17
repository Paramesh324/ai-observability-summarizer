FROM registry.access.redhat.com/ubi9/python-311:latest

WORKDIR /app

USER root

# Install system dependencies for WeasyPrint and pandas build on s390x
RUN dnf install -y --allowerasing \
    fontconfig \
    harfbuzz \
    pango \
    cairo \
    libxml2 \
    libxslt \
    freetype \
    openjpeg2 \
    python3-devel \
    gcc \
    gcc-c++ \
    libffi-devel \
    dejavu-sans-fonts \
    gcc-gfortran \
    openblas-devel \
    lapack \
    openssl-devel \
    curl \
    && dnf clean all

USER 1001

# Use system OpenSSL instead of BoringSSL for s390x compatibility
ENV GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1

# Copy and install Python dependencies via pip using requirements.txt
COPY mcp_server/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/requirements.txt

# Copy source code (mcp_server/data/ includes the base metrics catalog)
COPY core /app/core
COPY common /app/common
COPY chatbots /app/chatbots
COPY mcp_server /app/mcp_server

ENV PYTHONPATH=/app
EXPOSE 8085

CMD ["python", "-m", "mcp_server.main"]


