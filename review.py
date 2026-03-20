import fnmatch
import json
import os
import sys
from typing import Any, Dict, List, Optional

import requests
from openai import OpenAI


SEVERITY_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


def log(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def getenv_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        fail(f"Missing required environment variable: {name}")
    return value


def load_event() -> Dict[str, Any]:
    event_path = getenv_required("GITHUB_EVENT_PATH")
    with open(event_path, "r", encoding="utf-8") as f:
        return json.load(f)


def github_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_pull_request_files(
    api_url: str,
    repo: str,
    pr_number: int,
    token: str,
) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    per_page = 100
    page = 1
    url = f"{api_url.rstrip('/')}/repos/{repo}/pulls/{pr_number}/files"

    headers = github_headers(token)

    while True:
        params = {"per_page": per_page, "page": page}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.RequestException as e:
            fail(f"Network error while fetching PR files: {e}")

        if resp.status_code != 200:
            # Try to surface GitHub's error message if present
            try:
                err = resp.json()
                message = err.get("message") or str(err)
            except Exception:
                message = resp.text
            fail(f"Failed to fetch PR files: {resp.status_code} {message}")

        try:
            page_files = resp.json()
            if not isinstance(page_files, list):
                fail(f"Unexpected response when fetching PR files: {page_files}")
        except ValueError:
            fail("Failed to parse JSON response when fetching PR files")

        files.extend(page_files)

        # If fewer than per_page items returned, we've reached the last page
        if len(page_files) < per_page:
            break

        page += 1

    return files


def matches_any_pattern(path: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def normalize_patterns(raw: str) -> List[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


def should_review_file(file_info: Dict[str, Any], exclude_patterns: List[str]) -> bool:
    filename = file_info.get("filename", "")
    status = file_info.get("status", "")

    if not filename:
        return False

    if status == "removed":
        return False

    if matches_any_pattern(filename, exclude_patterns):
        return False

    patch = file_info.get("patch")
    if not patch:
        return False

    return True


def trim_patch(patch: str, max_chars: int) -> str:
    if len(patch) <= max_chars:
        return patch
    return patch[:max_chars] + "\n...[truncated]"


def build_review_payload(
    files: List[Dict[str, Any]],
    max_patch_chars: int,
) -> Dict[str, Any]:
    result_files = []

    for f in files:
        result_files.append(
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
                "changes": f.get("changes"),
                "patch": trim_patch(f.get("patch", ""), max_patch_chars),
            }
        )

    return {"files": result_files}


def build_prompt(min_severity: str) -> str:
    return f"""
You are an expert pull request reviewer for open-source repositories.

Review the provided GitHub pull request diff carefully.

Focus only on:
1. correctness bugs
2. security risks
3. major maintainability problems
4. risky edge cases introduced by the changes

Rules:
- Only report findings that are supported by the diff.
- Do not invent repository context that is not visible.
- Prefer fewer, higher-signal findings.
- Ignore style nits and low-value comments.
- Use severity levels: low, medium, high.
- Only include findings with severity >= {min_severity}.
- If there are no meaningful findings, return an empty findings list.
- Keep the summary concise.

Return valid JSON only in this schema:
{{
  "summary": "short overall summary",
  "findings": [
    {{
      "severity": "low|medium|high",
      "title": "short title",
      "file": "path/to/file",
      "explanation": "why this matters",
      "suggestion": "concrete fix or mitigation"
    }}
  ]
}}
""".strip()


def call_openai_review(
    client: OpenAI,
    model: str,
    payload: Dict[str, Any],
    min_severity: str,
) -> Dict[str, Any]:
    prompt = build_prompt(min_severity)

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": [{"type": "input_text", "text": prompt}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(payload, ensure_ascii=False),
                    }
                ],
            },
        ],
    )

    text = getattr(response, "output_text", "") or ""
    if not text.strip():
        return {"summary": "No review output generated.", "findings": []}

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "summary": "Model returned non-JSON output.",
            "findings": [
                {
                    "severity": "medium",
                    "title": "Model output parsing failed",
                    "file": "",
                    "explanation": text[:1500],
                    "suggestion": "Tighten the prompt or enforce JSON schema handling.",
                }
            ],
        }


def filter_findings_by_severity(
    findings: List[Dict[str, Any]],
    min_severity: str,
) -> List[Dict[str, Any]]:
    min_level = SEVERITY_ORDER.get(min_severity, 2)
    result = []

    for item in findings:
        sev = str(item.get("severity", "medium")).lower()
        if SEVERITY_ORDER.get(sev, 2) >= min_level:
            result.append(item)

    return result


def format_markdown_comment(
    review: Dict[str, Any],
    reviewed_files_count: int,
    skipped_files_count: int,
) -> str:
    summary = review.get("summary", "No summary provided.")
    findings = review.get("findings", [])

    lines = [
        "## AI PR Review",
        "",
        f"**Summary:** {summary}",
        "",
        f"- Reviewed files: `{reviewed_files_count}`",
        f"- Skipped files: `{skipped_files_count}`",
        "",
    ]

    if not findings:
        lines.extend(
            [
                "### Findings",
                "",
                "No medium/high-signal issues found in the reviewed diff.",
            ]
        )
        return "\n".join(lines)

    lines.extend(["### Findings", ""])
    for idx, item in enumerate(findings, start=1):
        severity = item.get("severity", "medium").upper()
        title = item.get("title", "Untitled finding")
        file_name = item.get("file", "")
        explanation = item.get("explanation", "")
        suggestion = item.get("suggestion", "")

        lines.extend(
            [
                f"{idx}. **[{severity}] {title}**",
                f"   - File: `{file_name}`" if file_name else "   - File: `unknown`",
                f"   - Why: {explanation}",
                f"   - Suggestion: {suggestion}",
                "",
            ]
        )

    return "\n".join(lines)


def post_issue_comment(
    api_url: str,
    repo: str,
    pr_number: int,
    token: str,
    body: str,
) -> None:
    url = f"{api_url}/repos/{repo}/issues/{pr_number}/comments"
    resp = requests.post(
        url,
        headers=github_headers(token),
        json={"body": body},
        timeout=30,
    )
    if resp.status_code >= 300:
        fail(f"Failed to post PR comment: {resp.status_code} {resp.text}")


def main() -> None:
    openai_api_key = getenv_required("OPENAI_API_KEY")
    github_token = getenv_required("GITHUB_TOKEN")
    repo = getenv_required("GITHUB_REPOSITORY")
    api_url = getenv_required("GITHUB_API_URL")

    model = os.getenv("INPUT_MODEL", "gpt-5")
    max_files = int(os.getenv("INPUT_MAX_FILES", "20"))
    max_patch_chars = int(os.getenv("INPUT_MAX_PATCH_CHARS", "12000"))
    exclude_patterns = normalize_patterns(os.getenv("INPUT_EXCLUDE_PATTERNS", ""))
    min_severity = os.getenv("INPUT_MIN_SEVERITY", "medium").lower()

    if min_severity not in SEVERITY_ORDER:
        fail("INPUT_MIN_SEVERITY must be one of: low, medium, high")

    event = load_event()
    pr = event.get("pull_request")
    if not pr:
        fail("This action only supports pull_request events")

    pr_number = pr.get("number")
    if not pr_number:
        fail("Could not determine pull request number")

    log(f"Fetching changed files for PR #{pr_number} ...")
    pr_files = get_pull_request_files(api_url, repo, pr_number, github_token)

    reviewable_files = []
    skipped_files = []

    for f in pr_files:
        if should_review_file(f, exclude_patterns):
            reviewable_files.append(f)
        else:
            skipped_files.append(f)

    if len(reviewable_files) > max_files:
        skipped_files.extend(reviewable_files[max_files:])
        reviewable_files = reviewable_files[:max_files]

    if not reviewable_files:
        body = "\n".join(
            [
                "## AI PR Review",
                "",
                "No eligible files found for review after filtering.",
            ]
        )
        post_issue_comment(api_url, repo, pr_number, github_token, body)
        log("No reviewable files found.")
        return

    payload = build_review_payload(reviewable_files, max_patch_chars)

    log(f"Sending {len(reviewable_files)} files to OpenAI model: {model}")
    client = OpenAI(api_key=openai_api_key)
    review = call_openai_review(client, model, payload, min_severity)

    findings = review.get("findings", [])
    review["findings"] = filter_findings_by_severity(findings, min_severity)

    comment_body = format_markdown_comment(
        review=review,
        reviewed_files_count=len(reviewable_files),
        skipped_files_count=len(skipped_files),
    )

    log("Posting review comment to PR ...")
    post_issue_comment(api_url, repo, pr_number, github_token, comment_body)
    log("Done.")


if __name__ == "__main__":
    main()