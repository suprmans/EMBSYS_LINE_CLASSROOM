# Development

## One-Time Setup

Install and enable git pre-commit hooks:

```bash
make precommit-install
```

Quick bootstrap (install hooks + run env check):

```bash
make setup
```

## Environment Secret Check

Run this before starting FastAPI to verify required LINE bot secrets exist:

```bash
make check-env
```

Optional: check values from a specific env file:

```bash
make check-env-file
# or
make check-env-file ENV_FILE=.env.local
```

Optional: validate additional variables:

```bash
uv run scripts/check_env.py --require APP_ENV --require WEBHOOK_BASE_URL
```

## Pre-Commit Workflow

Run all hooks manually:

```bash
make precommit-run
```

Update hook versions:

```bash
make precommit-update
```

Regenerate secrets baseline:

```bash
make baseline-generate
```

Audit baseline entries:

```bash
make baseline-audit
```

