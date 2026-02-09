# Security Policy

Thanks for helping keep this project secure.

## Supported Versions
This is a public demo repository intended for learning and portfolio purposes. Only the latest `main` branch is maintained.

## Reporting a Vulnerability
If you believe you’ve found a security issue, **please do not open a public GitHub Issue**.

Instead:
1. Email the maintainer with details (preferred), or
2. Use GitHub “Report a vulnerability” (Security tab) if enabled.

Include:
- A clear description of the issue and potential impact
- Steps to reproduce (proof-of-concept is helpful)
- Any relevant logs, screenshots, or configuration notes
- Whether the issue is already publicly known

## Scope
In scope:
- Secrets exposure (keys, tokens, private certs, `.env`, `tfvars`)
- Authentication/authorization bypass
- Injection vulnerabilities (SQLi, command injection, template injection)
- SSRF, insecure deserialization, path traversal
- Unsafe CI/CD practices (e.g., untrusted PRs gaining secret access)

Out of scope:
- Social engineering
- Issues requiring physical access
- Vulnerabilities in third-party services outside this repo (cloud provider issues)

## Secure Development Notes (Repo Rules)
- **Never commit secrets** (keys, tokens, certificates, `.env`, `.tfvars`)
- Use **GitHub Secrets** for CI/CD
- Prefer short-lived identity (OIDC) over long-lived keys when possible
- Demo stacks should be **destroyed after use** to reduce risk exposure
- Public endpoints should be treated as internet-exposed services:
  - Enable auth (JWT) for non-health endpoints
  - Rate-limit where possible
  - Use least-privilege permissions for cloud roles/users

## Response Expectations
I’ll acknowledge valid reports and aim to respond promptly. For accepted issues:
- I’ll share mitigation guidance and patch plans
- I may request more details to verify

Thank you for responsible disclosure.