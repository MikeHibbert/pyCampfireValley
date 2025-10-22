# PyPI Publishing Guide for CampfireValley

This guide provides instructions for publishing CampfireValley to PyPI.

## Prerequisites

1. **PyPI Account**: Create accounts on both:
   - [PyPI](https://pypi.org/account/register/) (production)
   - [TestPyPI](https://test.pypi.org/account/register/) (testing)

2. **API Tokens**: Generate API tokens for secure publishing:
   - Go to Account Settings → API tokens
   - Create a token with "Entire account" scope
   - Save the token securely (it won't be shown again)

3. **Configure `.pypirc`**: Create `~/.pypirc` file:
   ```ini
   [distutils]
   index-servers =
       pypi
       testpypi

   [pypi]
   repository = https://upload.pypi.org/legacy/
   username = __token__
   password = pypi-your-api-token-here

   [testpypi]
   repository = https://test.pypi.org/legacy/
   username = __token__
   password = pypi-your-testpypi-token-here
   ```

## Publishing Process

### Step 1: Verify Package Build

The package has already been built and tested:
```bash
# Build was successful - files in dist/:
# - campfirevalley-1.1.0-py3-none-any.whl
# - campfirevalley-1.1.0.tar.gz

# Verification passed:
twine check dist/campfirevalley-1.1.0*
```

### Step 2: Test Upload to TestPyPI (Recommended)

```bash
# Upload to TestPyPI first
twine upload --repository testpypi dist/campfirevalley-1.1.0*

# Test installation from TestPyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ campfirevalley==1.1.0
```

### Step 3: Upload to Production PyPI

```bash
# Upload to production PyPI
twine upload dist/campfirevalley-1.1.1*
```

### Step 4: Verify Installation

```bash
# Install from PyPI
pip install campfirevalley==1.1.1

# Test the installation
python -c "import campfirevalley; print(campfirevalley.__version__)"
campfirevalley --help
```

## Package Information

- **Package Name**: `campfirevalley`
- **Version**: `1.1.1`
- **Description**: A distributed AI agent orchestration platform with visual LiteGraph interface
- **Author**: Mike Hibbert
- **License**: MIT
- **Python Support**: 3.8+

## Key Features in v1.1.0

- LiteGraph integration for visual campfire management
- Enhanced web interface with FastAPI backend
- Federation support for multi-valley environments
- Comprehensive documentation and configuration improvements

## Files Included in Package

- Core Python modules (`campfirevalley/`)
- Web interface assets (`campfirevalley/web/static/`)
- Configuration files and templates
- Command-line interface tools

## Troubleshooting

### Common Issues

1. **Authentication Error**:
   - Verify API token is correct
   - Check `.pypirc` configuration
   - Ensure token has proper permissions

2. **Package Already Exists**:
   - Cannot re-upload same version
   - Increment version number if needed
   - Use `--skip-existing` flag for partial uploads

3. **Metadata Issues**:
   - Run `twine check` before uploading
   - Verify `pyproject.toml` configuration
   - Check README.md formatting

### Useful Commands

```bash
# Check package metadata
twine check dist/*

# Upload with verbose output
twine upload --verbose dist/campfirevalley-1.1.0*

# Upload only if doesn't exist
twine upload --skip-existing dist/campfirevalley-1.1.0*

# Upload to specific repository
twine upload --repository testpypi dist/campfirevalley-1.1.0*
```

## Security Notes

- Never commit API tokens to version control
- Use environment variables for CI/CD: `TWINE_USERNAME` and `TWINE_PASSWORD`
- Regularly rotate API tokens
- Use scoped tokens when possible

## Next Steps After Publishing

1. Update project documentation with installation instructions
2. Create GitHub release with changelog
3. Announce release on relevant channels
4. Monitor for issues and user feedback

## Automated Publishing (Optional)

Consider setting up GitHub Actions for automated publishing:

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.x'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine
    - name: Build package
      run: python -m build
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: twine upload dist/*
```

Remember to add `PYPI_API_TOKEN` to your GitHub repository secrets.