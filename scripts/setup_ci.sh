#!/bin/bash

# Setup script for CI/CD configuration
# This script helps you set up the complete CI/CD pipeline

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
cat << "EOF"
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║        TopShort Trading Bot - CI/CD Setup                 ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check Python version
echo -e "${BLUE}Checking Python version...${NC}"
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}✓ Python $PYTHON_VERSION found${NC}\n"

# Check if virtual environment exists
if [ -d ".venv" ]; then
    echo -e "${YELLOW}⚠ Virtual environment already exists${NC}"
    read -p "Do you want to recreate it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf .venv
        echo -e "${GREEN}✓ Old virtual environment removed${NC}\n"
    fi
fi

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo -e "${BLUE}Creating virtual environment...${NC}"
    python3 -m venv .venv
    echo -e "${GREEN}✓ Virtual environment created${NC}\n"
fi

# Activate virtual environment
echo -e "${BLUE}Activating virtual environment...${NC}"
source .venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}\n"

# Upgrade pip
echo -e "${BLUE}Upgrading pip...${NC}"
python -m pip install --upgrade pip --quiet
echo -e "${GREEN}✓ Pip upgraded${NC}\n"

# Install dependencies
echo -e "${BLUE}Installing production dependencies...${NC}"
pip install -r requirements.txt --quiet
echo -e "${GREEN}✓ Production dependencies installed${NC}\n"

echo -e "${BLUE}Installing test dependencies...${NC}"
pip install -r requirements-test.txt --quiet
echo -e "${GREEN}✓ Test dependencies installed${NC}\n"

# Install pre-commit
echo -e "${BLUE}Installing pre-commit...${NC}"
pip install pre-commit --quiet
echo -e "${GREEN}✓ Pre-commit installed${NC}\n"

# Setup pre-commit hooks
echo -e "${BLUE}Setting up pre-commit hooks...${NC}"
pre-commit install
echo -e "${GREEN}✓ Pre-commit hooks installed${NC}\n"

# Run pre-commit on all files
echo -e "${BLUE}Running pre-commit checks on all files (this may take a while)...${NC}"
pre-commit run --all-files || true
echo -e "${GREEN}✓ Pre-commit initial run completed${NC}\n"

# Test the setup
echo -e "${BLUE}Running quick test to verify setup...${NC}"
if pytest tests/ -q --tb=no > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Tests can run successfully${NC}\n"
else
    echo -e "${YELLOW}⚠ Some tests failed, but setup is complete${NC}\n"
fi

# Create .gitignore if it doesn't exist
if [ ! -f ".gitignore" ]; then
    echo -e "${BLUE}Creating .gitignore...${NC}"
    cat > .gitignore << 'GITIGNORE'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
.venv/
venv/
env/
ENV/

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/
coverage.xml
junit/

# MyPy
.mypy_cache/
.dmypy.json
dmypy.json

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Project specific
data/
logs/
*.log
*.db
*.sqlite
*.sqlite3

# Secrets
.env
.env.local
*.key
*.pem
credentials.json
config.local.yml
GITIGNORE
    echo -e "${GREEN}✓ .gitignore created${NC}\n"
fi

# Summary
echo -e "${GREEN}"
cat << "EOF"
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║              ✓ CI/CD Setup Complete!                      ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${BLUE}Next steps:${NC}\n"
echo -e "  1. Activate virtual environment:"
echo -e "     ${YELLOW}source .venv/bin/activate${NC}\n"

echo -e "  2. Run all CI checks locally:"
echo -e "     ${YELLOW}make ci${NC}"
echo -e "     ${YELLOW}# OR${NC}"
echo -e "     ${YELLOW}./scripts/run_ci_locally.sh${NC}\n"

echo -e "  3. Run specific checks:"
echo -e "     ${YELLOW}make test          ${NC}# Run tests"
echo -e "     ${YELLOW}make test-cov      ${NC}# Run tests with coverage"
echo -e "     ${YELLOW}make lint          ${NC}# Run linters"
echo -e "     ${YELLOW}make format        ${NC}# Format code"
echo -e "     ${YELLOW}make security      ${NC}# Security checks\n"

echo -e "  4. View coverage report:"
echo -e "     ${YELLOW}make coverage-report${NC}\n"

echo -e "  5. Push to GitHub:"
echo -e "     ${YELLOW}git add .${NC}"
echo -e "     ${YELLOW}git commit -m 'Add CI/CD configuration'${NC}"
echo -e "     ${YELLOW}git push${NC}\n"

echo -e "${BLUE}GitHub Actions will automatically:${NC}"
echo -e "  ✓ Run tests on Python 3.10, 3.11, and 3.12"
echo -e "  ✓ Check code quality and formatting"
echo -e "  ✓ Generate coverage reports"
echo -e "  ✓ Run security scans"
echo -e "  ✓ Block PRs if checks fail\n"

echo -e "${BLUE}Pre-commit hooks will automatically run before each commit:${NC}"
echo -e "  ✓ Format code with Black"
echo -e "  ✓ Sort imports with isort"
echo -e "  ✓ Lint with Flake8"
echo -e "  ✓ Type check with MyPy"
echo -e "  ✓ Security scan with Bandit"
echo -e "  ✓ Run tests with coverage check\n"

echo -e "${GREEN}Happy coding! 🚀${NC}\n"
