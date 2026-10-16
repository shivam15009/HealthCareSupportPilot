"""SMTP email service for Healthcare Support Pilot notifications."""

import os
import smtplib
import ssl
from email.message import EmailMessage


class EmailConfigurationError(Exception):
    """Raised when SMTP configuration is missing or invalid."""


class EmailDeliveryError(Exception):
    """Raised when an email cannot be sent."""


def _get_smtp_config(require_support_recipient=False):
    """Load SMTP settings from environment variables."""
    host = os.getenv("SMTP_HOST", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip()
    recipient = os.getenv("SUPPORT_EMAIL", "").strip()

    required = [
        ("SMTP_HOST", host),
        ("SMTP_USERNAME", username),
        ("SMTP_PASSWORD", password),
        ("SMTP_FROM", sender),
    ]

    if require_support_recipient:
        required.append(("SUPPORT_EMAIL", recipient))

    missing = [name for name, value in required if not value]

    if missing:
        raise EmailConfigurationError(
            "Missing SMTP environment variables: "
            + ", ".join(missing)
        )

    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError as exc:
        raise EmailConfigurationError(
            "SMTP_PORT must be a valid integer."
        ) from exc

    if not 1 <= port <= 65535:
        raise EmailConfigurationError(
            "SMTP_PORT must be between 1 and 65535."
        )

    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() in {
        "1", "true", "yes"
    }
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in {
        "1", "true", "yes"
    }

    if use_ssl and use_tls:
        raise EmailConfigurationError(
            "Choose SMTP_USE_SSL or SMTP_USE_TLS, not both."
        )

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "sender": sender,
        "recipient": recipient,
        "use_ssl": use_ssl,
        "use_tls": use_tls,
    }


def _send_email(config, recipient, subject, body_lines, ticket_id):
    """Send one email using the configured SMTP server."""
    if not recipient or "@" not in recipient:
        raise ValueError("A valid email recipient is required.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["sender"]
    message["To"] = recipient
    message.set_content("\n".join(body_lines))

    try:
        context = ssl.create_default_context()

        if config["use_ssl"]:
            with smtplib.SMTP_SSL(
                config["host"],
                config["port"],
                timeout=10,
                context=context,
            ) as server:
                server.login(config["username"], config["password"])
                server.send_message(message)
        else:
            with smtplib.SMTP(
                config["host"],
                config["port"],
                timeout=10,
            ) as server:
                server.ehlo()

                if config["use_tls"]:
                    server.starttls(context=context)
                    server.ehlo()

                server.login(config["username"], config["password"])
                server.send_message(message)

    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError(
            "Could not deliver the support notification."
        ) from exc

    return {
        "status": "SENT",
        "recipient": recipient,
        "ticket_id": ticket_id,
    }


def send_support_ticket_notification(
    ticket,
    jira_url=None,
    jira_issue_key=None,
    recipient_email=None,
):
    """Notify the support team about a ticket requiring human review."""
    recipient_email = (recipient_email or "").strip()

    config = _get_smtp_config(
        require_support_recipient=not bool(recipient_email)
    )

    ticket_id = ticket.get("ticket_id")
    if ticket_id is None:
        raise ValueError("ticket_id is required to send a notification")

    body_lines = [
        "Hello ",
        "Your support ticket requires human review.",
        "",
        f"Ticket ID: {ticket_id}",
        f"Title: {ticket.get('title') or 'Untitled ticket'}",
        f"Category: {ticket.get('category') or 'Unknown'}",
        f"Priority: {ticket.get('priority') or 'Not specified'}",
        f"Severity: {ticket.get('severity') or 'Not specified'}",
        f"Status: {ticket.get('status') or 'ESCALATE'}",

        "Our Support Team will contact you soon.",
    ]

    if jira_issue_key:
        body_lines.extend(["", f"Jira issue: {jira_issue_key}"])

    if jira_url:
        body_lines.append(f"Jira link: {jira_url}")

    body_lines.extend([
        "",
        "Review the original ticket through the authorized application.",
    ])

    return _send_email(
        config=config,
        recipient=recipient_email or config["recipient"],
        subject=f"[Healthcare Support] Escalated ticket #{ticket_id}",
        body_lines=body_lines,
        ticket_id=ticket_id,
    )


def send_resolution_notification(
    ticket,
    recipient,
    resolution,
    jira_issue_key=None,
    jira_url=None,
):
    """Email the requester the approved resolution instructions."""
    config = _get_smtp_config()

    ticket_id = ticket.get("ticket_id")
    if ticket_id is None:
        raise ValueError("ticket_id is required to send a notification")

    resolution_text = str(resolution or "").strip()
    if not resolution_text:
        raise ValueError(
            "Resolution instructions are required for a resolution email."
        )

    body_lines = [
        "Hello ",
        "Your support ticket has been automatically resolved.",
        "",
        f"Ticket ID: {ticket_id}",
        f"Title: {ticket.get('title') or 'Support ticket'}",
        f"Category: {ticket.get('category') or 'Unknown'}",
        "Status: AUTO_RESOLVE",
        "",
        "Resolution and troubleshooting steps:",
        "",
        resolution_text,
    ]

    if jira_issue_key:
        body_lines.extend(["", f"Jira issue: {jira_issue_key}"])

    if jira_url:
        body_lines.append(f"Jira link: {jira_url}")

    body_lines.extend([
        "",
        "If the issue persists, contact your support team "
        "through the authorized support application.",
    ])

    return _send_email(
        config=config,
        recipient=recipient,
        subject=f"[Healthcare Support] Ticket #{ticket_id} resolved",
        body_lines=body_lines,
        ticket_id=ticket_id,
    )