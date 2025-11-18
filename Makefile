.PHONY: help install install-dev test test-cov test-watch lint format type-check security clean ci pre-commit

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

install: ## Install production dependencies
	@echo "$(BLUE)Installing production dependencies...$(NC)"
	pip install -r requirements.txt

install-dev: ## Install development dependencies
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	pip install -r requirements.txt
	pip install -r requirements-test.txt
	pip install pre-commit
	pre-commit install

test: ## Run tests
	@echo "$(BLUE)Running tests...$(NC)"
	pytest tests/ -v

test-cov: ## Run tests with coverage
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	pytest tests/ \
		--verbose \
		--cov=src \
		--cov-report=term-missing \
		--cov-report=html \
		--cov-report=xml \
		--cov-fail-under=80

test-watch: ## Run tests in watch mode
	@echo "$(BLUE)Running tests in watch mode...$(NC)"
	pytest-watch tests/ -v

test-quick: ## Run tests without coverage (fast)
	@echo "$(BLUE)Running quick tests...$(NC)"
	pytest tests/ -v -x --ff

test-parallel: ## Run tests in parallel
	@echo "$(BLUE)Running tests in parallel...$(NC)"
	pytest tests/ -n auto -v

lint: ## Run all linters
	@echo "$(BLUE)Running linters...$(NC)"
	@echo "$(YELLOW)Flake8...$(NC)"
	flake8 src tests --max-line-length=127 --extend-ignore=E203,W503
	@echo "$(YELLOW)Pylint...$(NC)"
	pylint src --disable=C,R,W --errors-only || true

format: ## Format code with black and isort
	@echo "$(BLUE)Formatting code...$(NC)"
	black src tests
	isort src tests --profile=black

format-check: ## Check code formatting without modifying
	@echo "$(BLUE)Checking code formatting...$(NC)"
	black --check --diff src tests
	isort --check-only --diff src tests

type-check: ## Run type checking with mypy
	@echo "$(BLUE)Running type checks...$(NC)"
	mypy src --ignore-missing-imports

security: ## Run security checks
	@echo "$(BLUE)Running security checks...$(NC)"
	@echo "$(YELLOW)Bandit...$(NC)"
	bandit -r src -ll
	@echo "$(YELLOW)Safety...$(NC)"
	safety check || true

complexity: ## Check code complexity
	@echo "$(BLUE)Checking code complexity...$(NC)"
	radon cc src -a
	radon mi src

clean: ## Clean up generated files
	@echo "$(BLUE)Cleaning up...$(NC)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .mypy_cache
	rm -rf coverage.xml
	rm -rf junit
	rm -rf dist
	rm -rf build

ci: clean install-dev lint type-check security test-cov ## Run all CI checks locally
	@echo "$(GREEN)✓ All CI checks passed!$(NC)"

pre-commit: ## Run pre-commit hooks on all files
	@echo "$(BLUE)Running pre-commit hooks...$(NC)"
	pre-commit run --all-files

coverage-report: ## Generate and open HTML coverage report
	@echo "$(BLUE)Generating coverage report...$(NC)"
	pytest tests/ --cov=src --cov-report=html
	@echo "$(GREEN)Opening coverage report...$(NC)"
	open htmlcov/index.html || xdg-open htmlcov/index.html || echo "Please open htmlcov/index.html manually"

update-deps: ## Update all dependencies to latest versions
	@echo "$(BLUE)Updating dependencies...$(NC)"
	pip list --outdated
	pip install --upgrade pip
	pip install -U -r requirements.txt
	pip install -U -r requirements-test.txt

venv: ## Create virtual environment
	@echo "$(BLUE)Creating virtual environment...$(NC)"
	python3 -m venv .venv
	@echo "$(GREEN)Virtual environment created. Activate it with:$(NC)"
	@echo "  source .venv/bin/activate"

docker-test: ## Run tests in Docker container
	@echo "$(BLUE)Running tests in Docker...$(NC)"
	docker build -t topshort-test -f Dockerfile.test .
	docker run --rm topshort-test

badges: ## Generate README badges
	@echo "$(BLUE)Generate these badges for your README:$(NC)"
	@echo ""
	@echo "Tests:"
	@echo "[![Tests](https://github.com/$(shell git config --get remote.origin.url | sed 's/.*github.com[:/]\(.*\)\.git/\1/')/actions/workflows/tests.yml/badge.svg)](https://github.com/$(shell git config --get remote.origin.url | sed 's/.*github.com[:/]\(.*\)\.git/\1/')/actions/workflows/tests.yml)"
	@echo ""
	@echo "Coverage:"
	@echo "[![codecov](https://codecov.io/gh/$(shell git config --get remote.origin.url | sed 's/.*github.com[:/]\(.*\)\.git/\1/')/branch/main/graph/badge.svg)](https://codecov.io/gh/$(shell git config --get remote.origin.url | sed 's/.*github.com[:/]\(.*\)\.git/\1/'))"

status: ## Show project status
	@echo "$(BLUE)Project Status:$(NC)"
	@echo ""
	@echo "$(YELLOW)Git Status:$(NC)"
	@git status --short
	@echo ""
	@echo "$(YELLOW)Python Version:$(NC)"
	@python --version
	@echo ""
	@echo "$(YELLOW)Installed Packages:$(NC)"
	@pip list | grep -E "(pytest|coverage|flake8|black|mypy)" || echo "Test packages not installed"
	@echo ""
	@echo "$(YELLOW)Test Files:$(NC)"
	@find tests -name "test_*.py" -type f | wc -l | xargs -I {} echo "{} test files found"
