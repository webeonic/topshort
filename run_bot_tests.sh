#!/bin/bash
# Script to run all Telegram bot tests with coverage

set -e  # Exit on error

echo "🤖 Running TopShort Telegram Bot Test Suite"
echo "==========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}❌ pytest is not installed${NC}"
    echo "Install it with: pip install pytest pytest-asyncio pytest-cov"
    exit 1
fi

# Set PYTHONPATH
export PYTHONPATH="${PWD}:${PYTHONPATH}"
echo -e "${BLUE}📂 PYTHONPATH set to: ${PWD}${NC}"
echo ""

# Run tests based on argument
case "${1:-all}" in
    "all")
        echo -e "${YELLOW}🧪 Running ALL bot tests...${NC}"
        pytest tests/test_telegram_bot.py \
               tests/test_callback_handler.py \
               tests/test_commands.py \
               tests/test_keyboard_builder.py \
               --cov=src/bot \
               --cov-report=html \
               --cov-report=term-missing \
               --cov-fail-under=90 \
               -v
        ;;

    "fast")
        echo -e "${YELLOW}⚡ Running fast tests (no coverage)...${NC}"
        pytest tests/test_telegram_bot.py \
               tests/test_callback_handler.py \
               tests/test_commands.py \
               tests/test_keyboard_builder.py \
               --no-cov \
               -v
        ;;

    "bot")
        echo -e "${YELLOW}🤖 Running telegram_bot tests...${NC}"
        pytest tests/test_telegram_bot.py -v --cov=src/bot/telegram_bot.py --cov-report=term
        ;;

    "commands")
        echo -e "${YELLOW}💬 Running commands tests...${NC}"
        pytest tests/test_commands.py -v --cov=src/bot/commands.py --cov-report=term
        ;;

    "callback")
        echo -e "${YELLOW}🔘 Running callback handler tests...${NC}"
        pytest tests/test_callback_handler.py -v --cov=src/bot/callback_handler.py --cov-report=term
        ;;

    "keyboard")
        echo -e "${YELLOW}⌨️  Running keyboard builder tests...${NC}"
        pytest tests/test_keyboard_builder.py -v --cov=src/bot/keyboard_builder.py --cov-report=term
        ;;

    "coverage")
        echo -e "${YELLOW}📊 Generating coverage report...${NC}"
        pytest tests/test_telegram_bot.py \
               tests/test_callback_handler.py \
               tests/test_commands.py \
               tests/test_keyboard_builder.py \
               --cov=src/bot \
               --cov-report=html \
               --cov-report=term-missing

        echo ""
        echo -e "${GREEN}✅ Coverage report generated${NC}"
        echo -e "${BLUE}📄 Open htmlcov/index.html to view detailed report${NC}"
        ;;

    "watch")
        echo -e "${YELLOW}👁️  Running tests in watch mode...${NC}"
        pytest-watch tests/test_telegram_bot.py \
                      tests/test_callback_handler.py \
                      tests/test_commands.py \
                      tests/test_keyboard_builder.py \
                      -- -v
        ;;

    "failed")
        echo -e "${YELLOW}🔁 Re-running last failed tests...${NC}"
        pytest --lf -v
        ;;

    *)
        echo -e "${RED}❌ Unknown option: ${1}${NC}"
        echo ""
        echo "Usage: ./run_bot_tests.sh [option]"
        echo ""
        echo "Options:"
        echo "  all       - Run all bot tests with coverage (default)"
        echo "  fast      - Run all tests without coverage"
        echo "  bot       - Run only telegram_bot tests"
        echo "  commands  - Run only commands tests"
        echo "  callback  - Run only callback handler tests"
        echo "  keyboard  - Run only keyboard builder tests"
        echo "  coverage  - Generate detailed coverage report"
        echo "  watch     - Run tests in watch mode (requires pytest-watch)"
        echo "  failed    - Re-run only failed tests"
        echo ""
        echo "Examples:"
        echo "  ./run_bot_tests.sh              # Run all tests"
        echo "  ./run_bot_tests.sh fast         # Quick run without coverage"
        echo "  ./run_bot_tests.sh commands     # Test only commands"
        echo "  ./run_bot_tests.sh coverage     # Generate coverage report"
        exit 1
        ;;
esac

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ All tests passed!${NC}"
    echo ""
else
    echo ""
    echo -e "${RED}❌ Some tests failed${NC}"
    echo ""
    exit 1
fi
