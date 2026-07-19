## Issue-First Branch Workflow

### WHAT

- Never make changes directly on `main`.
- Before starting work, create a GitHub Issue that describes the work.
- Perform the work on a non-`main` branch associated with that Issue.

## Documentation

### HOW

- Update related documentation when code changes affect users
- Document usage for new features in README
- Update relevant docs when interfaces change
- Split large docs into separate files in `docs/` folder
- Add links to split docs in README

## File Operations

### HOW

```bash
# File operations
git mv <old-path> <new-path>  # Move files
git rm <path>                  # Delete files
```
