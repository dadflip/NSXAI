# Contributing & Versioning Guide

This document describes development conventions, versioning workflow, and best practices for contributing to the NSXAI project.

---

## Table of Contents

- [Development Workflow](#development-workflow)
- [Version Management](#version-management)
- [CI/CD GitHub Actions](#cicd-github-actions)
- [Code Conventions](#code-conventions)
- [Contribution Process](#contribution-process)

---

## Development Workflow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   feature/  │ ──→ │   develop   │ ──→ │    main     │
│   branch    │     │   branch    │     │   branch    │
└─────────────┘     └─────────────┘     └─────────────┘
                                              ↓
                                         [vX.Y.Z tag]
                                              ↓
                                      [GitHub Release]
```

### Branches

| Branch | Purpose |
|---------|---------|
| `main` | Stable production code (releases) |
| `develop` | Integration branch (merged features) |
| `feature/*` | New feature development |
| `hotfix/*` | Urgent fixes on `main` |
| `release/*` | Release preparation |

### Git Workflow

```bash
# 1. Create a feature branch from develop
git checkout develop
git pull origin develop
git checkout -b feature/feature-name

# 2. Develop and commit
git add .
git commit -m "feat: add feature X"

# 3. Push the branch
git push origin feature/feature-name

# 4. Create a Pull Request to develop
# (via GitHub interface)

# 5. After review and merge, delete the branch
git branch -d feature/feature-name
```

---

## Version Management

This project uses **Semantic Versioning** (SemVer) and `bump-my-version` for version management.

### Semantic Versioning

Format: `MAJOR.MINOR.PATCH[-prerelease]`

| Component | Meaning | When to increment |
|-----------|---------|-------------------|
| **MAJOR** | Breaking changes | API breaking changes |
| **MINOR** | New features | Compatible features |
| **PATCH** | Bug fixes | Compatible bug fixes |
| **prerelease** | Test versions | `-dev`, `-alpha`, `-beta`, `-rc` |

### Configuration Files

| File | Description |
|---------|-------------|
| `@c:\Users\david\Documents\Github\NSXAI\pyproject.toml` | Project configuration (versioning included) |
| `@c:\Users\david\Documents\Github\NSXAI\VERSION` | Current version |
| `@c:\Users\david\Documents\Github\NSXAI\CHANGELOG.md` | Changelog |
| `@c:\Users\david\Documents\Github\NSXAI\.gitattributes` | Line ending normalization |

### Installation

```bash
pip install bump-my-version
```

### Versioning Commands

#### Via Python Script

```bash
# Bump patch (0.1.0-dev → 0.1.1-dev)
python src/scripts/release/bump_version.py patch

# Bump minor (0.1.0-dev → 0.2.0-dev)
python src/scripts/release/bump_version.py minor

# Bump major (0.1.0-dev → 1.0.0-dev)
python src/scripts/release/bump_version.py major

# Release stable version (0.1.0-dev → 0.1.0)
python src/scripts/release/bump_version.py release
```

#### Directly with bump-my-version

```bash
bump-my-version bump patch      # Bump patch
bump-my-version bump minor      # Bump minor
bump-my-version bump major      # Bump major
bump-my-version bump release    # Release stable version
```

### Release Workflow

1. **Update CHANGELOG.md** with version changes
   ```bash
   # Add changes under [Unreleased] in CHANGELOG.md
   ```

2. **Bump version** to stable
   ```bash
   python src/scripts/release/bump_version.py release
   ```

3. **Create Git tag** with the version
   ```bash
   git tag v$(cat VERSION)
   ```

4. **Push to GitHub** (tag push triggers release)
   ```bash
   git push origin main
   git push origin v$(cat VERSION)
   ```

5. **GitHub Actions** automatically creates the release

### Version Examples

| Version | Meaning |
|---------|---------|
| `0.1.0-dev` | Initial development |
| `0.1.0-alpha.1` | First alpha |
| `0.1.0-beta.2` | Second beta |
| `0.1.0-rc.1` | Release candidate |
| `0.1.0` | Stable release |
| `0.1.1` | Patch fix |
| `0.2.0` | New minor feature |
| `1.0.0` | Major release |

---

## CI/CD GitHub Actions

Workflows configured in `@c:\Users\david\Documents\Github\NSXAI\.github\workflows\`:

| Workflow | File | Trigger | Action |
|----------|---------|-------------|--------|
| **CI** | `ci.yml` | Push to `main`/`develop`, PR | Tests, lint, coverage |
| **Release** | `release.yml` | Push tag `v*` | GitHub release creation |

### CI Pipeline

The CI workflow runs:
1. **Tests** on Python 3.10, 3.11, 3.12
2. **Lint** with flake8
3. **Format** check with black
4. **Coverage** with pytest-cov
5. **Upload** to Codecov

### Release Pipeline

The Release workflow:
1. Triggers on tags `v*` (e.g., `v0.1.0`)
2. Automatically creates a GitHub release
3. Uses CHANGELOG.md as description

---

## Code Conventions

### Python

- **Style**: PEP 8
- **Formatter**: black
- **Import sorting**: isort
- **Linter**: flake8
- **Line length**: 127 characters max
- **Docstrings**: Google style

### Git Commits

Format: `type(scope): description`

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting (no code change)
- `refactor`: Refactoring
- `test`: Tests
- `chore`: Maintenance

Examples:
```
feat(symbolic): add OWL ontology loader
fix(api): fix 500 error on /predict
docs(readme): update architecture
```

---

## Contribution Process

1. **Fork** the repository (for external contributors)
2. **Create** a branch `feature/xxx` or `fix/xxx`
3. **Code** following conventions
4. **Test** locally: `pytest`
5. **Commit** with conventional messages
6. **Push** the branch
7. **Create** a Pull Request to `develop`
8. **Wait** for review and green CI
9. **Merge** after approval

---

## Resources

- [Semantic Versioning](https://semver.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [GitHub Actions](https://docs.github.com/actions)
- [bump-my-version](https://github.com/callowayproject/bump-my-version)

---

## Questions?

For any questions about versioning or contributions, open an issue with the `question` label.
