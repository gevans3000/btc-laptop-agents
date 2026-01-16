import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    tomllib = None

def get_pyproject_version():
    path = Path("pyproject.toml")
    if not path.exists():
        return None
    with open(path, "rb") as f:
        # Use simple grep-like check if tomllib not available or just for speed
        for line in f:
            if b"version =" in line:
                return line.split(b"=")[1].strip().decode().strip('"').strip("'")
    return None

def get_init_version():
    path = Path("src/laptop_agents/__init__.py")
    if not path.exists():
        return None
    with open(path, "r") as f:
        for line in f:
            if "__version__ =" in line:
                return line.split("=")[1].strip().strip('"').strip("'")
    return None

def main():
    v1 = get_pyproject_version()
    v2 = get_init_version()
    
    if v1 == v2:
        print(f"Versions match: {v1}")
        sys.exit(0)
    else:
        print(f"Version mismatch! pyproject.toml: {v1}, __init__.py: {v2}")
        sys.exit(1)

if __name__ == "__main__":
    main()
