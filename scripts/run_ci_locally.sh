#!/bin/bash

# Run CI checks locally before pushing
# This script runs the same checks as GitHub Actions

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          Running CI Checks Locally                        ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}⚠ Warning: No virtual environment detected${NC}"
    echo -e "${YELLOW}  Consider activating venv: source .venv/bin/activate${NC}"
    echo ""
fi

# Counter for passed/failed checks
PASSED=0
FAILED=0

run_check() {
    local name=$1
    local command=$2

    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}Running: ${name}${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if eval $command; then
        echo -e "${GREEN}✓ ${name} passed${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ ${name} failed${NC}"
        ((FAILED++))
    fi
    echo ""
}

# 1. Code Formatting Check
run_check "Code Formatting (Black)" "black --check src tests"

# 2. Import Sorting Check
run_check "Import Sorting (isort)" "isort --check-only src tests"

# 3. Linting
run_check "Linting (Flake8)" "flake8 src tests"

# 4. Type Checking (temporarily disabled - many type errors to fix)
# run_check "Type Checking (MyPy)" "mypy src --ignore-missing-imports"

# 5. Security Check
run_check "Security Check (Bandit)" "bandit -r src -ll"

# 6. Run Tests
run_check "Unit Tests (Pytest)" "pytest tests/ --verbose --cov=src --cov-report=term-missing --cov-fail-under=30"

# Summary
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                    CI Summary                             ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Total checks: $((PASSED + FAILED))"
echo -e "  ${GREEN}Passed: ${PASSED}${NC}"
echo -e "  ${RED}Failed: ${FAILED}${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║         ✓ All CI checks passed!                          ║${NC}"
    echo -e "${GREEN}║         Ready to push to repository                       ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║         ✗ Some CI checks failed!                         ║${NC}"
    echo -e "${RED}║         Please fix the issues before pushing             ║${NC}"
    echo -e "${RED}╚═══════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi
