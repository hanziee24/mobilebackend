import logging
import smtplib
import socket
import ssl
from email.message import EmailMessage
from typing import Iterable

from django.conf import settings
from django.core.mail import send_mail


logger = logging.getLogger(__name__)

BREVO_FALLBACK_PORTS = (2525, 587, 465)


def _mask_value(value: str) -> str:
    raw = (value or '').strip()
    if not raw:
        return ''
    if '@' in raw:
        name, domain = raw.split('@', 1)
        if len(name) <= 2:
            return f'{name[0]}***@{domain}' if name else f'***@{domain}'
        return f'{name[:2]}***@{domain}'
    if len(raw) <= 4:
        return '****'
    return f'{raw[:2]}***{raw[-2:]}'


def get_system_from_email() -> str:
    configured = (getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '').strip()
    if configured:
        return configured
    support_email = (getattr(settings, 'SUPPORT_TICKET_EMAIL', '') or '').strip()
    if support_email:
        return support_email
    return 'no-reply@deliverytrack.local'


def build_email_diagnostics() -> dict:
    email_host = (getattr(settings, 'EMAIL_HOST', '') or '').strip()
    default_from_email = get_system_from_email()
    support_ticket_email = (getattr(settings, 'SUPPORT_TICKET_EMAIL', '') or '').strip()
    email_host_user = (getattr(settings, 'EMAIL_HOST_USER', '') or '').strip()

    warnings = []
    if not email_host_user:
        warnings.append('EMAIL_HOST_USER is empty.')
    if not (getattr(settings, 'EMAIL_HOST_PASSWORD', '') or '').strip():
        warnings.append('EMAIL_HOST_PASSWORD is empty.')
    if 'brevo' in email_host.lower() and default_from_email.lower().endswith('@gmail.com'):
        warnings.append('Brevo may reject Gmail sender addresses unless that exact sender is verified in Brevo.')
    if default_from_email.lower().endswith('@smtp-brevo.com'):
        warnings.append('DEFAULT_FROM_EMAIL looks like an SMTP login, not a sender inbox.')

    return {
        'backend': getattr(settings, 'EMAIL_BACKEND', ''),
        'host': email_host,
        'port': getattr(settings, 'EMAIL_PORT', ''),
        'use_tls': getattr(settings, 'EMAIL_USE_TLS', False),
        'use_ssl': getattr(settings, 'EMAIL_USE_SSL', False),
        'timeout': getattr(settings, 'EMAIL_TIMEOUT', None),
        'from_email': default_from_email,
        'support_ticket_email': support_ticket_email,
        'host_user_masked': _mask_value(email_host_user),
        'warnings': warnings,
    }


def _uses_brevo_smtp() -> bool:
    backend = (getattr(settings, 'EMAIL_BACKEND', '') or '').lower()
    host = (getattr(settings, 'EMAIL_HOST', '') or '').lower()
    return 'smtp' in backend and 'brevo' in host


def _is_timeout_error(exc: Exception) -> bool:
    return isinstance(exc, (TimeoutError, socket.timeout)) or 'timed out' in str(exc).lower()


def _smtp_timeout() -> int:
    timeout = getattr(settings, 'EMAIL_TIMEOUT', 30)
    try:
        return max(5, int(timeout))
    except (TypeError, ValueError):
        return 30


def _brevo_candidate_ports() -> list[int]:
    candidates = []
    try:
        configured_port = int(getattr(settings, 'EMAIL_PORT', 587))
        candidates.append(configured_port)
    except (TypeError, ValueError):
        configured_port = None

    for port in BREVO_FALLBACK_PORTS:
        if port not in candidates:
            candidates.append(port)
    return candidates


def _send_via_smtp_port(subject: str, message: str, recipients: list[str], port: int) -> int:
    host = (getattr(settings, 'EMAIL_HOST', '') or '').strip()
    username = (getattr(settings, 'EMAIL_HOST_USER', '') or '').strip()
    password = (getattr(settings, 'EMAIL_HOST_PASSWORD', '') or '').strip()
    from_email = get_system_from_email()

    email = EmailMessage()
    email['Subject'] = subject
    email['From'] = from_email
    email['To'] = ', '.join(recipients)
    email.set_content(message)

    timeout = _smtp_timeout()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context()) as server:
            if username:
                server.login(username, password)
            server.send_message(email)
            return 1

    with smtplib.SMTP(host, port, timeout=timeout) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        if username:
            server.login(username, password)
        server.send_message(email)
        return 1


def _retry_brevo_send_after_timeout(subject: str, message: str, recipients: list[str], original_exc: Exception) -> int:
    last_exc = original_exc
    configured_port = getattr(settings, 'EMAIL_PORT', None)

    for port in _brevo_candidate_ports():
        if str(port) == str(configured_port):
            continue
        try:
            result = _send_via_smtp_port(subject, message, recipients, port)
            logger.warning(
                'Recovered Brevo email delivery after timeout by retrying SMTP port %s.',
                port,
            )
            return result
        except Exception as exc:
            last_exc = exc
            logger.warning(
                'Brevo retry on SMTP port %s failed: %s',
                port,
                exc,
            )

    raise last_exc


def send_system_email(
    subject: str,
    message: str,
    recipient_list: Iterable[str],
    *,
    fail_silently: bool = False,
) -> int:
    recipients = list(recipient_list)
    try:
        return send_mail(
            subject,
            message,
            get_system_from_email(),
            recipients,
            fail_silently=fail_silently,
        )
    except Exception as exc:
        if _uses_brevo_smtp() and _is_timeout_error(exc):
            try:
                return _retry_brevo_send_after_timeout(subject, message, recipients, exc)
            except Exception as retry_exc:
                exc = retry_exc

        diagnostics = build_email_diagnostics()
        logger.exception(
            'Email delivery failed. host=%s port=%s tls=%s ssl=%s timeout=%s from_email=%s host_user=%s recipients=%s warnings=%s',
            diagnostics['host'],
            diagnostics['port'],
            diagnostics['use_tls'],
            diagnostics['use_ssl'],
            diagnostics['timeout'],
            diagnostics['from_email'],
            diagnostics['host_user_masked'],
            len(recipients),
            '; '.join(diagnostics['warnings']) or 'none',
        )
        if fail_silently:
            return 0
        raise exc
