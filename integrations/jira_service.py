"""Jira Cloud integration for the Healthcare Support Pilot."""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


JIRA_TIMEOUT_SECONDS = 10


class JiraConfigurationError(Exception):
    """Raised when Jira configuration is missing or invalid."""


class JiraIntegrationError(Exception):
    """Raised when Jira operations fail."""


def _get_jira_config():
    base_url = os.getenv("JIRA_BASE_URL", "").strip().rstrip("/")
    email = os.getenv("JIRA_EMAIL", "").strip()
    api_token = os.getenv("JIRA_API_TOKEN", "").strip()
    project_key = os.getenv("JIRA_PROJECT_KEY", "").strip()

    missing = [
        name
        for name, value in (
            ("JIRA_BASE_URL", base_url),
            ("JIRA_EMAIL", email),
            ("JIRA_API_TOKEN", api_token),
            ("JIRA_PROJECT_KEY", project_key),
        )
        if not value
    ]

    if missing:
        raise JiraConfigurationError(
            "Missing Jira environment variables: " + ", ".join(missing)
        )

    if not base_url.startswith("https://"):
        raise JiraConfigurationError(
            "JIRA_BASE_URL must use HTTPS."
        )

    return {
        "base_url": base_url,
        "email": email,
        "api_token": api_token,
        "project_key": project_key,
    }


def _jira_request(method, url, config, **kwargs):
    """Make a bounded-time Jira request and normalize errors."""

    try:
        response = requests.request(
            method,
            url,
            auth=(config["email"], config["api_token"]),
            headers={"Accept": "application/json"},
            timeout=JIRA_TIMEOUT_SECONDS,
            **kwargs,
        )
    except requests.RequestException as exc:
        raise JiraIntegrationError(
            "Could not connect to Jira."
        ) from exc

    if not response.ok:
        try:
            error_data = response.json()
            messages = error_data.get("errorMessages", [])
            field_errors = error_data.get("errors", {})

            details = []
            if messages:
                details.extend(str(message) for message in messages)

            if field_errors:
                details.extend(
                    f"{field}: {message}"
                    for field, message in field_errors.items()
                )

            detail_text = "; ".join(details)
        except (ValueError, AttributeError):
            detail_text = ""

        error_message = (
            f"Jira request failed with HTTP {response.status_code}."
        )
        if detail_text:
            error_message += f" Details: {detail_text}"

        raise JiraIntegrationError(error_message)

    try:
        return response.json()
    except ValueError as exc:
        raise JiraIntegrationError(
            "Jira returned an invalid JSON response."
        ) from exc


def _find_existing_issue(ticket_id, config):
    """Find an issue carrying this application's unique ticket label."""

    label = f"healthcare-support-ticket-{ticket_id}"
    endpoint = f"{config['base_url']}/rest/api/3/search/jql"

    result = _jira_request(
        "GET",
        endpoint,
        config,
        params={
            "jql": (
                f'project = "{config["project_key"]}" '
                f'AND labels = "{label}"'
            ),
            "fields": "key",
            "maxResults": 2,
        },
    )

    issues = result.get("issues")
    if not isinstance(issues, list):
        raise JiraIntegrationError(
            "Jira search response did not contain an issues list."
        )

    if not issues:
        return None

    # If duplicates already exist, reuse one rather than creating another.
    issue = issues[0]
    issue_key = issue.get("key") if isinstance(issue, dict) else None

    if not isinstance(issue_key, str) or not issue_key:
        raise JiraIntegrationError(
            "Jira search returned an invalid issue."
        )

    return {
        "key": issue_key,
        "url": f'{config["base_url"]}/browse/{issue_key}',
    }


def create_jira_issue(ticket):
    """Find or create the Jira issue associated with a saved support ticket."""

    config = _get_jira_config()

    ticket_id = ticket.get("ticket_id")
    if ticket_id is None:
        raise ValueError("ticket_id is required to create a Jira issue")

    # Search first so a retry after an uncertain result can reuse the issue.
    existing = _find_existing_issue(ticket_id, config)
    if existing:
        return existing

    title = str(ticket.get("title") or "").strip()
    if not title:
        title = f"Healthcare support ticket #{ticket_id}"

    label = f"healthcare-support-ticket-{ticket_id}"

    description_lines = [
        f"Healthcare Support Pilot ticket: #{ticket_id}",
        f"Category: {ticket.get('category') or 'Unknown'}",
        f"Priority: {ticket.get('priority') or 'Not specified'}",
        f"Severity: {ticket.get('severity') or 'Not specified'}",
        f"Status: {ticket.get('status') or 'Open'}",
        "",
        (
            "Review the original ticket in the Healthcare Support Pilot "
            "using the application's access controls."
        ),
    ]

    description = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": line,
                    }
                ],
            }
            for line in description_lines
        ],
    }

    payload = {
        "fields": {
            "project": {"key": config["project_key"]},
            "summary": f"[Support #{ticket_id}] {title}"[:250],
            "description": description,
            "issuetype": {"name": "Task"},
            "labels": [
                "healthcare-support-pilot",
                label,
            ],
        }
    }

    result = _jira_request(
        "POST",
        f'{config["base_url"]}/rest/api/3/issue',
        config,
        json=payload,
    )

    issue_key = result.get("key")
    if not isinstance(issue_key, str) or not issue_key:
        raise JiraIntegrationError(
            "Jira response did not contain an issue key."
        )

    return {
        "key": issue_key,
        "url": f'{config["base_url"]}/browse/{issue_key}',
    }