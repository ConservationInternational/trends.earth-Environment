# trends.earth Environment

[![Tests](https://github.com/ConservationInternational/trends.earth-Environment/actions/workflows/tests.yml/badge.svg)](https://github.com/ConservationInternational/trends.earth-Environment/actions/workflows/tests.yml)
[![Code Quality](https://github.com/ConservationInternational/trends.earth-Environment/actions/workflows/code-quality.yml/badge.svg)](https://github.com/ConservationInternational/trends.earth-Environment/actions/workflows/code-quality.yml)
[![Security Scan](https://github.com/ConservationInternational/trends.earth-Environment/actions/workflows/security.yml/badge.svg)](https://github.com/ConservationInternational/trends.earth-Environment/actions/workflows/security.yml)

This project belongs to the trends.earth project by Conservation International.

This repository implements the Core Platform of the trends.earth Environment for running Google Earth Engine scripts.

## Project Structure

```
trends.earth-Environment/
├── gefcore/                 # Core Python package
│   ├── __init__.py         # Package initialization and main entry point
│   ├── api.py              # API client for trends.earth-API
│   ├── loggers.py          # Custom logging handlers
│   └── runner.py           # Script execution engine
├── scripts/                # Utility scripts
│   └── dependency_manager.py # Security and dependency management
├── tests/                  # Test suite
├── .github/workflows/      # CI/CD workflows
├── Dockerfile             # Container build configuration
├── main.py               # Application entry point
├── entrypoint.sh         # Docker container entrypoint
├── requirements.txt      # Production dependencies
├── requirements-dev.txt  # Development dependencies
├── pyproject.toml       # Project configuration and tools
└── run_tests.sh         # Test execution script
```

## Related Projects

- [trends.earth API](https://github.com/ConservationInternational/trends.earth-API) - Backend API service
- [trends.earth CLI](https://github.com/ConservationInternational/trends.earth-CLI) - Command-line interface

## Development Setup

### Prerequisites

- Python 3.10+ 
- Docker (for containerized development)
- Google Earth Engine service account (for production use)

### Local Development

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ConservationInternational/trends.earth-Environment.git
   cd trends.earth-Environment
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

4. **Run tests:**
   ```bash
   ./run_tests.sh
   # Or directly with pytest
   pytest tests/ -v
   ```

### Docker Development

1. **Build the container:**
   ```bash
   docker build -t trends-earth-env .
   ```

2. **Run the container:**
   ```bash
   docker run --rm \
     -e ENV=development \
     -e TESTING=false \
     trends-earth-env
   ```

## Environment Variables

Required environment variables for production use:

- `ENV` - Environment mode (`production`, `staging`, `development`, `test`)
- `TESTING` - Set to `true` for test environments
- `ROLLBAR_SCRIPT_TOKEN` - Rollbar error reporting token
- `GOOGLE_PROJECT_ID` - Google Cloud Project ID
- `GEE_ENDPOINT` - Google Earth Engine API endpoint
- `API_URL` - trends.earth API base URL
- `API_USER` - API authentication username
- `API_PASSWORD` - API authentication password
- `EXECUTION_ID` - Unique execution identifier
- `PARAMS_S3_BUCKET` - S3 bucket for parameters
- `PARAMS_S3_PREFIX` - S3 key prefix for parameters

## Testing

The project includes comprehensive testing with pytest:

```bash
# Run all tests
./run_tests.sh

# Run specific test files
pytest tests/test_api.py -v

# Run with coverage
pytest tests/ --cov=gefcore --cov-report=html

# Run only fast tests (exclude slow integration tests)
pytest tests/ -m "not slow"
```

## Code Quality

Code quality is maintained using:

- **Ruff** - Fast Python linter and formatter
- **mypy** - Static type checking
- **pytest** - Testing framework with 92%+ coverage requirement

Run quality checks:

```bash
# Linting and formatting
ruff check gefcore/ tests/
ruff format gefcore/ tests/

# Type checking
mypy gefcore/ --ignore-missing-imports
```

## Security

### Security Tools

Use the dependency manager script for security checks:

```bash
# Check for vulnerabilities
python scripts/dependency_manager.py --check-vulns

# Check for outdated packages
python scripts/dependency_manager.py --check-outdated

# Run comprehensive security audit
python scripts/dependency_manager.py --audit

# Run all security checks
python scripts/dependency_manager.py --all
```

### Manual Security Scanning

```bash
# Install security tools
pip install safety bandit[toml]

# Check dependencies for vulnerabilities
safety scan -r requirements.txt

# Scan code for security issues
bandit -r gefcore/

## Architecture

### Core Modules

- **`gefcore.api`** - HTTP client for communicating with trends.earth-API, handles authentication, retries, and error handling
- **`gefcore.runner`** - Main script execution engine that initializes Google Earth Engine and executes user scripts
- **`gefcore.loggers`** - Custom logging handlers that send logs to the API and handle different environment configurations
- **`scripts.dependency_manager`** - Security and dependency management utilities

### Execution Flow

1. Container starts via `main.py` → `gefcore.__init__.py`
2. Environment validation and logger setup
3. Google Earth Engine authentication and initialization
4. Script parameter retrieval from S3
5. User script execution with monitoring and logging
6. Results and status reporting back to API

## Container security scan (requires Docker)
docker run --rm -v $(pwd):/workspace aquasec/trivy fs /workspace
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes and add tests
4. Run the test suite (`./run_tests.sh`)
5. Ensure code quality checks pass
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
