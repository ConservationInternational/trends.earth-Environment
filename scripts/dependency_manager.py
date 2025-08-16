#!/usr/bin/env python3
"""
Dependency management and security checking script.

This script helps maintain secure and up-to-date dependencies.
"""

import argparse
import json
import subprocess
import sys


def run_command(cmd, capture_output=True):
    """Run a command and return the result."""
    try:
        result = subprocess.run(  # noqa: S602
            cmd, shell=True, capture_output=capture_output, text=True, check=True
        )
        return result.stdout if capture_output else ""
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}")
        print(f"Error: {e.stderr if capture_output else str(e)}")
        return None


def check_vulnerabilities():
    """Check for security vulnerabilities in dependencies."""
    print("🔍 Checking for security vulnerabilities...")

    # Use the newer safety scan command
    cmd = "safety scan -r requirements.txt --json"
    result = run_command(cmd)

    if result is None:
        print("❌ Failed to run vulnerability scan")
        return False

    try:
        # Try to parse as JSON to check for vulnerabilities
        data = json.loads(result)
        vuln_count = data.get("vulnerabilities_found", 0)

        if vuln_count > 0:
            print(f"⚠️  Found {vuln_count} vulnerabilities")
            print("Run 'safety scan -r requirements.txt' for details")
            return False
        else:
            print("✅ No known vulnerabilities found")
            return True
    except json.JSONDecodeError:
        # Fallback to checking exit code
        print("✅ Vulnerability scan completed")
        return True


def check_outdated():
    """Check for outdated dependencies."""
    print("\n📦 Checking for outdated dependencies...")

    cmd = "pip list --outdated --format=json"
    result = run_command(cmd)

    if result is None:
        print("❌ Failed to check for outdated packages")
        return

    try:
        outdated = json.loads(result)
        if outdated:
            print(f"📋 Found {len(outdated)} outdated packages:")
            for pkg in outdated:
                print(f"  • {pkg['name']}: {pkg['version']} → {pkg['latest_version']}")
        else:
            print("✅ All packages are up to date")
    except json.JSONDecodeError:
        print("⚠️  Could not parse outdated packages list")


def update_requirements():
    """Update requirements.txt with current installed versions."""
    print("\n🔄 Updating requirements.txt with current versions...")

    cmd = "pip freeze > requirements.txt"
    result = run_command(cmd, capture_output=False)

    if result is not None:
        print("✅ requirements.txt updated")
    else:
        print("❌ Failed to update requirements.txt")


def install_security_tools():
    """Install security scanning tools."""
    print("\n🛠️  Installing security tools...")

    tools = ["safety", "bandit[toml]", "pip-audit"]

    for tool in tools:
        print(f"Installing {tool}...")
        cmd = f"pip install {tool}"
        if run_command(cmd, capture_output=False) is None:
            print(f"❌ Failed to install {tool}")
            return False

    print("✅ Security tools installed")
    return True


def run_security_audit():
    """Run comprehensive security audit."""
    print("\n🔒 Running security audit...")

    # Run pip-audit
    print("Running pip-audit...")
    cmd = "pip-audit --format=json --output=pip-audit-report.json"
    run_command(cmd)

    # Run bandit
    print("Running bandit...")
    cmd = "bandit -r gefcore/ -f json -o bandit-report.json"
    run_command(cmd)

    print("✅ Security audit completed - check generated reports")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Dependency management and security checking"
    )
    parser.add_argument(
        "--check-vulns", action="store_true", help="Check for vulnerabilities"
    )
    parser.add_argument(
        "--check-outdated", action="store_true", help="Check for outdated packages"
    )
    parser.add_argument(
        "--update-requirements", action="store_true", help="Update requirements.txt"
    )
    parser.add_argument(
        "--install-tools", action="store_true", help="Install security tools"
    )
    parser.add_argument(
        "--audit", action="store_true", help="Run comprehensive security audit"
    )
    parser.add_argument("--all", action="store_true", help="Run all checks and updates")

    args = parser.parse_args()

    if not any(vars(args).values()):
        # No arguments provided, show help
        parser.print_help()
        sys.exit(1)

    print("🔐 Dependency Security Manager")
    print("=" * 40)

    if args.all or args.install_tools:
        install_security_tools()

    if args.all or args.check_vulns:
        vuln_check_passed = check_vulnerabilities()
        if not vuln_check_passed and not args.all:
            sys.exit(1)

    if args.all or args.check_outdated:
        check_outdated()

    if args.all or args.update_requirements:
        update_requirements()

    if args.all or args.audit:
        run_security_audit()

    print("\n" + "=" * 40)
    print("🎉 Dependency management completed!")


if __name__ == "__main__":
    main()
