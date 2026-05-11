"""
skills/compose_email.py

Composes and opens an email via browser (Gmail web) or SMTP.
Primary path: opens Gmail compose window in browser with pre-filled fields.
Fallback path: uses SMTP if configured via environment variables.

This handles natural language email commands like:
  "send mail to john@example.com asking to attend the meeting"
  "email boss@company.com about the project delay"
"""

import logging
import os
from urllib.parse import urlencode

from skills.base import SkillBase, SkillResult


logger = logging.getLogger("jarvis.skills.compose_email")


def _generate_subject_from_body(body: str) -> str:
    """
    Generate a short subject line from the email body.
    Takes first 8 words, capitalizes first letter.
    """
    words = body.strip().split()[:8]
    if not words:
        return "Message from Jarvis"
    subject = " ".join(words)
    if not subject.endswith((".", "!", "?")):
        subject = subject.rstrip(",;:")
    return subject.capitalize()


def _open_gmail_compose(to: str, subject: str, body: str) -> bool:
    """
    Opens Gmail compose window in browser with pre-filled fields.
    Uses Gmail's URL scheme: https://mail.google.com/mail/?view=cm&to=X&su=Y&body=Z
    """
    try:
        import webbrowser

        params = {
            "view": "cm",
            "to": to,
            "su": subject,
            "body": body,
            "fs": "1",
        }
        url = "https://mail.google.com/mail/?" + urlencode(params)
        webbrowser.open(url)
        logger.info("Opened Gmail compose to: %s", to)
        return True
    except Exception as exc:
        logger.error("Failed to open Gmail compose: %s", exc)
        return False


def _send_via_smtp(to: str, subject: str, body: str) -> tuple[bool, str]:
    """
    Send email via SMTP if credentials are configured.
    Returns (success, message).
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    smtp_host = os.environ.get("JARVIS_SMTP_HOST", "")
    smtp_port = int(os.environ.get("JARVIS_SMTP_PORT", "587"))
    smtp_user = os.environ.get("JARVIS_SMTP_USER", "")
    smtp_pass = os.environ.get("JARVIS_SMTP_PASS", "")

    if not all([smtp_host, smtp_user, smtp_pass]):
        return False, "SMTP not configured"

    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to, msg.as_string())

        logger.info("Email sent via SMTP to %s", to)
        return True, f"Email sent to {to}"
    except Exception as exc:
        logger.error("SMTP send failed: %s", exc)
        return False, str(exc)


class ComposeEmailSkill(SkillBase):
    name = "compose_email"
    description = "Composes and sends an email via Gmail browser or SMTP"
    timeout_seconds = 15.0

    def execute(self, params: dict, state) -> SkillResult:
        to = params.get("to", "").strip()
        body_raw = params.get("body", "").strip()
        subject = params.get("subject", "").strip()

        if not to:
            return SkillResult(
                success=False,
                output=None,
                error="No recipient email address provided",
            )

        if "@" not in to or "." not in to:
            return SkillResult(
                success=False,
                output=None,
                error=f"'{to}' does not look like a valid email address",
            )

        body = self._build_email_body(body_raw)

        if not subject:
            subject = _generate_subject_from_body(body_raw or body)

        smtp_configured = all(
            [
                os.environ.get("JARVIS_SMTP_HOST"),
                os.environ.get("JARVIS_SMTP_USER"),
                os.environ.get("JARVIS_SMTP_PASS"),
            ]
        )

        if smtp_configured:
            success, message = _send_via_smtp(to, subject, body)
            if success:
                return SkillResult(
                    success=True,
                    output=f"Email sent to {to} - Subject: {subject}",
                )
            logger.warning("SMTP failed (%s), falling back to browser compose", message)

        opened = _open_gmail_compose(to, subject, body)
        if opened:
            return SkillResult(
                success=True,
                output=(
                    "Opened Gmail compose window.\n"
                    f"To: {to}\n"
                    f"Subject: {subject}\n"
                    "Body pre-filled - review and click Send."
                ),
            )

        return SkillResult(
            success=False,
            output=None,
            error="Could not open Gmail compose or send via SMTP",
        )

    def _build_email_body(self, raw_body: str) -> str:
        """
        Convert natural language body description to a proper email body.
        Example: "asking to attend the marriage"
        -> "Hi,\n\nAttend the marriage.\n\nBest regards"
        """
        if not raw_body:
            return "Hi,\n\nPlease see the subject for details.\n\nBest regards"

        body = raw_body.strip()

        import re

        body = re.sub(
            r"^(?:asking|saying|telling|requesting|informing|about|regarding)\s+",
            "",
            body,
            flags=re.IGNORECASE,
        )
        body = re.sub(r"^to\s+", "", body, flags=re.IGNORECASE)

        if body:
            body = body[0].upper() + body[1:]

        if body and not body.endswith((".", "!", "?")):
            body += "."

        return f"Hi,\n\n{body}\n\nBest regards"
