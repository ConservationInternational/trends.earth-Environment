#!/bin/bash

# Test runner script for trends.earth-Environment
# This script runs all tests and code quality checks locally

set -e

echo "🧪 Running trends.earth-Environment test suite..."

# Check if we're in the right directory
if [ ! -f "gefcore/__init__.py" ]; then
    echo "❌ Error: Please run this script from the trends.earth-Environment root directory"
    exit 1
fi

# Set test environment variables
export ENV=test
export TESTING=true
export ROLLBAR_SCRIPT_TOKEN=test_token
export GOOGLE_PROJECT_ID=test_project
export GEE_ENDPOINT=https://test.example.com
export API_URL=https://test-api.example.com
export API_USER=test_user
export API_PASSWORD=test_password
export EXECUTION_ID=test_execution_id
export PARAMS_S3_BUCKET=test-bucket
export PARAMS_S3_PREFIX=test-prefix

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}🔍 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    print_warning "No virtual environment detected. Activating .venv..."
    if [ -d ".venv" ]; then
        source .venv/bin/activate
        print_success "Virtual environment activated"
    else
        print_error ".venv directory not found. Please create one first with: python -m venv .venv"
        exit 1
    fi
fi

# Install/upgrade dependencies if needed
print_status "Checking dependencies..."
if [ -f "requirements-dev.txt" ]; then
    pip install -q -r requirements.txt
    pip install -q -r requirements-dev.txt
    print_success "Dependencies installed"
else
    print_warning "requirements-dev.txt not found, installing basic requirements only"
    pip install -q -r requirements.txt
    pip install -q pytest pytest-mock pytest-cov
fi

# Run all unit tests
print_status "Running unit tests..."
if pytest tests/ -v --cov=gefcore --cov-report=term-missing --cov-report=html \
    --ignore=.venv \
    --ignore=venv \
    --ignore=security-venv \
    --ignore=__pycache__ \
    --ignore=.pytest_cache \
    --ignore=htmlcov; then
    print_success "Unit tests passed"
else
    print_error "Unit tests failed"
    exit 1
fi

# Code quality checks (non-blocking)
print_status "Running code quality checks..."

# Ruff linting and formatting
if command -v ruff >/dev/null 2>&1; then
    print_status "Running Ruff linting..."
    if ruff check . --exclude=".venv,venv,security-venv,__pycache__" --quiet; then
        print_success "Ruff linting passed"
    else
        print_warning "Ruff linting issues found. Run 'ruff check . --fix' to fix automatically."
        echo "Issues found:"
        ruff check . --exclude=".venv,venv,security-venv,__pycache__" || true
    fi
    
    print_status "Checking code formatting with Ruff..."
    if ruff format --check . --exclude=".venv,venv,security-venv,__pycache__" >/dev/null 2>&1; then
        print_success "Code formatting (Ruff) passed"
    else
        print_warning "Code formatting issues found. Run 'ruff format .' to fix."
        echo "Formatting differences:"
        ruff format --check --diff . --exclude=".venv,venv,security-venv,__pycache__" || true
    fi
else
    print_warning "Ruff not installed, skipping linting and formatting checks"
fi

echo ""
print_success "🎉 All tests completed successfully!"
echo ""
echo "📊 Test coverage report generated in htmlcov/index.html"
echo "🔧 To fix formatting and linting issues, run:"
echo "   ruff check . --fix"
echo "   ruff format ."
echo ""
echo "🚀 Your code is ready for commit!"
