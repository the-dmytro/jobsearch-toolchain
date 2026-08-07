# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

Please report security issues privately via GitHub Security Advisories on this repository, or email the maintainer listed in the repository profile.

Do not open public issues for security vulnerabilities.

## Scope

- SQL injection in `jobtracker/store/` query paths
- Authentication bypass in `crm/` middleware or RLS policies
- Credential leakage in logs, error messages, or committed files

## Out of scope

- Scraping third-party job boards against their terms of service
- Storing credentials in tracked configuration files (use `.env`, never commit)
