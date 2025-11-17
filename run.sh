#!/bin/bash

# TopShort Trading Bot Runner

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}Virtual environment created${NC}"
fi

# Activate virtual environment
echo -e "${GREEN}Activating virtual environment...${NC}"
source venv/bin/activate

# Check if dependencies are installed
if [ ! -f "venv/lib/python3.*/site-packages/ccxt/__init__.py" ]; then
    echo -e "${YELLOW}Dependencies not found. Installing...${NC}"
    pip install -r requirements.txt
    echo -e "${GREEN}Dependencies installed${NC}"
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo -e "${YELLOW}Please copy .env.example to .env and configure it:${NC}"
    echo "cp .env.example .env"
    exit 1
fi

# Run the bot
echo -e "${GREEN}Starting TopShort Trading Bot...${NC}"
echo "Press Ctrl+C to stop"
echo ""

python -m src.main
