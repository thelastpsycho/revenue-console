"""Builds the stop sale email and sends one copy per recipient over SMTP.

SMTP is configured in backend/.env (never stored in the database or sent to
the browser):

    SMTP_HOST, SMTP_PORT (default 587), SMTP_SECURITY (starttls | ssl | none;
    default ssl on port 465, otherwise starttls), SMTP_USERNAME,
    SMTP_PASSWORD, SMTP_FROM_EMAIL (default SMTP_USERNAME)

Intro, closing and subject may use {name} and {company}, filled in per
recipient.
"""

import html
import os
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from .rules import ALL_ROOMS_LABEL, format_range, group_by_room

SMTP_TIMEOUT = 30
# For waits this long or longer the connection is closed and reopened
# afterwards, rather than left idle for the server to drop.
IDLE_RECONNECT_SECONDS = 30


class SmtpNotConfigured(RuntimeError):
    pass


def smtp_config():
    host = os.environ.get("SMTP_HOST", "").strip()
    port_text = os.environ.get("SMTP_PORT", "").strip() or "587"
    try:
        port = int(port_text)
    except ValueError:
        port = 0
    security = os.environ.get("SMTP_SECURITY", "").strip().lower() or ("ssl" if port == 465 else "starttls")
    username = os.environ.get("SMTP_USERNAME", "").strip()
    from_email = os.environ.get("SMTP_FROM_EMAIL", "").strip() or username
    problems = []
    if not host:
        problems.append("SMTP_HOST is not set")
    if not 0 < port < 65536:
        problems.append("SMTP_PORT is not a valid port")
    if security not in ("starttls", "ssl", "none"):
        problems.append("SMTP_SECURITY must be starttls, ssl or none")
    if not from_email:
        problems.append("SMTP_FROM_EMAIL (or SMTP_USERNAME) is not set")
    if username and not os.environ.get("SMTP_PASSWORD"):
        problems.append("SMTP_PASSWORD is not set")
    return {
        "host": host, "port": port, "security": security, "username": username,
        "fromEmail": from_email, "configured": not problems, "problems": problems,
    }


def public_smtp_status():
    """SMTP status for the UI - no password."""
    cfg = smtp_config()
    return {k: cfg[k] for k in ("configured", "problems", "host", "port", "security", "fromEmail")}


def _fill(text, recipient):
    return (text.replace("{name}", recipient.get("name") or "")
                .replace("{company}", recipient.get("company") or ""))


def build_message(email_settings, ranges, recipient, from_email):
    """EmailMessage for one recipient, plain text + HTML."""
    subject = _fill(email_settings["subject"], recipient)
    intro = _fill(email_settings["intro"], recipient)
    closing = _fill(email_settings["closing"], recipient)
    greeting = f"Dear {recipient['name']},"

    by_room = group_by_room(ranges)
    lines = [greeting, "", intro, "", "STOP SALE - all static rates", ""]
    for item in by_room:
        lines.append(f"{item['room']}:")
        lines += [f"  - {format_range(r['start'], r['end'])}" for r in item["ranges"]]
    lines += ["", closing]
    text = "\n".join(lines)

    def paragraphs(block):
        return "".join(
            f'<p style="margin:0 0 12px">{html.escape(p).replace(chr(10), "<br>")}</p>'
            for p in block.split("\n\n") if p.strip())

    cell = "padding:8px 12px;border:1px solid #d6d3d1;text-align:left;vertical-align:top"
    rows = "".join(
        f'<tr><td style="{cell}{";font-weight:bold" if item["room"] == ALL_ROOMS_LABEL else ""}">{html.escape(item["room"])}</td>'
        f'<td style="{cell};white-space:nowrap">'
        f'{"<br>".join(html.escape(format_range(r["start"], r["end"])) for r in item["ranges"])}</td></tr>'
        for item in by_room)
    body = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:#1c1917">'
        f'<p style="margin:0 0 12px">{html.escape(greeting)}</p>'
        f"{paragraphs(intro)}"
        '<p style="margin:16px 0 8px;font-weight:bold;color:#b91c1c">STOP SALE &ndash; all static rates</p>'
        '<table style="border-collapse:collapse;margin:0 0 16px">'
        f'<thead><tr style="background:#f5f5f4"><th style="{cell}">Room type</th><th style="{cell}">Stop sale dates</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
        f"{paragraphs(closing)}"
        "</div>"
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((email_settings["fromName"], from_email))
    msg["To"] = formataddr((recipient["name"], recipient["email"]))
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=from_email.split("@")[-1])
    msg.set_content(text)
    msg.add_alternative(f"<!doctype html><html><body>{body}</body></html>", subtype="html")
    return msg


def _open_smtp(cfg):
    context = ssl.create_default_context()
    if cfg["security"] == "ssl":
        server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=SMTP_TIMEOUT, context=context)
    else:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=SMTP_TIMEOUT)
        if cfg["security"] == "starttls":
            server.starttls(context=context)
    if cfg["username"]:
        server.login(cfg["username"], os.environ.get("SMTP_PASSWORD", ""))
    return server


def _quit(server):
    if server is None:
        return
    try:
        server.quit()
    except (smtplib.SMTPException, OSError):
        pass


def send_individually(email_settings, ranges, recipients, on_result=None, throttle=None, wait=None):
    """Sends one email per recipient. Returns [{"id", "name", "email",
    "company", "ok", "error"}]; on_result, if given, is called with each
    result as it happens (for progress).

    throttle: {"delaySeconds": wait between emails, "batchSize": pause after
    every N emails (0 = never), "batchPauseMinutes": length of that pause}.
    wait(seconds) does the waiting and returns True to stop the send early
    (default: plain sleep, never stops). The connection is closed during long
    waits (servers drop idle connections) and reopened for the next email."""
    cfg = smtp_config()
    if not cfg["configured"]:
        raise SmtpNotConfigured("; ".join(cfg["problems"]))
    throttle = throttle or {}
    delay = max(0, throttle.get("delaySeconds") or 0)
    batch_size = max(0, throttle.get("batchSize") or 0)
    batch_pause = max(0, throttle.get("batchPauseMinutes") or 0) * 60
    wait = wait or (lambda seconds: time.sleep(seconds) or False)

    results = []
    server = _open_smtp(cfg)
    try:
        for index, recipient in enumerate(recipients):
            if index:
                pause = batch_pause if batch_size and index % batch_size == 0 else delay
                if pause >= IDLE_RECONNECT_SECONDS:
                    _quit(server)
                    server = None
                if wait(pause):  # also called with 0, so Stop works unthrottled
                    break
            result = {k: recipient.get(k) for k in ("id", "name", "email", "company")}
            message = build_message(email_settings, ranges, recipient, cfg["fromEmail"])
            for attempt in (1, 2):
                try:
                    if server is None:
                        server = _open_smtp(cfg)
                    server.send_message(message)
                    result.update(ok=True, error=None)
                    break
                except smtplib.SMTPServerDisconnected as exc:
                    # Dropped connection: reconnect and retry this email once.
                    server = None
                    result.update(ok=False, error=str(exc)[:300] or "Mail server disconnected")
                except (smtplib.SMTPException, OSError) as exc:
                    result.update(ok=False, error=str(exc)[:300])
                    break
            results.append(result)
            if on_result:
                on_result(result)
    finally:
        _quit(server)
    return results
