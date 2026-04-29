"""
skills/send_email.py
Send email via SMTP. High-risk - triggers approval in remote bridge.
Requires env vars: JARVIS_SMTP_HOST, JARVIS_SMTP_PORT, JARVIS_SMTP_USER, JARVIS_SMTP_PASS
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from skills.base import SkillBase, SkillResult


logger = logging.getLogger("jarvis.skills.send_email")


class SendEmailSkill(SkillBase):
    name = "send_email"
    description = "Sends an email to a recipient via SMTP"
    timeout_seconds = 15.0

    def execute(self, params: dict, state) -> SkillResult:
        _ = state
        to = str(params.get("to", "")).strip()
        subject = str(params.get("subject", "Message from Jarvis")).strip()
        body = str(params.get("body", "")).strip()

        if not to:
            return SkillResult(success=False, output=None, error="No recipient specified")
        if not body:
            return SkillResult(success=False, output=None, error="No email body specified")

        smtp_host = os.environ.get("JARVIS_SMTP_HOST", "")
        smtp_port = int(os.environ.get("JARVIS_SMTP_PORT", "587"))
        smtp_user = os.environ.get("JARVIS_SMTP_USER", "")
        smtp_pass = os.environ.get("JARVIS_SMTP_PASS", "")

        if not all([smtp_host, smtp_user, smtp_pass]):
            return SkillResult(
                success=False,
                output=None,
                error="SMTP not configured. Set JARVIS_SMTP_HOST, JARVIS_SMTP_USER, JARVIS_SMTP_PASS",
            )

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

            logger.info("Email sent to %s", to)
            return SkillResult(success=True, output=f"Email sent to {to}")

        except smtplib.SMTPAuthenticationError:
            return SkillResult(success=False, output=None, error="SMTP authentication failed")
        except smtplib.SMTPException as exc:
            return SkillResult(success=False, output=None, error=f"SMTP error: {exc}")
        except Exception as exc:
            logger.error("send_email error: %s", exc)
            return SkillResult(success=False, output=None, error=str(exc))
