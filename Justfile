# Automatically load .env file if it exists
set dotenv-load := true

# Display available commands with descriptions
default:
    @just --list --unsorted

## --- Setup & Configuration ---

# Install dependencies with uv and setup pre-commit hooks
env-setup:
    uv self update
    uv sync --all-groups --all-extras
    uvx detect-secrets scan > .secrets.baseline
    uv run pre-commit install --install-hooks -t pre-commit -t commit-msg -t pre-push
    @echo "success: Environment setup complete. Pre-commit hooks installed."

## --- Development & Maintenance ---

# Upgrade project lockfile dependencies
lock:
    uv lock --upgrade

# Update git pre-commit hook versions to latest
hooks-update:
    uv run pre-commit autoupdate
    sed -i 's|rev: v1$|rev: v1.51.1|' .pre-commit-config.yaml
    @echo "warning: Check https://github.com/crate-ci/typos/releases for the latest typos version — v1.51.1 was hardcoded above and may be stale"

# Run pre-commit checks across all staged/unstaged files
hooks-run:
    uv run pre-commit run --all-files

## --- Testing & Quality ---

# Run pytest test suite with coverage report
test:
    uv run pytest tests/ -v

## --- Documentation ---

# Serve the documentation site locally with live reload
docs-serve mkdocs_port="5050":
    uv run mkdocs serve -a 127.0.0.1:{{mkdocs_port}} --strict

# Publish the documentation to GitHub Pages
docs-deploy:
    uv run mkdocs gh-deploy -csm "Deploy the latest documentation" -b gh-pages --shell --force

## --- Application Execution ---

# Run the FastAPI application with uvicorn for development
serve:
    uv run uvicorn forecasting_analytics.api.app:app --reload

## --- Cleanup ---

# Clean everything; cache, generated files and logs
clean-all: clean-cache clean-logs

# Clean temporary Python, pytest, and build cache directories
clean-cache:
    find . -type d -regex ".*\(__pycache__\|\.pytest_cache\|\.ruff_cache\|\.mypy_cache\|\.pyright_cache\)" -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
    rm -rf .coverage htmlcov/ site/ dist/ build/ *.egg-info
    rm -f coverage.xml
    @echo "success: Cleaned all the cache"

# Clean the generated log files
clean-logs:
    rm -f logs/*.log
    @echo "success: Cleaned log files in the logs directory."
