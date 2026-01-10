# Alert Quebec - Unified Snow & Waste Alert System

## Product Requirements Document (PRD)

### Version 2.0 | January 2025

---

## 1. Executive Summary

Alert Quebec is a unified web application that provides snow removal and waste collection alerts for residents of Quebec's major cities. The application merges two existing projects (Alert MTL for Montreal and Snow Alert for Quebec City) into a single, cohesive platform with a modern Apple-like design.

### Key Features
- **City Toggle**: Switch between Montreal and Quebec City with visual icons
- **Snow Removal Alerts**: Real-time notifications when snow operations are scheduled
- **Waste Collection Reminders**: Day-before reminders for garbage and recycling
- **Postal Code Lookup**: Simple input - just enter your postal code
- **Email Subscriptions**: Get automatic alerts delivered to your inbox

---

## 2. Problem Statement

Currently, two separate applications exist for snow and waste alerts:
1. **Alert MTL** - Serves Montreal residents (H postal codes)
2. **Snow Alert** - Serves Quebec City residents (G postal codes)

This fragmentation leads to:
- Duplicate infrastructure and maintenance costs
- Inconsistent user experiences
- Separate codebases to maintain
- Inability to scale to additional cities easily

---

## 3. Solution Overview

### 3.1 Unified Platform
Merge both applications into a single Flask application with:
- Shared infrastructure (database, email service, hosting)
- City-specific service modules
- Unified UI with city toggle
- Single deployment on Render

### 3.2 Architecture

```
alert-quebec/
├── app/
│   ├── __init__.py           # Flask app factory
│   ├── models.py             # Unified database models
│   ├── routes.py             # API routes with city context
│   ├── scheduler.py          # Background jobs for both cities
│   ├── services/
│   │   ├── montreal/
│   │   │   ├── planif_neige.py   # Montreal SOAP API
│   │   │   ├── geobase.py        # Geobase Double lookup
│   │   │   └── waste.py          # Montreal waste GEOJSON
│   │   ├── quebec/
│   │   │   ├── snow_checker.py   # Quebec ArcGIS API
│   │   │   └── waste.py          # Quebec waste zones
│   │   └── email.py              # Shared email service
│   └── templates/
│       ├── index.html            # Unified UI with city toggle
│       ├── email/                # Email templates
│       └── unsubscribe.html
├── tests/
├── config.py
├── requirements.txt
└── render.yaml
```

---

## 4. User Interface Design

### 4.1 City Toggle Component

The city toggle is the primary UI element for switching between cities:

```
┌─────────────────────────────────────────┐
│                                         │
│     🏙️              🏰                 │
│   Montreal      Quebec City             │
│                                         │
│   ┌─────────────────────────────────┐   │
│   │ ●━━━━━━━━━━━━━━━    ○          │   │
│   └─────────────────────────────────┘   │
│                                         │
└─────────────────────────────────────────┘
```

**Design Requirements:**
- Apple-like toggle switch (iOS style)
- City icons above toggle (Montreal skyline emoji 🏙️, Quebec château emoji 🏰)
- Montreal is default (left position)
- Quebec City when toggled (right position)
- Smooth animation on toggle (0.3s ease)
- Selected city icon slightly enlarged (1.1x scale) with higher opacity
- Non-selected city icon dimmed (0.5 opacity)
- Toggle persists in localStorage
- City name labels under each icon

### 4.2 Color Scheme

| Element | Montreal | Quebec City |
|---------|----------|-------------|
| Primary | #0071e3 (Blue) | #5856d6 (Purple) |
| Accent | #34c759 (Green) | #ff9500 (Orange) |
| Snow | #5ac8fa (Light Blue) | #5ac8fa (Light Blue) |
| Toggle Track (selected) | #0071e3 | #5856d6 |

### 4.3 Layout Structure

```
┌────────────────────────────────────────────┐
│                  HEADER                     │
│              Alert Quebec                   │
│                                            │
│     🏙️              🏰                    │
│   Montreal      Quebec City                │
│   ●━━━━━━━━━━━━━━━━━━━━○                  │
│                                            │
├────────────────────────────────────────────┤
│                                            │
│             QUICK CHECK CARD               │
│  ┌────────────────────────────────────┐   │
│  │  Postal Code: [H2V 1V5] [Check]   │   │
│  │         - or -                     │   │
│  │    [📍 Use My Location]            │   │
│  └────────────────────────────────────┘   │
│                                            │
│              RESULTS CARD                  │
│  ┌────────────────────────────────────┐   │
│  │  ❄️ Snow: No operation scheduled   │   │
│  │  🗑️ Garbage: Tomorrow              │   │
│  │  ♻️ Recycling: This week           │   │
│  └────────────────────────────────────┘   │
│                                            │
│            SUBSCRIBE CARD                  │
│  ┌────────────────────────────────────┐   │
│  │  Postal Code: [        ]           │   │
│  │  Email: [                  ]       │   │
│  │  [✓] Snow  [✓] Garbage  [ ] Recycle│   │
│  │  [Subscribe to Alerts]             │   │
│  └────────────────────────────────────┘   │
│                                            │
├────────────────────────────────────────────┤
│                  FOOTER                     │
│     Data from Ville de Montréal /          │
│           Ville de Québec                  │
└────────────────────────────────────────────┘
```

### 4.4 Responsive Behavior

- **Desktop (>768px)**: Full layout, icons side by side
- **Mobile (<768px)**: Stacked cards, touch-friendly toggle

---

## 5. Data Models

### 5.1 Subscriber Model (Unified)

```python
class Subscriber(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    city = db.Column(db.String(20), nullable=False)  # 'montreal' or 'quebec'
    postal_code = db.Column(db.String(10), nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    # Alert preferences
    snow_alerts = db.Column(db.Boolean, default=True)
    waste_alerts = db.Column(db.Boolean, default=False)

    # Metadata
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    unsubscribe_token = db.Column(db.String(36), unique=True)

    # Montreal-specific
    cote_rue_id = db.Column(db.Integer)

    # Quebec-specific
    waste_zone_id = db.Column(db.Integer)
```

### 5.2 Alert History Model

```python
class AlertHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('subscribers.id'))
    city = db.Column(db.String(20), nullable=False)
    alert_type = db.Column(db.String(50))  # 'snow', 'garbage', 'recycling'
    reference_date = db.Column(db.Date)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### 5.3 Quebec Waste Zone Model

```python
class WasteZone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    zone_code = db.Column(db.String(10), unique=True)
    garbage_day = db.Column(db.String(10))  # 'monday', 'tuesday', etc.
    recycling_week = db.Column(db.String(10))  # 'odd' or 'even'
```

---

## 6. API Endpoints

### 6.1 Quick Check

```
GET /api/quick-check/{postal_code}
```
Automatically detects city from postal code prefix (H=Montreal, G=Quebec)

**Response:**
```json
{
  "city": "montreal",
  "postal_code": "H2V 1V5",
  "snow_status": {
    "active": false,
    "message": "No operation scheduled"
  },
  "waste_schedule": {
    "garbage": {"next": "2025-01-10", "day": "Friday"},
    "recycling": {"next": "2025-01-15", "week": "odd"}
  }
}
```

### 6.2 Subscribe

```
POST /api/subscribe
Content-Type: application/json

{
  "email": "user@example.com",
  "postal_code": "H2V 1V5",
  "snow_alerts": true,
  "waste_alerts": true
}
```
City is auto-detected from postal code.

### 6.3 Unsubscribe

```
GET /unsubscribe/{token}
POST /api/unsubscribe
```

### 6.4 City-Specific Endpoints (Internal)

```
GET /api/montreal/snow-status/{postal_code}
GET /api/quebec/snow-status/{postal_code}
GET /api/montreal/waste-schedule?lat={lat}&lon={lon}
GET /api/quebec/waste-schedule?zone={zone_code}
```

---

## 7. City-Specific Implementations

### 7.1 Montreal

| Feature | Implementation |
|---------|----------------|
| Snow Status | Planif-Neige SOAP API via zeep |
| Geocoding | FSA lookup table + Nominatim fallback |
| Waste Schedule | GEOJSON sector lookup by coordinates |
| Postal Codes | H prefix (H1A-H9X) |

### 7.2 Quebec City

| Feature | Implementation |
|---------|----------------|
| Snow Status | ArcGIS REST API (flashing lights) |
| Geocoding | ArcGIS World Geocoder |
| Waste Schedule | Zone-based (garbage day + recycling week) |
| Postal Codes | G prefix (G1A-G3N) |

---

## 8. Background Jobs

### 8.1 Scheduler Configuration

| Job ID | City | Schedule | Description |
|--------|------|----------|-------------|
| `snow_check_montreal` | Montreal | */10 * * * * | Check Planif-Neige API |
| `snow_check_quebec` | Quebec | */10 * * * * | Check ArcGIS flashing lights |
| `waste_reminder_both` | Both | 0 18 * * * | Send waste reminders (6 PM) |
| `geobase_refresh` | Montreal | 0 3 * * 0 | Refresh Geobase cache (Sun 3 AM) |

### 8.2 GitHub Actions Triggers

```yaml
schedule:
  - cron: '56 20 * * *'  # Wake up 4min before
  - cron: '0 21 * * *'   # Snow check trigger
  - cron: '56 22 * * *'  # Wake up 4min before
  - cron: '0 23 * * *'   # Waste check trigger
```

---

## 9. Email Templates

### 9.1 Snow Alert (Shared Template)

```html
Subject: ❄️ Snow Removal Alert - {{city_name}}

{{city_icon}} {{city_name}} Snow Alert

Your area ({{postal_code}}) has snow removal {{status}}:
{{details}}

{{#if is_montreal}}
Status: {{status_french}} ({{status_english}})
{{/if}}

{{#if is_quebec}}
Flashing lights detected: {{light_count}} active
Nearest: {{nearest_street}} ({{distance}}m)
{{/if}}

[Unsubscribe]({{unsubscribe_url}})
```

### 9.2 Waste Reminder (Shared Template)

```html
Subject: 🗑️ {{waste_type}} Collection Tomorrow - {{city_name}}

Tomorrow is {{waste_type}} collection day in your area ({{postal_code}}).

Please put out your {{waste_type}} bin before 7 AM.

[Unsubscribe]({{unsubscribe_url}})
```

---

## 10. Deployment

### 10.1 Environment Variables

```bash
# Database
DATABASE_URL=postgresql://...

# Email
RESEND_API_KEY=re_...

# App
SECRET_KEY=...
ADMIN_TOKEN=...
APP_URL=https://alert-quebec.onrender.com

# Feature flags
ENABLE_SCHEDULER=true
ENABLE_MONTREAL=true
ENABLE_QUEBEC=true
```

### 10.2 Render Configuration

```yaml
services:
  - type: web
    name: alert-quebec
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn "app:create_app()"
    envVars:
      - key: FLASK_ENV
        value: production

databases:
  - name: alert-quebec-db
    plan: free
```

---

## 11. Testing Strategy

### 11.1 Test Categories

| Category | Scope | Tools |
|----------|-------|-------|
| Unit Tests | Services, Models | pytest |
| Integration Tests | API endpoints | pytest-flask |
| UI Tests | Frontend JS | Jest (optional) |
| E2E Tests | Full flows | pytest + requests |

### 11.2 Test Coverage Requirements

- Models: 100%
- Services: 90%
- Routes: 90%
- City toggle: Manual verification

---

## 12. Migration Plan

### 12.1 Phase 1: Code Merge
1. Create unified project structure
2. Merge models with city field
3. Merge services into city subfolders
4. Create unified UI with toggle

### 12.2 Phase 2: Data Migration
1. Export Montreal subscribers
2. Export Quebec subscribers
3. Merge into unified table with city field
4. Handle email conflicts (ask user to choose city)

### 12.3 Phase 3: Cutover
1. Deploy to alert-quebec.onrender.com
2. Update DNS
3. Redirect old URLs
4. Decommission old apps

---

## 13. Additional Suggestions

### 13.1 Implemented in This PRD
1. **Auto-detect city from postal code** - No need to manually select
2. **Unified unsubscribe** - One token works for both cities
3. **Shared email service** - Single Resend account
4. **City-specific theming** - Colors change based on selected city

### 13.2 Future Enhancements (Out of Scope)
1. **Push notifications** - Web push API
2. **SMS alerts** - Twilio integration
3. **Multi-language** - FR/EN toggle
4. **Additional cities** - Laval, Longueuil, Gatineau
5. **Mobile app** - React Native wrapper
6. **Historical data** - Past snow operations
7. **Community features** - User-reported status

---

## 14. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Page Load | < 2s | Lighthouse |
| API Response | < 500ms | Server logs |
| Email Delivery | > 98% | Resend dashboard |
| Uptime | > 99.5% | Render monitoring |
| User Growth | 10%/month | Database count |

---

## 15. Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| API rate limiting | Medium | High | Aggressive caching |
| Geocoding failures | Medium | Medium | Multiple fallback services |
| Email spam filters | Low | High | Authenticated domain, SPF/DKIM |
| Database limits | Medium | Medium | Cleanup old alert history |
| City API changes | Low | High | Version detection, alerts |

---

## Appendix A: Postal Code Detection

```python
def detect_city(postal_code: str) -> str:
    """Detect city from postal code prefix."""
    prefix = postal_code.upper().strip()[0]
    if prefix == 'H':
        return 'montreal'
    elif prefix == 'G':
        return 'quebec'
    else:
        raise ValueError(f"Unsupported postal code: {postal_code}")
```

---

## Appendix B: City Icons

**Montreal:** 🏙️ (Cityscape emoji)
- Represents modern downtown skyline
- Easily recognizable

**Quebec City:** 🏰 (Castle emoji)
- Represents Château Frontenac
- Historic European feel

---

*Document Version: 2.0*
*Last Updated: January 2025*
*Project: Alert Quebec (Unified)*
