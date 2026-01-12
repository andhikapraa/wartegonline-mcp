FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy project files
COPY pyproject.toml .
COPY README.md .
COPY warlon_client.py .
COPY warlon_mcp.py .

# Install dependencies
RUN uv pip install --system -e .

# Set environment variable for HTTP mode
ENV MCP_HTTP_MODE=1

# Expose port (Smithery will set PORT env var)
EXPOSE 8081

# Run the server in HTTP mode
CMD ["python", "warlon_mcp.py", "--http"]
