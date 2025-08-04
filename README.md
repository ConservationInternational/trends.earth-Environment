# trends.earth Environment

This project belongs to the trends.earth project by Conservation International.

This repository implements the Core Platform of the trends.earth Environment for running Google Earth Engine scripts.

Check out the other parts of the trends.earth project:

- The API [trends.earth API](https://github.com/ConservationInternational/trends.earth-API)

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

# Container security scan (requires Docker)
docker run --rm -v $(pwd):/workspace aquasec/trivy fs /workspace
```
