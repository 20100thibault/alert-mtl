"""
Email Service using Resend

Handles sending alert emails via the Resend API.
Supports both Montreal and Quebec City.
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


def get_sender_name(city: str = 'montreal') -> str:
    """Get sender name based on city."""
    if city == 'quebec':
        return 'Alert Quebec'
    return 'Alert Quebec'  # Unified branding


def send_email(
    to: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    city: str = 'montreal',
    retry_count: int = 0
) -> Dict[str, Any]:
    """
    Send an email via Resend.

    Args:
        to: Recipient email address
        subject: Email subject
        html_content: HTML body
        text_content: Plain text body (optional)
        city: City for sender branding
        retry_count: Current retry attempt

    Returns:
        Dict with success status and message ID or error
    """
    try:
        resend = get_resend_client()
        sender = current_app.config.get('SENDER_EMAIL', 'alerts@alertquebec.com')
        sender_name = get_sender_name(city)

        params = {
            "from": f"{sender_name} <{sender}>",
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
            return send_email(to, subject, html_content, text_content, city, retry_count + 1)

        return {
            'success': False,
            'error': str(e),
            'to': to
        }


def send_confirmation_email(subscriber, address) -> Dict[str, Any]:
    """Send subscription confirmation email."""
    app_url = current_app.config.get('APP_URL', 'http://localhost:5000')
    unsubscribe_url = f"{app_url}/unsubscribe/{subscriber.unsubscribe_token}"

    city = getattr(address, 'city', 'montreal') or 'montreal'
    city_display = 'Montreal' if city == 'montreal' else 'Quebec City'
    language = getattr(subscriber, 'language', 'en') or 'en'

    html_content = render_template(
        'email/confirmation.html',
        address=address.full_address(),
        city=city,
        city_display=city_display,
        unsubscribe_url=unsubscribe_url,
        language=language
    )

    if language == 'fr':
        subject = f"Bienvenue à Alerte Québec - Abonnement confirmé"
    else:
        subject = f"Welcome to Alert Quebec - {city_display} Subscription Confirmed"

    return send_email(
        to=subscriber.email,
        subject=subject,
        html_content=html_content,
        city=city
    )


def send_snow_scheduled_alert(subscriber, address, status_data: Dict) -> Dict[str, Any]:
    """Send alert when snow removal is scheduled (Montreal)."""
    app_url = current_app.config.get('APP_URL', 'http://localhost:5000')
    unsubscribe_url = f"{app_url}/unsubscribe/{subscriber.unsubscribe_token}"
    language = getattr(subscriber, 'language', 'en') or 'en'

    html_content = render_template(
        'email/snow_scheduled.html',
        address=address.full_address(),
        city='montreal',
        city_display='Montreal',
        status=status_data,
        unsubscribe_url=unsubscribe_url,
        language=language
    )

    if language == 'fr':
        subject = f"Déneigement prévu - {address.full_address()}"
    else:
        subject = f"Snow Removal Scheduled - {address.full_address()}"

    return send_email(
        to=subscriber.email,
        subject=subject,
        html_content=html_content,
        city='montreal'
    )


def send_snow_urgent_alert(subscriber, address, status_data: Dict) -> Dict[str, Any]:
    """Send urgent alert when snow removal is in progress (Montreal)."""
    app_url = current_app.config.get('APP_URL', 'http://localhost:5000')
    unsubscribe_url = f"{app_url}/unsubscribe/{subscriber.unsubscribe_token}"
    language = getattr(subscriber, 'language', 'en') or 'en'

    html_content = render_template(
        'email/snow_urgent.html',
        address=address.full_address(),
        city='montreal',
        city_display='Montreal',
        status=status_data,
        unsubscribe_url=unsubscribe_url,
        language=language
    )

    if language == 'fr':
        subject = f"URGENT: Déneigement en cours - {address.full_address()}"
    else:
        subject = f"URGENT: Snow Removal In Progress - {address.full_address()}"

    return send_email(
        to=subscriber.email,
        subject=subject,
        html_content=html_content,
        city='montreal'
    )


def send_snow_cleared_alert(subscriber, address) -> Dict[str, Any]:
    """Send confirmation when street is cleared (Montreal)."""
    app_url = current_app.config.get('APP_URL', 'http://localhost:5000')
    unsubscribe_url = f"{app_url}/unsubscribe/{subscriber.unsubscribe_token}"
    language = getattr(subscriber, 'language', 'en') or 'en'

    html_content = render_template(
        'email/snow_cleared.html',
        address=address.full_address(),
        city='montreal',
        city_display='Montreal',
        unsubscribe_url=unsubscribe_url,
        language=language
    )

    if language == 'fr':
        subject = f"Rue déneigée - {address.full_address()}"
    else:
        subject = f"Street Cleared - {address.full_address()}"

    return send_email(
        to=subscriber.email,
        subject=subject,
        html_content=html_content,
        city='montreal'
    )


def send_snow_alert_quebec(subscriber, address, status_data: Dict) -> Dict[str, Any]:
    """Send snow removal alert for Quebec City (flashing lights detected)."""
    app_url = current_app.config.get('APP_URL', 'http://localhost:5000')
    unsubscribe_url = f"{app_url}/unsubscribe/{subscriber.unsubscribe_token}"
    language = getattr(subscriber, 'language', 'en') or 'en'

    lights_nearby = status_data.get('lights_nearby', 0)
    lights = status_data.get('lights', [])
    nearest_light = lights[0] if lights else {}

    html_content = render_template(
        'email/snow_quebec.html',
        address=address.full_address(),
        postal_code=address.postal_code,
        city='quebec',
        city_display='Quebec City',
        lights_nearby=lights_nearby,
        nearest_street=nearest_light.get('street', 'Unknown'),
        nearest_distance=int(nearest_light.get('distance', 0)),
        status=status_data,
        unsubscribe_url=unsubscribe_url,
        language=language
    )

    if language == 'fr':
        subject = f"Alerte Déneigement - {address.postal_code}"
    else:
        subject = f"Snow Removal Alert - {address.postal_code}"

    return send_email(
        to=subscriber.email,
        subject=subject,
        html_content=html_content,
        city='quebec'
    )


def send_waste_reminder(subscriber, address, collections: List[Dict]) -> Dict[str, Any]:
    """Send waste collection reminder (Montreal)."""
    app_url = current_app.config.get('APP_URL', 'http://localhost:5000')
    unsubscribe_url = f"{app_url}/unsubscribe/{subscriber.unsubscribe_token}"
    language = getattr(subscriber, 'language', 'en') or 'en'

    collection_names = ', '.join([c['name'] for c in collections])
    collection_names_fr = ', '.join([c.get('name_fr', c['name']) for c in collections])

    html_content = render_template(
        'email/waste_reminder.html',
        address=address.full_address(),
        city='montreal',
        city_display='Montreal',
        collections=collections,
        unsubscribe_url=unsubscribe_url,
        language=language
    )

    if language == 'fr':
        subject = f"Demain: Collecte {collection_names_fr} - {address.full_address()}"
    else:
        subject = f"Tomorrow: {collection_names} Collection - {address.full_address()}"

    return send_email(
        to=subscriber.email,
        subject=subject,
        html_content=html_content,
        city='montreal'
    )


def send_waste_reminder_quebec(subscriber, address, collection_types: List[str], schedule: Dict) -> Dict[str, Any]:
    """Send waste collection reminder for Quebec City."""
    app_url = current_app.config.get('APP_URL', 'http://localhost:5000')
    unsubscribe_url = f"{app_url}/unsubscribe/{subscriber.unsubscribe_token}"
    language = getattr(subscriber, 'language', 'en') or 'en'

    collection_names = []
    collection_names_fr = []
    if 'garbage' in collection_types:
        collection_names.append('Garbage')
        collection_names_fr.append('Ordures')
    if 'recycling' in collection_types:
        collection_names.append('Recycling')
        collection_names_fr.append('Recyclage')

    collection_display = ' & '.join(collection_names)
    collection_display_fr = ' & '.join(collection_names_fr)

    html_content = render_template(
        'email/waste_reminder_quebec.html',
        address=address.full_address(),
        postal_code=address.postal_code,
        city='quebec',
        city_display='Quebec City',
        collection_types=collection_types,
        collection_display=collection_display,
        collection_display_fr=collection_display_fr,
        schedule=schedule,
        unsubscribe_url=unsubscribe_url,
        language=language
    )

    if language == 'fr':
        subject = f"Demain: Collecte {collection_display_fr} - {address.postal_code}"
    else:
        subject = f"Tomorrow: {collection_display} Collection - {address.postal_code}"

    return send_email(
        to=subscriber.email,
        subject=subject,
        html_content=html_content,
        city='quebec'
    )


def send_batch_emails(emails: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Send multiple emails in batch.

    Args:
        emails: List of email configs, each with 'to', 'subject', 'html_content', optional 'city'

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
            text_content=email_config.get('text_content'),
            city=email_config.get('city', 'montreal')
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
