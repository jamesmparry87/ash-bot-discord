#!/bin/bash

# Discord Bot - Local Testing Script
# This script runs the complete test suite locally with proper environment setup

set -e  # Exit on any error

echo "🤖 Discord Bot - Local Testing Suite"
echo "===================================="

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "Live/ash_bot_fallback.py" ]; then
    print_error "Please run this script from the project root directory"
    exit 1
fi

# Check Python version
python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
required_version="3.11"
print_status "Detected Python version: $python_version"

if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is required but not installed"
    exit 1
fi

# Check for virtual environment
if [[ "$VIRTUAL_ENV" != "" ]]; then
    print_success "Virtual environment detected: $VIRTUAL_ENV"
else
    print_warning "No virtual environment detected. Consider using 'python -m venv venv && source venv/bin/activate'"
fi

# Install dependencies
print_status "Installing dependencies..."
python3 -m pip install --upgrade pip
pip install -r Live/requirements.txt
pip install -r tests/requirements-test.txt

# Setup test environment
print_status "Setting up test environment..."
export TEST_MODE=true

# Set default test environment variables if not already set
export DISCORD_TOKEN=${DISCORD_TOKEN:-"test_discord_token_12345"}
export DATABASE_URL=${DATABASE_URL:-"postgresql://test:test@localhost/test_discord_bot"}
export GOOGLE_API_KEY=${GOOGLE_API_KEY:-"test_google_api_key_12345"}
export ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-"test_anthropic_api_key_12345"}
export YOUTUBE_API_KEY=${YOUTUBE_API_KEY:-"test_youtube_api_key_12345"}
export TWITCH_CLIENT_ID=${TWITCH_CLIENT_ID:-"test_twitch_client_id_12345"}
export TWITCH_CLIENT_SECRET=${TWITCH_CLIENT_SECRET:-"test_twitch_client_secret_12345"}
export GUILD_ID=${GUILD_ID:-"123456789"}
export VIOLATION_CHANNEL_ID=${VIOLATION_CHANNEL_ID:-"123456790"}
export MOD_ALERT_CHANNEL_ID=${MOD_ALERT_CHANNEL_ID:-"123456791"}
export TWITCH_HISTORY_CHANNEL_ID=${TWITCH_HISTORY_CHANNEL_ID:-"123456792"}
export YOUTUBE_HISTORY_CHANNEL_ID=${YOUTUBE_HISTORY_CHANNEL_ID:-"123456793"}
export RECOMMEND_CHANNEL_ID=${RECOMMEND_CHANNEL_ID:-"123456794"}

# Validate test environment
print_status "Validating test environment..."
python3 test_config.py

# Check for PostgreSQL (optional for full integration tests)
if command -v pg_isready &> /dev/null; then
    if pg_isready -h localhost >/dev/null 2>&1; then
        print_success "PostgreSQL is available for integration tests"
        export POSTGRES_AVAILABLE=true
    else
        print_warning "PostgreSQL not running - integration tests will use mocks"
        export POSTGRES_AVAILABLE=false
    fi
else
    print_warning "PostgreSQL not installed - integration tests will use mocks"
    export POSTGRES_AVAILABLE=false
fi

# Function to run tests with proper error handling
run_test_suite() {
    local test_name=$1
    local test_file=$2
    local extra_args=${3:-""}
    
    print_status "Running $test_name..."
    
    if python3 -m pytest $test_file -v --tb=short $extra_args; then
        print_success "$test_name passed"
        return 0
    else
        print_error "$test_name failed"
        return 1
    fi
}

# Parse command line arguments
RUN_ALL=true
RUN_LINT=false
RUN_SECURITY=false
VERBOSE=false
COVERAGE=false
SMOKE_TEST=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --database)
            RUN_ALL=false
            RUN_DATABASE=true
            shift
            ;;
        --commands)
            RUN_ALL=false
            RUN_COMMANDS=true
            shift
            ;;
        --ai)
            RUN_ALL=false
            RUN_AI=true
            shift
            ;;
        --lint)
            RUN_LINT=true
            shift
            ;;
        --security)
            RUN_SECURITY=true
            shift
            ;;
        --coverage)
            COVERAGE=true
            shift
            ;;
        --smoke)
            SMOKE_TEST=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --database    Run only database tests"
            echo "  --commands    Run only command tests"
            echo "  --ai          Run only AI integration tests"
            echo "  --lint        Run code linting"
            echo "  --security    Run security checks"
            echo "  --coverage    Run with coverage reporting"
            echo "  --smoke       Run smoke test only"
            echo "  --verbose     Verbose output"
            echo "  --help        Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                    # Run all tests"
            echo "  $0 --database         # Run only database tests"
            echo "  $0 --coverage --lint  # Run all tests with coverage and linting"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Set verbose flag for pytest
PYTEST_ARGS=""
if [ "$VERBOSE" = true ]; then
    PYTEST_ARGS="$PYTEST_ARGS -vv"
fi

# Set coverage flag
if [ "$COVERAGE" = true ]; then
    PYTEST_ARGS="$PYTEST_ARGS --cov=Live --cov-report=term-missing --cov-report=html"
fi

# Main test execution
print_status "Starting test execution..."
echo

# Track test results
FAILED_TESTS=()

# Run smoke test if requested
if [ "$SMOKE_TEST" = true ]; then
    print_status "Running smoke test..."
    cd Live
    if timeout 10s python3 -c "
import ash_bot_fallback
print('✅ Bot imports successfully')
db = ash_bot_fallback.db
if hasattr(db, 'database_url') and db.database_url:
    print('✅ Database connection configured')
else:
    print('⚠️ Database connection not configured (expected for testing)')
print('✅ Smoke test passed - basic functionality verified')
" 2>/dev/null; then
        print_success "Smoke test passed"
    else
        print_error "Smoke test failed"
        exit 1
    fi
    cd ..
    exit 0
fi

# Run specific test suites based on arguments
if [ "$RUN_ALL" = true ] || [ "$RUN_DATABASE" = true ]; then
    if ! run_test_suite "Database Tests" "tests/test_database.py" "$PYTEST_ARGS"; then
        FAILED_TESTS+=("Database")
    fi
    echo
fi

if [ "$RUN_ALL" = true ] || [ "$RUN_COMMANDS" = true ]; then
    if ! run_test_suite "Command Tests" "tests/test_commands.py" "$PYTEST_ARGS"; then
        FAILED_TESTS+=("Commands")
    fi
    echo
fi

if [ "$RUN_ALL" = true ] || [ "$RUN_AI" = true ]; then
    if ! run_test_suite "AI Integration Tests" "tests/test_ai_integration.py" "$PYTEST_ARGS"; then
        FAILED_TESTS+=("AI Integration")
    fi
    echo
fi

# Run all tests together if RUN_ALL is true
if [ "$RUN_ALL" = true ]; then
    print_status "Running complete test suite..."
    if ! run_test_suite "Complete Test Suite" "tests/" "$PYTEST_ARGS"; then
        FAILED_TESTS+=("Complete Suite")
    fi
    echo
fi

# Run linting if requested
if [ "$RUN_LINT" = true ]; then
    print_status "Running code quality checks..."
    
    # Install linting tools if not available
    pip install black isort flake8 mypy > /dev/null 2>&1
    
    echo "🔍 Checking code formatting with Black..."
    if black --check --diff Live/ tests/ 2>/dev/null; then
        print_success "Black formatting check passed"
    else
        print_warning "Black formatting issues found (run 'black Live/ tests/' to fix)"
    fi
    
    echo "🔍 Checking import sorting with isort..."
    if isort --check-only --diff Live/ tests/ 2>/dev/null; then
        print_success "Import sorting check passed"
    else
        print_warning "Import sorting issues found (run 'isort Live/ tests/' to fix)"
    fi
    
    echo "🔍 Running flake8 linting..."
    if flake8 Live/ tests/ --max-line-length=120 --extend-ignore=E203,W503 2>/dev/null; then
        print_success "Flake8 linting passed"
    else
        print_warning "Flake8 found code style issues"
    fi
    
    echo "🔍 Running mypy type checking..."
    if mypy Live/database.py --ignore-missing-imports > /dev/null 2>&1; then
        print_success "MyPy type checking passed"
    else
        print_warning "MyPy found type issues (non-blocking)"
    fi
    echo
fi

# Run security checks if requested
if [ "$RUN_SECURITY" = true ]; then
    print_status "Running security checks..."
    
    # Install security tools if not available
    pip install bandit safety > /dev/null 2>&1
    
    echo "🛡️ Running Bandit security analysis..."
    if bandit -r Live/ -f json > bandit-report.json 2>/dev/null; then
        print_success "Bandit security check passed"
    else
        print_warning "Bandit found potential security issues (check bandit-report.json)"
    fi
    
    echo "🛡️ Checking for known vulnerabilities with Safety..."
    if safety check --json > safety-report.json 2>/dev/null; then
        print_success "Safety vulnerability check passed"
    else
        print_warning "Safety found known vulnerabilities (check safety-report.json)"
    fi
    echo
fi

# Final results
echo "🎯 Test Results Summary"
echo "======================"

if [ ${#FAILED_TESTS[@]} -eq 0 ]; then
    print_success "All tests passed successfully! ✨"
    echo
    print_status "Your bot is ready for deployment to the staging environment."
    echo "Next steps:"
    echo "1. Commit your changes to the develop branch"
    echo "2. Push to GitHub to trigger automated CI/CD tests"
    echo "3. If CI passes, your changes will be ready for staging deployment"
    exit 0
else
    print_error "Some tests failed:"
    for test in "${FAILED_TESTS[@]}"; do
        echo "  ❌ $test"
    done
    echo
    print_status "Please fix the failing tests before deploying."
    echo "Run specific test suites with: $0 --database, $0 --commands, or $0 --ai"
    exit 1
fi
