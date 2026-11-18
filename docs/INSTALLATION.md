# Installation & Setup Guide
## Local Privacy & Security Module

---

## 1. System Prerequisites

- **Python**: Python 3.11, 3.12, 3.13, or 3.14 (Verified on Python 3.14.7 64-bit).
- **Operating System**:
  - **Windows**: Windows 10 or Windows 11 (64-bit) with Windows Hello support.
  - **Linux**: Linux Mint (Cinnamon), Ubuntu 22.04+, or Debian-based distributions with DBus / `fprintd` / `secretstorage`.
  - **macOS**: macOS 12+ Monterey / Ventura / Sonoma / Sequoia with Touch ID.

---

## 2. Setting Up the Virtual Environment

### Windows (PowerShell)
```powershell
# Navigate to workspace
cd E:\PRO

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```

### Linux / macOS (Bash / Zsh)
```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## 3. Installing Dependencies

Install dependencies from `pyproject.toml` into your virtual environment:

```bash
pip install --upgrade pip setuptools wheel
pip install -e ".[dev]" --no-build-isolation
```

### Key Dependencies Installed
- `sqlcipher3-wheels`: Pre-compiled binary wheel with SQLCipher 4.12.0 community and FTS5 enabled.
- `argon2-cffi`: High-security salted Argon2id password/PIN hashing.
- `cryptography`: AES-GCM and cryptographic primitives.
- `PySide6`: Official Qt 6 desktop application framework.
- `pydantic`: Typed data validation for domain records.
- `pytest`: Automated test runner.
- `ruff`: Fast linter and formatter.
- `mypy`: Static type checker.

---

## 4. Running the Desktop Application

Launch the desktop security dashboard and interactive vault:

```powershell
.\.venv\Scripts\python.exe -m local_security.ui.app
```

On first launch:
1. The **Initial Security Setup** dialog will open.
2. Enter your Name, Username, and create a 6-digit PIN.
3. Toggle OS Biometrics (Windows Hello) if supported on your PC.
4. Click **Complete Setup & Encrypt Vault**.

---

## 5. Running Automated Tests

Run the full automated test suite (unit, integration, security audit, cross-platform, and UI tests):

```powershell
.\.venv\Scripts\pytest
```

To run a specific test suite:
```powershell
# Run database and cipher tests
.\.venv\Scripts\pytest tests/unit/test_database.py

# Run encryption and key management tests
.\.venv\Scripts\pytest tests/unit/test_encryption.py

# Run security audit & disk verification tests
.\.venv\Scripts\pytest tests/security/test_security_audit.py

# Run cross-platform adapter tests
.\.venv\Scripts\pytest tests/cross_platform/test_platform_adapters.py
```

---

## 6. Code Quality & Linting

Run Ruff to verify code formatting and standards:

```powershell
.\.venv\Scripts\ruff check src tests examples
```
