@echo off
echo Setting up test environment...

echo Checking Python version...
python --version
if errorlevel 1 (
    echo Python not found. Please install Python 3.10+ first.
    pause
    exit /b 1
)

echo Installing Python dependencies...
python -m pip install --upgrade pip --user
if errorlevel 1 (
    echo Failed to upgrade pip
    pause
    exit /b 1
)

pip install -r requirements.txt --user
if errorlevel 1 (
    echo Failed to install dependencies
    pause
    exit /b 1
)

echo Running EPUB viewer tests...
cd api
python -m pytest test_epub_viewer.py -v
if errorlevel 1 (
    echo Some tests failed
    pause
    exit /b 1
)

echo All tests completed successfully!
pause