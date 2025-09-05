# Test runner script for trends.earth-Environment
# This script runs all tests and code quality checks locally

# Enable strict error handling
$ErrorActionPreference = "Stop"

Write-Host "[TEST] Running trends.earth-Environment test suite..." -ForegroundColor Blue

# Check if we're in the right directory
if (-not (Test-Path "gefcore\__init__.py")) {
    Write-Host "[ERROR] Please run this script from the trends.earth-Environment root directory" -ForegroundColor Red
    exit 1
}

# Check Python version
try {
    $pythonVersion = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
    Write-Host "[INFO] Using Python version $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Could not check Python version: $_" -ForegroundColor Red
    Write-Host "[ERROR] Make sure Python is installed and accessible" -ForegroundColor Red
    exit 1
}

# Set test environment variables
$env:ENV = "test"
$env:TESTING = "true"
$env:ROLLBAR_SCRIPT_TOKEN = "test_token"
$env:GOOGLE_PROJECT_ID = "test_project"
$env:GEE_ENDPOINT = "https://test.example.com"
$env:API_URL = "https://test-api.example.com"
$env:API_USER = "test_user"
$env:API_PASSWORD = "test_password"
$env:EXECUTION_ID = "test_execution_id"
$env:PARAMS_S3_BUCKET = "test-bucket"
$env:PARAMS_S3_PREFIX = "test-prefix"

Write-Host "[INFO] Test environment variables configured" -ForegroundColor Cyan

# Functions for colored output
function Write-Status {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# Check if virtual environment is activated
if (-not $env:VIRTUAL_ENV) {
    Write-Warning "No virtual environment detected. Looking for virtual environment to activate..."
    
    # Check for common virtual environment directory names
    $venvPaths = @(".venv", "venv", ".virtualenv", "env")
    $foundVenv = $null
    
    foreach ($venvPath in $venvPaths) {
        if (Test-Path $venvPath) {
            $foundVenv = $venvPath
            break
        }
    }
    
    if ($foundVenv) {
        Write-Host "[INFO] Found virtual environment at: $foundVenv" -ForegroundColor Cyan
        
        # Try to find activation script in different locations
        $activateScripts = @(
            (Join-Path $foundVenv "Scripts\Activate.ps1"),     # Windows style
            (Join-Path $foundVenv "bin\Activate.ps1"),        # Unix style with PowerShell script
            (Join-Path $foundVenv "Scripts\activate.ps1"),    # Windows style (lowercase)
            (Join-Path $foundVenv "bin\activate.ps1")         # Unix style (lowercase)
        )
        
        $activateScript = $null
        foreach ($script in $activateScripts) {
            if (Test-Path $script) {
                $activateScript = $script
                break
            }
        }
        
        if ($activateScript) {
            Write-Host "[INFO] Using activation script: $activateScript" -ForegroundColor Cyan
            & $activateScript
            Write-Success "Virtual environment activated"
        } else {
            Write-Error "Virtual environment found at '$foundVenv' but no PowerShell activation script found."
            Write-Host "[INFO] Looked for activation scripts at:" -ForegroundColor Yellow
            foreach ($script in $activateScripts) {
                Write-Host "  - $script" -ForegroundColor Gray
            }
            Write-Host "[SOLUTION] Please create a proper virtual environment with: python -m venv .venv" -ForegroundColor Yellow
            exit 1
        }
    } else {
        Write-Error "No virtual environment directory found. Looked for: $($venvPaths -join ', ')"
        Write-Host "[SOLUTION] Please create a virtual environment first with: python -m venv .venv" -ForegroundColor Yellow
        exit 1
    }
}

# Install/upgrade dependencies if needed
Write-Status "Checking dependencies..."
if (Test-Path "requirements-dev.txt") {
    try {
        Write-Host "[INFO] Installing production dependencies..." -ForegroundColor Cyan
        & python -m pip install -q -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install production dependencies"
        }
        
        Write-Host "[INFO] Installing development dependencies..." -ForegroundColor Cyan
        & python -m pip install -q -r requirements-dev.txt
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install development dependencies"
        }
        
        Write-Success "Dependencies installed successfully"
    } catch {
        Write-Error "Failed to install dependencies: $_"
        Write-Host "[INFO] Check the error messages above for specific package issues" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Warning "requirements-dev.txt not found, installing basic requirements only"
    try {
        & python -m pip install -q -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install basic requirements"
        }
        & python -m pip install -q pytest pytest-mock pytest-cov
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install pytest dependencies"
        }
        Write-Success "Basic dependencies installed successfully"
    } catch {
        Write-Error "Failed to install basic dependencies: $_"
        exit 1
    }
}

# Run all unit tests
Write-Status "Running unit tests..."
try {
    $testArgs = @(
        "tests/",
        "-v",
        "--cov=gefcore",
        "--cov-report=term-missing",
        "--cov-report=html",
        "--ignore=.venv",
        "--ignore=venv",
        "--ignore=security-venv",
        "--ignore=__pycache__",
        "--ignore=.pytest_cache",
        "--ignore=htmlcov"
    )
    
    & python -m pytest @testArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Unit tests failed"
    }
    Write-Success "Unit tests passed"
} catch {
    Write-Error "Unit tests failed: $_"
    exit 1
}

# Code quality checks (non-blocking)
Write-Status "Running code quality checks..."

# Check if ruff is available
$ruffAvailable = $false
try {
    & ruff --version > $null 2>&1
    $ruffAvailable = $true
} catch {
    $ruffAvailable = $false
}

if ($ruffAvailable) {
    # Ruff linting
    Write-Status "Running Ruff linting..."
    try {
        $ruffArgs = @(
            "check",
            ".",
            "--exclude=.venv,venv,security-venv,__pycache__",
            "--quiet"
        )
        & ruff @ruffArgs
        Write-Success "Ruff linting passed"
    } catch {
        Write-Warning "Ruff linting issues found. Run 'ruff check . --fix' to fix automatically."
        Write-Host "Issues found:" -ForegroundColor Yellow
        try {
            $ruffCheckArgs = @(
                "check",
                ".",
                "--exclude=.venv,venv,security-venv,__pycache__"
            )
            & ruff @ruffCheckArgs
        } catch {
            # Ignore error for display purposes
        }
    }
    
    # Ruff formatting check
    Write-Status "Checking code formatting with Ruff..."
    try {
        $ruffFormatArgs = @(
            "format",
            "--check",
            ".",
            "--exclude=.venv,venv,security-venv,__pycache__"
        )
        & ruff @ruffFormatArgs > $null 2>&1
        Write-Success "Code formatting (Ruff) passed"
    } catch {
        Write-Warning "Code formatting issues found. Run 'ruff format .' to fix."
        Write-Host "Formatting differences:" -ForegroundColor Yellow
        try {
            $ruffDiffArgs = @(
                "format",
                "--check",
                "--diff",
                ".",
                "--exclude=.venv,venv,security-venv,__pycache__"
            )
            & ruff @ruffDiffArgs
        } catch {
            # Ignore error for display purposes
        }
    }
} else {
    Write-Warning "Ruff not installed, skipping linting and formatting checks"
}

Write-Host ""
Write-Success "All tests completed successfully!"
Write-Host ""
Write-Host "Test coverage report generated in htmlcov\index.html" -ForegroundColor Cyan
Write-Host "To fix formatting and linting issues, run:" -ForegroundColor Cyan
Write-Host "   ruff check . --fix" -ForegroundColor Gray
Write-Host "   ruff format ." -ForegroundColor Gray
Write-Host ""
Write-Host "Your code is ready for commit!" -ForegroundColor Green
