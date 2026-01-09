# Alert MTL - Product Requirements Document

## Executive Summary

Alert MTL is a web application that provides Montreal residents with real-time snow removal status notifications and waste collection reminders. The application leverages Montreal's open data APIs to alert users before parking restrictions take effect, helping them avoid tickets and towing during snow removal operations.

## Research Summary: Montreal vs Quebec City

### Key Differences

| Feature | Quebec City | Montreal |
|---------|-------------|----------|
| **Snow Removal API** | REST API with direct lat/lon lookup | SOAP-based API requiring COTE_RUE_ID |
| **Authentication** | None required | None required (as of 2024) |
| **Street Lookup** | Direct coordinates | Requires Geobase Double dataset |
| **Rate Limiting** | None documented | 1 request per 5 minutes |
| **Status Codes** | Binary (active/inactive) | Multi-state (enneige, planifie, en_cours, deneige, replanifie) |
| **Waste Data** | Web scraping required | GEOJSON open data available |

### Montreal Data Sources

#### 1. Snow Removal (Planif-Neige)
- **Production Endpoint**: `https://servicesenligne2.ville.montreal.qc.ca/api/infoneige/`
- **WSDL**: `https://servicesenligne2.ville.montreal.qc.ca/api/infoneige/InfoneigeWebService?WSDL`
- **Methods**:
  - `GetPlanificationsForDate` - Get all planned operations for a date
  - `GetPlanificationInfosForDate` - Get detailed planning info
- **Rate Limit**: Maximum 1 request per 5 minutes (300 seconds)

#### 2. Geobase Double (Address to COTE_RUE_ID Mapping)
- **Source**: `https://donnees.montreal.ca/dataset/geobase-double`
- **Formats**: JSON (74.7MB), CSV (5.3MB), ZIP (11.6MB)
- **Key Fields**:
  - `COTE_RUE_ID` - Primary key for snow removal lookup
  - `NOM_VOIE` - Street name
  - `DEBUT_ADRESSE` / `FIN_ADRESSE` - Address range
  - `COTE` - Side of street ("Droit"/"Gauche")
  - `NOM_VILLE` - Municipality name

#### 3. Waste Collection (Info-Collections)
- **Source**: `https://donnees.montreal.ca/dataset/2df0fa28-7a7b-46c6-912f-93b215bd201e`
- **Format**: GEOJSON
- **Categories**:
  - Garbage collection (ordures-menageres)
  - Recyclable materials (matieres-recyclables)
  - Food waste (residus-alimentaires)
  - Organic materials
  - Green waste / dead leaves
  - Construction/renovation/demolition (CRD) and bulky items
- **Update Frequency**: Monthly (internal updates ad hoc by district)

### Montreal Snow Removal Status Codes

| Status | French | Color | Meaning | Action Required |
|--------|--------|-------|---------|-----------------|
| `enneige` | Enneigé | Blue | Street is snowy | Monitor for changes |
| `planifie` | Planifié | Orange | Removal scheduled | Move vehicle soon |
| `en_cours` | En cours | Purple/Mauve | Removal in progress | Vehicle should be moved |
| `deneige` | Déneigé | Green | Snow cleared | Parking allowed |
| `replanifie` | Replanifié | Orange | Rescheduled | Check new schedule |
| N/A | Interdit | Red | Parking prohibited | DO NOT PARK |
| N/A | Bientôt interdit | Yellow | Soon prohibited | Move vehicle NOW |

---

## Functional Requirements

### FR-1: User Registration & Authentication
- **FR-1.1**: Users can register with email address
- **FR-1.2**: Users can subscribe to alerts for specific addresses
- **FR-1.3**: Users can manage multiple addresses (home, work, etc.)
- **FR-1.4**: Unsubscribe functionality via email link

### FR-2: Address Management
- **FR-2.1**: Address input with autocomplete from Geobase Double
- **FR-2.2**: Address validation against Montreal boundaries
- **FR-2.3**: Automatic COTE_RUE_ID resolution from address
- **FR-2.4**: Support for both sides of street (left/right)
- **FR-2.5**: Manual COTE_RUE_ID entry for edge cases

### FR-3: Snow Removal Alerts
- **FR-3.1**: Real-time status monitoring via Planif-Neige API
- **FR-3.2**: Email alert when status changes to `planifie` (scheduled)
- **FR-3.3**: Urgent email alert when status changes to `en_cours` (in progress)
- **FR-3.4**: Alert when parking prohibition starts (red status)
- **FR-3.5**: Confirmation email when street is cleared (`deneige`)

### FR-4: Waste Collection Alerts
- **FR-4.1**: Parse GEOJSON waste collection schedules
- **FR-4.2**: Match user address to collection sector
- **FR-4.3**: Send reminder email day before collection
- **FR-4.4**: Support all collection types (garbage, recycling, organic, etc.)
- **FR-4.5**: Handle special collection schedules (holidays)

### FR-5: Quick Check Interface
- **FR-5.1**: Web interface for instant status lookup
- **FR-5.2**: Display current snow removal status with color coding
- **FR-5.3**: Show next scheduled operations
- **FR-5.4**: Display parking restriction times if applicable
- **FR-5.5**: Mobile-responsive design

### FR-6: Geolocation Feature
- **FR-6.1**: Browser geolocation API integration
- **FR-6.2**: Reverse geocoding to Montreal address
- **FR-6.3**: Automatic COTE_RUE_ID lookup from coordinates
- **FR-6.4**: Fallback to manual address entry
- **FR-6.5**: Postal code lookup as alternative

---

## Technical Architecture

### Backend Stack
- **Framework**: Python Flask
- **Database**: SQLite (development) / PostgreSQL (production)
- **Task Scheduler**: APScheduler
- **SOAP Client**: zeep (for Planif-Neige WSDL)
- **Email Service**: Resend API
- **Hosting**: Render.com

### External Integrations
1. **Planif-Neige API** - Snow removal status (SOAP/WSDL)
2. **Geobase Double** - Address/street data (JSON download)
3. **Info-Collections** - Waste schedules (GEOJSON)
4. **Nominatim/OpenStreetMap** - Reverse geocoding
5. **Resend** - Transactional emails

### Data Flow
```
User Address → Geobase Double Lookup → COTE_RUE_ID
     ↓
COTE_RUE_ID → Planif-Neige API → Snow Status
     ↓
Status Change Detected → Resend Email → User Inbox
```

### Caching Strategy
- **Geobase Double**: Download and cache locally (weekly refresh)
- **Planif-Neige**: Cache responses for 5 minutes (API rate limit)
- **Waste Schedules**: Cache for 24 hours (daily refresh)

---

## Non-Functional Requirements

### NFR-1: Performance
- API response time < 2 seconds
- Email delivery within 1 minute of status change
- Support 1000+ concurrent users

### NFR-2: Reliability
- 99.9% uptime target
- Graceful degradation when external APIs unavailable
- Retry logic for failed API calls

### NFR-3: Security
- HTTPS only
- Email validation for subscriptions
- No sensitive data stored (addresses only)
- Rate limiting on public endpoints

### NFR-4: Compliance
- Respect Montreal Open Data license (CC BY 4.0)
- CASL compliance for email communications
- Unsubscribe mechanism in all emails

---

## User Interface Mockup

### Home Page
```
┌─────────────────────────────────────────────┐
│           ALERT MTL                         │
│     Snow Removal & Waste Collection Alerts  │
├─────────────────────────────────────────────┤
│                                             │
│  [📍 Use My Location]                       │
│                                             │
│  ─── OR ───                                 │
│                                             │
│  [Enter your Montreal address...        ]   │
│                                             │
│  [Check Status]                             │
│                                             │
├─────────────────────────────────────────────┤
│  📧 Get Alerts:                             │
│  [your@email.com                        ]   │
│  [Subscribe]                                │
└─────────────────────────────────────────────┘
```

### Status Display
```
┌─────────────────────────────────────────────┐
│  📍 1234 Rue Saint-Denis                    │
│     Plateau-Mont-Royal                      │
├─────────────────────────────────────────────┤
│                                             │
│  🟡 SNOW REMOVAL SCHEDULED                  │
│     ───────────────────────                 │
│     Status: Planifié                        │
│     Planned: Jan 10, 2026 02:00 - 08:00     │
│     Parking prohibited during operation     │
│                                             │
│  ⚠️  Move your vehicle before 02:00!        │
│                                             │
├─────────────────────────────────────────────┤
│  🗑️ NEXT WASTE COLLECTION                   │
│     ───────────────────────                 │
│     Recycling: Tomorrow (Jan 10)            │
│     Garbage: Friday (Jan 12)                │
│     Organic: Friday (Jan 12)                │
│                                             │
└─────────────────────────────────────────────┘
```

---

## Deployment Architecture

### GitHub Actions Workflow
Due to Render.com free tier limitations (server spins down after 15 min):

1. **Wake-up Job**: 4 minutes before scheduled checks
2. **Snow Check Job**: Poll Planif-Neige API
3. **Waste Check Job**: Check for tomorrow's collections

### Environment Variables
```
RESEND_API_KEY=re_xxxxx
DATABASE_URL=postgresql://...
PLANIF_NEIGE_ENDPOINT=https://servicesenligne2.ville.montreal.qc.ca/api/infoneige/
GEOBASE_URL=https://donnees.montreal.ca/dataset/geobase-double
```

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| API rate limiting (5 min) | High | Medium | Batch queries, aggressive caching |
| Geobase data changes | Medium | High | Weekly sync, validation checks |
| SOAP API deprecation | Low | High | Monitor for REST alternatives |
| Email deliverability | Medium | High | Use Resend, monitor bounce rates |
| Free tier limitations | High | Medium | GitHub Actions for scheduling |

---

## Success Metrics

1. **User Engagement**: Number of active subscriptions
2. **Alert Accuracy**: % of alerts sent before actual operation
3. **Delivery Rate**: Email delivery success rate > 99%
4. **Response Time**: Average status check < 2 seconds
5. **User Satisfaction**: Feedback and reviews

---

## Out of Scope (v1.0)

- Push notifications (future consideration)
- SMS alerts (future consideration)
- Multiple language support (French only initially)
- Historical data analytics
- Integration with parking apps

---

## Appendix: API Response Examples

### Planif-Neige Status Response
```json
{
  "cote_rue_id": 13811012,
  "etat": "planifie",
  "date_debut": "2026-01-10T02:00:00",
  "date_fin": "2026-01-10T08:00:00",
  "date_maj": "2026-01-09T18:00:00"
}
```

### Geobase Double Entry
```json
{
  "COTE_RUE_ID": 13811012,
  "ID_TRC": 1234567,
  "NOM_VOIE": "Saint-Denis",
  "TYPE_F": "Rue",
  "DEBUT_ADRESSE": 1200,
  "FIN_ADRESSE": 1300,
  "COTE": "Droit",
  "NOM_VILLE": "Montréal"
}
```

---

*Document Version: 1.0*
*Last Updated: January 9, 2026*
