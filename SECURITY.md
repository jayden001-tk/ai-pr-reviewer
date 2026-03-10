
---

## `SECURITY.md`

```md
# Security Policy

## Supported versions

This project is in early development.

Security fixes will generally be applied to the latest maintained version.

## Reporting a vulnerability

Please do not open public GitHub issues for suspected security vulnerabilities.

Instead, report security issues privately to the maintainer.

Include the following where possible:

- description of the issue
- steps to reproduce
- affected component or file
- impact assessment
- suggested remediation, if known

## Scope

Examples of security-relevant issues include:

- exposure of API keys, tokens, or secrets
- insecure handling of pull request data
- prompt injection risks that affect review behavior
- unintended posting of sensitive code or content
- privilege escalation through GitHub Action permissions
- unsafe logging of repository content
- insecure defaults for public repositories

## Security expectations

This project aims to follow these principles:

- least-privilege GitHub permissions
- no automatic merge or code execution from model output
- no unnecessary retention of sensitive content
- explicit and reviewable automation behavior
- safe defaults for OSS repositories

## Out of scope

The following are generally out of scope unless they lead to a real security impact:

- low-severity content quality issues
- false positives in review suggestions
- prompt style preferences
- minor documentation mistakes

## Disclosure

Please allow reasonable time to investigate and fix reported issues before public disclosure.