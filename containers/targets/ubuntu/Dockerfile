# Hermes Target Container - Ubuntu 22.04
# This container serves as the sandbox environment for attacker sessions.
# Network is disabled (network_mode=none) at runtime for isolation.

FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install common tools that attackers expect to find
RUN apt-get update && apt-get install -y \
    # Core utilities
    bash \
    coreutils \
    procps \
    file \
    less \
    # Text editors
    vim \
    nano \
    # Network tools (will fail due to network isolation, but realistic)
    curl \
    wget \
    netcat-traditional \
    net-tools \
    iputils-ping \
    dnsutils \
    # Programming languages
    python3 \
    python3-pip \
    # SSH client (for attacker testing)
    openssh-client \
    # Version control
    git \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Create fake "interesting" files for attackers to discover
RUN mkdir -p /var/log /etc/config /home/admin /root/.ssh

# Fake database credentials (honeypot)
RUN echo "# Application Configuration" > /etc/config/app.env && \
    echo "DB_HOST=internal-db-01.company.local" >> /etc/config/app.env && \
    echo "DB_USER=app_user" >> /etc/config/app.env && \
    echo "DB_PASSWORD=not_a_real_password_123" >> /etc/config/app.env && \
    echo "API_KEY=sk-fake-key-do-not-use" >> /etc/config/app.env

# Fake access log with internal URLs
RUN echo "192.168.1.10 - - [$(date +'%d/%b/%Y:%H:%M:%S %z')] \"GET /admin HTTP/1.1\" 200 1234" > /var/log/access.log && \
    echo "192.168.1.15 - admin - [$(date +'%d/%b/%Y:%H:%M:%S %z')] \"POST /api/users HTTP/1.1\" 201 512" >> /var/log/access.log && \
    echo "Internal admin panel: http://admin.company.internal" >> /var/log/access.log

# Fake bash history (makes it look like a real server)
RUN echo "# Bash history from previous admin session" > /home/admin/.bash_history && \
    echo "ls -la" >> /home/admin/.bash_history && \
    echo "cd /var/www/html" >> /home/admin/.bash_history && \
    echo "vim config.php" >> /home/admin/.bash_history && \
    echo "systemctl restart nginx" >> /home/admin/.bash_history && \
    echo "tail -f /var/log/nginx/access.log" >> /home/admin/.bash_history

# Empty SSH config (tempting for attackers)
RUN touch /root/.ssh/config && chmod 600 /root/.ssh/config

# Set up a convincing environment
ENV HOSTNAME=prod-web-01
ENV USER=root
ENV HOME=/root

# Working directory
WORKDIR /root

# Default command (will be overridden by docker exec in actual use)
CMD ["/bin/bash"]
