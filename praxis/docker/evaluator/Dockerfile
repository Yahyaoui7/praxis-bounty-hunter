# We allow the python version to be overridden via build arg (default 3.11-slim)
ARG PYTHON_VERSION=3.11-slim
FROM python:${PYTHON_VERSION}

# Create a non-root user
RUN useradd -m -s /bin/bash student

# Install testing requirements
# For the POC, we just need pytest. We can add more later.
RUN pip install --no-cache-dir pytest

# Create mount points
RUN mkdir /workspace /tests && chown student:student /workspace /tests

# Drop privileges
USER student
WORKDIR /workspace

# Set a safe default entrypoint (though the service will override it with pytest)
ENTRYPOINT ["python3"]
