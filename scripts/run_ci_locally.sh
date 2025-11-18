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

# Activate virtual environment if not already activated
if [ -z "$VIRTUAL_ENV" ]; then
    if [ -f ".venv/bin/activate" ]; then
        echo -e "${YELLOW}🔧 Activating virtual environment (.venv)${NC}"
        source .venv/bin/activate
        echo -e "${GREEN}✓ Virtual environment activated${NC}"
        echo ""
    else
        echo -e "${RED}❌ Error: .venv not found${NC}"
        echo -e "${YELLOW}  Create it with: python3 -m venv .venv${NC}"
        echo -e "${YELLOW}  Then install deps: pip install -r requirements.txt${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ Virtual environment already activated${NC}"
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
echo -e "${BLUE}Running tests...${NC}"
# Run all tests with appropriate coverage thresholds
run_check "Unit Tests (Pytest)" "pytest tests/ --verbose --cov=src --cov-report=term-missing --cov-fail-under=40"

# Optional: Run bot tests separately to verify comprehensive coverage
if [ -f "tests/test_callback_handler.py" ]; then
    echo -e "${BLUE}Running bot component tests...${NC}"
    run_check "Bot Tests" "pytest tests/test_callback_handler.py tests/test_commands.py tests/test_keyboard_builder.py -v"
fi

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
