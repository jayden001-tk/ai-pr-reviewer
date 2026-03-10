# AI PR Reviewer
AI PR Reviewer helps maintainers review pull requests faster by analyzing diffs, identifying possible bugs, security risks, and maintainability issues, then posting structured feedback directly on the PR.

## Why this project exists

Maintainers spend a lot of time on repetitive pull request review:
- catching obvious bugs and edge cases
- checking risky changes before merge
- summarizing large diffs
- helping contributors get faster feedback

This project is built for real OSS maintainer workflows, especially:
- pull request review
- issue / PR triage
- release-readiness checks
- contributor feedback automation

## Features

- Review pull request diffs automatically
- Highlight possible bugs, regressions, and risky logic changes
- Flag security-sensitive patterns
- Suggest maintainability improvements
- Post review output back to GitHub pull requests
- Configurable file filters and ignore patterns
- Cost-aware review with file and token limits
- Supports incremental review for updated PRs

## How it works

1. GitHub Actions triggers on `pull_request`
2. The action fetches the PR diff
3. Files are filtered based on configured include/exclude rules
4. Relevant code changes are sent to OpenAI for review
5. The action generates structured review comments
6. Results are posted back to the PR as comments or a summary

## Example workflow

```yaml
name: AI PR Review

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  pull-requests: write
  contents: read

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Run AI PR Reviewer
        uses: jayden001-tk/ai-pr-reviewer@v0.1.0
        with:
          openai_api_key: ${{ secrets.OPENAI_API_KEY }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
          max_files: 30
          exclude: "*.lock,dist/**,coverage/**"