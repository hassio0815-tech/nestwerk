# Security policy

🇬🇧 **English** · 🇩🇪 [Deutsch](SECURITY.de.md)

Nestwerk runs inside family networks and stores data about children. We take security reports seriously.

## Supported versions

| Version | Supported |
|---|---|
| `main` (latest commit) | Yes |
| Older commits and forks | No |

Please update to the latest `main` before reporting.

## Reporting a vulnerability

**Do not open a public issue for security problems.**

Use GitHub's private vulnerability reporting:

1. Open the [Security tab](https://github.com/hassio0815-tech/nestwerk/security) of the repository.
2. Click **Report a vulnerability**.
3. Describe the problem, the affected version or commit, and steps to reproduce.

Please do not include real family data, passwords or tokens in your report.

## What to expect

- We confirm receipt within a few days. Nestwerk is maintained in spare time, so please be patient.
- We assess the report, prepare a fix on `main` and tell you when it is released.
- With your agreement, we credit you in the changelog once the fix is public.

## Scope

In scope: the Nestwerk application, the Docker setup and the scripts in `deploy/`.

Out of scope: problems in your own server, reverse proxy or network setup, and vulnerabilities in third-party dependencies that are already publicly known (please report those upstream; a hint to us is welcome).
