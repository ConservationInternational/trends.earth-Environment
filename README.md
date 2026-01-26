# trends.earth Environment

[![Tests](https://github.com/ConservationInternational/trends.earth-Environment/actions/workflows/tests.yml/badge.svg)](https://github.com/ConservationInternational/trends.earth-Environment/actions/workflows/tests.yml)
[![Code Quality](https://github.com/ConservationInternational/trends.earth-Environment/actions/workflows/code-quality.yml/badge.svg)](https://github.com/ConservationInternational/trends.earth-Environment/actions/workflows/code-quality.yml)
[![Security Scan](https://github.com/ConservationInternational/trends.earth-Environment/actions/workflows/security.yml/badge.svg)](https://github.com/ConservationInternational/trends.earth-Environment/actions/workflows/security.yml)

This project belongs to the trends.earth project by Conservation International.

This repository implements the environment used for executing jobs run via the trends.earth API.

## Project Structure

```
trends.earth-Environment/
├── gefcore/                  # Core Python package
│   ├── __init__.py           # Package initialization and main entry point
│   ├── api.py                # API client for trends.earth-API
│   ├── loggers.py            # Custom logging handlers
│   └── runner.py             # Script execution engine
├── scripts/                  # Utility scripts
│   └── dependency_manager.py # Security and dependency management
├── tests/                    # Test suite
├── .github/workflows/        # CI/CD workflows
├── Dockerfile                # Container build configuration
├── main.py                   # Application entry point
├── entrypoint.sh             # Docker container entrypoint
├── requirements.txt          # Production dependencies
├── requirements-dev.txt      # Development dependencies
├── pyproject.toml            # Project configuration and tools
└── run_tests.sh              # Test execution script
```

## Related Projects

- [trends.earth API](https://github.com/ConservationInternational/trends.earth-API) - Backend API service
- [trends.earth CLI](https://github.com/ConservationInternational/trends.earth-CLI) - Command-line interface

## Developing Custom Scripts

This environment package serves as the execution platform for custom geospatial analysis scripts developed using the [trends.earth CLI](https://github.com/ConservationInternational/trends.earth-CLI). Here's how to create and deploy new scripts:

### Script Package Structure

Custom scripts are organized as packages with the following structure:

```
my-custom-script/
├── configuration.json      # Script metadata and configuration
├── requirements.txt        # Python dependencies specific to this script
└── src/                   # Source code directory
    ├── __init__.py        # Python package initialization
    └── main.py           # Main script entry point with run() function
```

### Script Entry Point

Every script must implement a `run(params, logger)` function in `src/main.py`:

```python
def run(params, logger):
    """
    Main script execution function.
    
    Args:
        params (dict): Parameters passed from the API/UI
        logger: Pre-configured logger instance for progress reporting
    
    Returns:
        dict: Results to be sent back to the API
    """
    # Your script logic here
    logger.info("Script started")
    
    # Access input parameters
    area_of_interest = params.get('geometry')
    start_date = params.get('start_date')
    end_date = params.get('end_date')
    
    # Your analysis logic using Google Earth Engine, NumPy, etc.
    result = perform_analysis(area_of_interest, start_date, end_date)
    
    logger.info("Analysis complete")
    return {
        'status': 'success',
        'results': result
    }
```

### Configuration File

The `configuration.json` file defines script metadata and environment requirements:

```json
{
    "name": "sdg-15-3-1-indicator 2_1_17",
    "environment": "trends.earth-environment", 
    "environment_version": "2.1.18"
}
```

**Required fields:**
- `name` - Unique identifier for your script
- `environment` - Must be "trends.earth-environment" 
- `environment_version` - Version of this environment package to use

**Important:** The environment package is pulled from the main Docker registry (conservationinternational organization). The specified version must be built and publicly available in the registry before scripts can reference it. Check [Docker Hub](https://hub.docker.com/r/conservationinternational/trends.earth-environment) for available versions.

**Server-assigned fields:**
- `id` - Unique UUID assigned by the server when the script is published (do not include in initial submission)

**Note:** When first submitting a script, do **not** include the `id` field in your configuration.json. The server will assign a unique UUID and return it in the response when the script is successfully published.

### Script Parameters

Script parameters are passed via the `params` argument to your `run()` function and are defined through the trends.earth UI or API rather than in the configuration file. Common parameters include:

- `geometry` - GeoJSON area of interest
- `start_date` / `end_date` - Date ranges for analysis  
- `resolution` - Spatial resolution for analysis
- Custom parameters specific to your analysis

### Available Libraries and Services

Scripts running in this environment have access to:

- **Google Earth Engine** - Pre-authenticated and initialized
- **Standard Python libraries** - NumPy, SciPy, etc. (via base requirements)
- **GDAL** - Geospatial Data Abstraction Library (via Docker base image)
- **Additional geospatial libraries** - Can be added via your script's `requirements.txt` (Rasterio, Shapely, Fiona, etc.)
- **Custom logger** - Integrated with trends.earth API for progress tracking
- **Parameter retrieval** - Automatic parameter loading from API (implemented via S3)
- **Result publishing** - Automatic result upload to API

**Note:** The base environment includes essential libraries for geospatial analysis. For additional Python packages, add them to your script's `requirements.txt` file and they will be automatically installed when your script runs.

### Example Scripts

#### Simple NumPy Analysis
```python
import numpy as np

def run(params, logger):
    logger.info("Starting NumPy analysis")
    
    data = np.array(params.get('input_data', []))
    result = np.mean(data)
    
    logger.info(f"Calculated mean: {result}")
    return {'mean': result}
```

#### Google Earth Engine Analysis
```python
import ee

def run(params, logger):
    logger.info("Starting GEE analysis")
    
    # Get area of interest
    geometry = ee.Geometry(params['geometry'])
    
    # Load satellite data
    collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
        .filterBounds(geometry) \
        .filterDate(params['start_date'], params['end_date'])
    
    # Perform analysis
    mean_image = collection.mean()
    
    # Extract statistics
    stats = mean_image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometry,
        scale=30
    ).getInfo()
    
    logger.info("Analysis complete")
    return {'statistics': stats}
```

### Script Development Workflow

1. **Create script package** using trends.earth CLI:
   ```bash
   tecli create my-script
   cd my-script
   ```

2. **Develop your script** in `src/main.py` with the required `run()` function

3. **Test locally** using trends.earth CLI:
   ```bash
   # Test with mock parameters (using query parameters)
   tecli start --param="geometry={...}&start_date=2023-01-01"
   
   # Test with a JSON payload file
   echo '{"geometry": {...}, "start_date": "2023-01-01", "end_date": "2023-12-31"}' > test_params.json
   tecli start --payload=test_params.json
   ```

4. **Publish to API** using CLI:
   ```bash
   tecli publish my-script
   ```

5. **Execute via API** - The script will run in this environment container

### Best Practices

- **Error handling** - Use try/except blocks and log errors appropriately
- **Progress reporting** - Use `logger.info()` for user-visible progress updates
- **Memory management** - Be mindful of memory usage for large datasets
- **Timeouts** - Design scripts to complete within reasonable timeframes
- **Parameter validation** - Validate input parameters before processing
- **Modular code** - Split complex logic into separate functions/modules

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
