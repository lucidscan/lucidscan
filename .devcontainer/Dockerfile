FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    unzip \
    gnupg \
    lsb-release \
    openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# Install Trivy
RUN curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

# Install Ruff
RUN pip install --no-cache-dir ruff

# Install Biome
RUN curl -fsSL https://biomejs.dev/install.sh | sh && \
    mv /root/.biome/bin/biome /usr/local/bin/biome || true

# Install Checkov
RUN pip install --no-cache-dir checkov

# Set working directory
WORKDIR /workspaces/lucidshark

# Switch to non-root user (vscode user is created by the base devcontainer image)
USER vscode

# Default command
CMD ["bash"]
