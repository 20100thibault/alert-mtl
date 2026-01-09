"""
Email Service using Resend

Handles sending alert emails via the Resend API.
"""

import logging
import time
from typing import Optional, Dict, Any, List

from flask import current_app, render_template

logger = logging.getLogger(__name__)

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def get_resend_client():
    """Initialize Resend client."""
    import resend

    api_key = current_app.config.get('RESEND_API_KEY')
    if not api_key:
        raise ValueError("RESEND_API_KEY not configured")

    resend.api_key = api_key
    return resend


def send_email(
    to: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    retry_count: int = 0
) -> Dict[str, Any]:
    """
    Send an email via Resend.

    Args:
        to: Recipient email address
        subject: Email subject
        html_content: HTML body
        text_content: Plain text body (optional)
        retry_count: Current retry attempt

    Returns:
        Dict with success status and message ID or error
    """
    try:
        resend = get_resend_client()
        sender = current_app.config.get('SENDER_EMAIL', 'alerts@alertmtl.com')

        params = {
            "from": f"Alert MTL <{sender}>",
            "to": [to],
            "subject": subject,
            "html": html_content,
        }

        if text_content:
            params["text"] = text_content

        response = resend.Emails.send(params)

        logger.info(f"Email sent to {to}: {response.get('id', 'unknown')}")

        return {
            'success': True,
            'message_id': response.get('id'),
            'to': to
        }

    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")

        # Retry with exponential backoff
        if retry_count < MAX_RETRIES:
            time.sleep(RETRY_DELAY * (2 ** retry_count))
            return send_email(to, subject, html_content, text_content, retry_count + 1)

        return {
            'success': False,
            'error': str(e),
            'to': to
        }


def send_confirmation_email(subscriber, address) -> Dict[str, Any]:
    """Send subscription confirmation email."""
    app_url = current_app.config.get('APP_URL', 'http://localhost:5000')
    unsubscribe_url = f"{app_url}/unsubscribe/{subscriber.unsubscribe_token}"

    html_content = render_template(
        'email/confirmation.html',
        address=address.full_address(),
        unsubscribe_url=unsubscribe_url
    )

    return send_email(
        to=subscriber.email,
        subject="Welcome to Alert MTL - Subscription Confirmed",
        html_content=html_content
    )


def send_snow_scheduled_alert(subscriber, address, status_data: Dict) -> Dict[str, Any]:
    """Send alert when snow removal is scheduled."""
    app_url = current_app.config.get('APP_URL', 'http://localhost:5000')
    unsubscribe_url = f"{app_url}/unsubscribe/{subscriber.unsubscribe_token}"

    html_content = render_template(
        'email/snow_scheduled.html',
        address=address.full_address(),
        status=status_data,
        unsubscribe_url=unsubscribe_url
    )

    return send_email(
        to=subscriber.email,
        subject=f"Snow Removal Scheduled - {address.full_address()}",
        html_content=html_content
    )


def send_snow_urgent_alert(subscriber, address, status_data: Dict) -> Dict[str, Any]:
    """Send urgent alert when snow removal is in progress."""
    app_url = current_app.config.get('APP_URL', 'http://localhost:5000')
    unsubscribe_url = f"{app_url}/unsubscribe/{subscriber.unsubscribe_token}"

    html_content = render_template(
        'email/snow_urgent.html',
        address=address.full_address(),
        status=status_data,
        unsubscribe_url=unsubscribe_url
    )

    return send_email(
        to=subscriber.email,
        subject=f"URGENT: Snow Removal In Progress - {address.full_address()}",
        html_content=html_content
    )


def send_snow_cleared_alert(subscriber, address) -> Dict[str, Any]:
    """Send confirmation when street is cleared."""
    app_url = current_app.config.get('APP_URL', 'http://localhost:5000')
    unsubscribe_url = f"{app_url}/unsubscribe/{subscriber.unsubscribe_token}"

    html_content = render_template(
        'email/snow_cleared.html',
        address=address.full_address(),
        unsubscribe_url=unsubscribe_url
    )

    return send_email(
        to=subscriber.email,
        subject=f"Street Cleared - {address.full_address()}",
        html_content=html_content
    )


def send_waste_reminder(subscriber, address, collections: List[Dict]) -> Dict[str, Any]:
    """Send waste collection reminder."""
    app_url = current_app.config.get('APP_URL', 'http://localhost:5000')
    unsubscribe_url = f"{app_url}/unsubscribe/{subscriber.unsubscribe_token}"

    collection_names = ', '.join([c['name'] for c in collections])

    html_content = render_template(
        'email/waste_reminder.html',
        address=address.full_address(),
        collections=collections,
        unsubscribe_url=unsubscribe_url
    )

    return send_email(
        to=subscriber.email,
        subject=f"Tomorrow: {collection_names} Collection - {address.full_address()}",
        html_content=html_content
    )


def send_batch_emails(emails: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Send multiple emails in batch.

    Args:
        emails: List of email configs, each with 'to', 'subject', 'html_content'

    Returns:
        Summary of sent/failed emails
    """
    results = {
        'sent': 0,
        'failed': 0,
        'errors': []
    }

    for email_config in emails:
        result = send_email(
            to=email_config['to'],
            subject=email_config['subject'],
            html_content=email_config['html_content'],
            text_content=email_config.get('text_content')
        )

        if result['success']:
            results['sent'] += 1
        else:
            results['failed'] += 1
            results['errors'].append({
                'to': email_config['to'],
                'error': result.get('error')
            })

        # Small delay between emails to avoid rate limiting
        time.sleep(0.1)

    return results
