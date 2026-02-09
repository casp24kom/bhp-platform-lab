# Contributing

Thanks for your interest in contributing! This repo is a portfolio/demo project focused on enterprise-style Data/AI platform patterns.

## Ground Rules
- Be respectful and constructive.
- Keep contributions aligned with the project goals: reliability, clarity, and secure-by-default patterns.
- Avoid adding heavy dependencies unless they clearly improve the demo.

## How to Contribute
### 1) Open an Issue (recommended first)
Before starting major work, open an Issue describing:
- The problem/opportunity
- Proposed approach
- Scope (small/medium/large)
- Any design trade-offs

### 2) Submit a Pull Request
PRs should:
- Be focused (one change per PR if possible)
- Include a clear description and screenshots/logs where relevant
- Include tests or validation steps

## Development Setup
### Prereqs
- Python 3.11+
- Docker
- Terraform 1.6+ (optional, for infra)

### Local run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
## Basic checks
Before opening a PR, please verify:
- `GET /health`
- `POST /rag/self_test` (requires Snowflake env vars)

## Security & Secrets (important)
- Never commit: `.env`, `.tfvars`, private keys, certificates, tokens
- Use **GitHub Secrets** for CI/CD
- Avoid printing secrets in logs
- For cloud examples, use **least privilege** and **demo-only** resources

If you find a vulnerability, see `SECURITY.md`.

## Branching / PR conventions
- Branch from `main`
- Suggested branch names:
  - `feature/<short-name>`
  - `fix/<short-name>`
  - `docs/<short-name>`
- PR title format:
  - `feat: ...`
  - `fix: ...`
  - `docs: ...`
  - `chore: ...`

## What’s welcome
- Documentation improvements (clearer setup steps, diagrams, runbooks)
- Better demo scripts / sample payloads
- Observability improvements (structured logging, correlation IDs)
- Safer defaults (rate limiting, JWT hardening, input validation)
- Terraform improvements that reduce cost/risk for demo users
- CI/CD improvements (reliability, destroy workflows, linting)

## What’s not welcome (usually)
- Large framework rewrites
- New paid services that complicate “demo-only” usage
- Changes that reduce clarity of the “enterprise-aligned” story

## License
By contributing, you agree your contributions will be licensed under the MIT License (same as this repo).