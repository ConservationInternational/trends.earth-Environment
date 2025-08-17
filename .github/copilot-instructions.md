# trends.earth Environment

trends.earth Environment is a Python application that implements the Core Platform for running Google Earth Engine scripts. This is part of the larger trends.earth project by Conservation International.

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

### Bootstrap the development environment:
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies - takes ~90 seconds total. NEVER CANCEL.
# May fail in sandboxed environments due to network/SSL issues.
pip install --upgrade pip
pip install -r requirements.txt      # ~30 seconds
pip install -r requirements-dev.txt  # ~60 seconds
```

### Build and test the application:
```bash
# Run full test suite - takes ~20 seconds. NEVER CANCEL.
./run_tests.sh

# Alternative: run pytest directly - takes ~19 seconds
pytest tests/ -v --cov=gefcore --cov-report=term-missing --cov-report=html
```

### Code quality and security checks:
```bash
# Lint and format code - takes <0.1 seconds
ruff check .
ruff format .

# Security scanning - takes ~0.2 seconds
bandit -r gefcore/

# Type checking - takes ~5 seconds, may show missing stub warnings
mypy gefcore/ --ignore-missing-imports --no-strict-optional

# Dependency security check - may timeout in sandboxed environments
safety scan -r requirements.txt

# Comprehensive security audit using built-in script - may timeout
python scripts/dependency_manager.py --all
```

### Run the application:
```bash
# Test basic import (application expects GEE credentials in production)
# Takes ~0.2 seconds
ENV=test TESTING=true python -c "import gefcore; print('Import successful')"

# The application runs as a containerized service processing Earth Engine scripts
# For development, use the test environment with proper environment variables
```

### Docker build (may fail in sandboxed environments):
```bash
# Build container - takes 10+ minutes if successful. NEVER CANCEL.
# Set timeout to 30+ minutes. May fail due to SSL certificate issues.
docker build -t trends-earth-env-test .

# Test container if build succeeds
docker run --rm -e ENV=test -e TESTING=true trends-earth-env-test python -c "import gefcore; print('Import successful')"
```

## Validation

### ALWAYS run these validation steps after making changes:
1. **Test basic functionality**: Run `ENV=test TESTING=true python -c "import gefcore"` to verify imports work
2. **Run test suite**: Execute `./run_tests.sh` - 97 tests must pass with >90% coverage (currently 92%)
3. **Check code quality**: Run `ruff check . && ruff format .` - all checks must pass
4. **Security validation**: Run `bandit -r gefcore/` - no high/medium severity issues allowed
5. **Test coverage**: Ensure test coverage remains above 50% (configured minimum)

### Manual validation scenarios:
- **API changes**: Run tests in `tests/test_api.py` to verify API functionality with mock calls
- **Runner changes**: Run tests in `tests/test_runner.py` to verify Earth Engine integration with mocks
- **Core changes**: Run full test suite and verify no regressions in error handling or logging
- **Security changes**: Run `python scripts/dependency_manager.py --audit` for comprehensive security check

### Complete validation workflow:
```bash
# Run this complete workflow after making any changes:
echo "=== Validating changes ==="
ENV=test TESTING=true python -c "import gefcore; print('✓ Import successful')"
ruff check . && echo "✓ Linting passed"
ruff format --check . && echo "✓ Format check passed"  
bandit -r gefcore/ -q && echo "✓ Security scan passed"
pytest tests/ -q --cov=gefcore && echo "✓ Tests passed with coverage"
echo "🎉 All validation steps completed!"
```

### CI validation requirements:
Always run these before committing to ensure CI passes:
```bash
# Format check (required for CI)
ruff format --check .

# Linting (required for CI)  
ruff check .

# Security checks (informational in CI)
bandit -r gefcore/ -f json -o bandit-report.json || true
safety scan -r requirements.txt --json --output safety-report.json || true
```

## Key Environment Variables

### Required for production:
- `API_URL`: API base URL (e.g., https://api.trendsearth.org)
- `API_USER`: API username/email  
- `API_PASSWORD`: API password
- `EXECUTION_ID`: Execution ID for processing
- `PARAMS_S3_PREFIX`: S3 parameters prefix
- `PARAMS_S3_BUCKET`: S3 parameters bucket
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to GEE service account JSON file

### Required for development/testing:
- `ENV`: Set to "test" for testing, "dev" for development, "prod" for production
- `TESTING`: Set to "true" to enable testing mode and disable GEE authentication

### Optional:
- `ROLLBAR_SCRIPT_TOKEN`: For error tracking (disabled in test mode)
- `GOOGLE_PROJECT_ID`: Google Cloud project ID
- `GEE_ENDPOINT`: Google Earth Engine endpoint URL

## Project Structure

### Core modules (`gefcore/`):
- `api.py`: API communication, authentication, S3 integration (285 lines)
- `runner.py`: Main execution logic, Earth Engine initialization (77 lines)  
- `loggers.py`: Custom logging with server integration (64 lines)
- `__init__.py`: Module initialization and exception handling (62 lines)

### Key files:
- `main.py`: Application entry point
- `entrypoint.sh`: Docker container entry script with credential management
- `run_tests.sh`: Comprehensive test runner with colored output
- `requirements.txt`: Production dependencies (8 packages)
- `requirements-dev.txt`: Development dependencies (6 packages)
- `pyproject.toml`: Project configuration, pytest settings, ruff configuration

### Testing (`tests/`):
- 97 tests across 6 test files
- Tests cover API functionality, runner logic, imports, and error handling
- Uses pytest with mock objects for external dependencies
- Achieves 92% code coverage

### CI/CD (`.github/workflows/`):
- `tests.yml`: Runs tests on Python 3.8-3.12, includes security scans
- `code-quality.yml`: Ruff linting and formatting checks
- `security.yml`: Bandit and Trivy security scanning

## Common Tasks

### Fix formatting issues:
```bash
ruff format .
ruff check . --fix
```

### Update dependencies:
```bash
# Check for vulnerabilities
python scripts/dependency_manager.py --check-vulns

# Check for outdated packages  
python scripts/dependency_manager.py --check-outdated

# Update requirements.txt with current versions
python scripts/dependency_manager.py --update-requirements
```

### Debug test failures:
```bash
# Run specific test file - takes ~18 seconds for test_api.py
pytest tests/test_api.py -v

# Run with detailed output
pytest tests/ -v -s --tb=long

# Run with coverage report - takes ~19 seconds
pytest tests/ --cov=gefcore --cov-report=html
```

### Security audit:
```bash
# Quick security check
bandit -r gefcore/ -ll

# Comprehensive audit
python scripts/dependency_manager.py --audit

# Check for known vulnerabilities
safety scan -r requirements.txt
```

## Important Notes

- **NEVER CANCEL builds or tests**: Test suite takes ~20 seconds, dependency installation ~90 seconds
- **Network limitations**: Dependency installation and security scans may fail in sandboxed environments due to SSL/network issues
- **Environment variables are critical**: Application will fail without proper configuration  
- **Docker builds may fail**: SSL certificate issues common in sandboxed environments
- **Tests use mocks**: External dependencies (GEE, API calls) are mocked in test environment
- **Security is important**: This processes geospatial data and integrates with cloud services
- **Coverage requirement**: Maintain >50% test coverage (currently 92%)
- **Python compatibility**: Supports Python 3.8-3.12, tested in CI

## Troubleshooting

### Import errors:
- Ensure virtual environment is activated: `source .venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt requirements-dev.txt`  
- Set test environment: `ENV=test TESTING=true`

### Dependency installation failures:
- Network/SSL certificate issues are common in sandboxed environments
- Try setting `pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org` if SSL fails
- Use existing working environment when possible instead of fresh installs

### Test failures:
- Check environment variables are set correctly
- Ensure no external network dependencies in test environment
- Run individual test files to isolate issues

### Docker build failures:
- SSL certificate issues are common in sandboxed environments
- Try building with `--network=host` if permitted
- Use direct Python execution for development instead of containers

### CI failures:
- Run `ruff format .` to fix formatting issues
- Run `ruff check . --fix` to auto-fix linting issues  
- Ensure test coverage remains above 50%