# PRD: Internationalization (i18n) & Geolocation Enhancement

## Overview

Add French language support to Alert Quebec with a language toggle, automatic language detection from browser settings, and automatic city detection from browser geolocation.

---

## 1. Goals

1. **Bilingual Support**: Full English/French UI and email templates
2. **Smart Defaults**: Auto-detect language from browser `navigator.language`
3. **City Geolocation**: Auto-detect Montreal vs Quebec City from browser location
4. **Seamless UX**: Language toggle in top-right corner, persist preference
5. **Accessibility**: Proper `lang` attribute, ARIA labels in both languages

---

## 2. Language Toggle Feature

### 2.1 UI Design

**Location**: Top-right corner of the page, above the city toggle

**Design Pattern**: Pill-style toggle matching city toggle aesthetic
```
┌─────────────────────────────────────────────────────┐
│                                    [EN] [FR]        │  ← Language toggle
│                                                     │
│              🏙️ Montreal  ○───────●  Quebec City 🏰 │  ← City toggle
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Visual States**:
- Active language: Filled background with primary color
- Inactive language: Transparent with border
- Hover: Slight background tint

### 2.2 State Management

```javascript
// Similar pattern to city toggle
let currentLanguage = localStorage.getItem('selectedLanguage') || detectBrowserLanguage();

function detectBrowserLanguage() {
    const browserLang = navigator.language || navigator.userLanguage;
    return browserLang.startsWith('fr') ? 'fr' : 'en';
}
```

### 2.3 Persistence
- Store in `localStorage` as `selectedLanguage`
- Override browser default once user manually selects
- Persist across sessions

---

## 3. Translation Architecture

### 3.1 Frontend Translation Object

Create `translations` object with all UI strings:

```javascript
const translations = {
    en: {
        // Hero
        heroTitle: "Alert Quebec",
        heroDescription: "Get notified about snow removal and waste collection for your address.",

        // Quick Check
        quickCheckTitle: "Quick Check",
        quickCheckSubtitle: "Check today's status without subscribing",
        checkNowBtn: "Check Now",
        orDivider: "or",
        useMyLocation: "Use My Location",
        gettingLocation: "Getting location...",

        // Subscribe
        subscribeTitle: "or subscribe for alerts",
        postalCodeLabel: "Postal Code",
        emailLabel: "Email Address",
        chooseAlerts: "Choose Your Alerts",
        snowAlertTitle: "Snow Removal",
        snowAlertDesc: "Get notified when snow removal is scheduled for your area",
        wasteAlertTitle: "Waste Collection",
        wasteAlertDesc: "Day-before reminder at 6 PM for garbage and recycling",
        subscribeBtn: "Subscribe to Alerts",

        // How it works
        howItWorks: "How it works",
        infoBullet1: "Snow removal alerts are sent when operations are scheduled for your area",
        infoBullet2: "Waste collection reminders are sent the day before at 6:00 PM",
        infoBullet3: "Unsubscribe anytime with one click from any email",

        // Unsubscribe
        alreadySubscribed: "Already subscribed?",
        unsubscribeBtn: "Unsubscribe from All Alerts",

        // Results
        snowRemoval: "Snow Removal",
        garbageCollection: "Garbage Collection",
        recyclingCollection: "Recycling Collection",
        statusActive: "Active",
        statusClear: "Clear",
        wantNotifications: "Want to receive automatic notifications?",
        getNotified: "Get Notified Automatically",

        // Footer
        dataFrom: "Data from",

        // Messages
        successSubscribed: "Successfully subscribed! Check your email for confirmation.",
        errorSelectAlert: "Please select at least one alert type.",
        errorInvalidPostal: "Please enter a valid postal code",
        errorGeolocation: "Geolocation is not supported by your browser",
        errorLocationDenied: "Location access denied. Please enter your postal code instead.",
        errorNetwork: "Network error. Please try again.",
        unsubscribeSuccess: "You have been unsubscribed from all alerts."
    },
    fr: {
        // Hero
        heroTitle: "Alerte Québec",
        heroDescription: "Recevez des notifications pour le déneigement et la collecte des déchets à votre adresse.",

        // Quick Check
        quickCheckTitle: "Vérification Rapide",
        quickCheckSubtitle: "Vérifiez le statut d'aujourd'hui sans vous abonner",
        checkNowBtn: "Vérifier",
        orDivider: "ou",
        useMyLocation: "Utiliser ma position",
        gettingLocation: "Localisation en cours...",

        // Subscribe
        subscribeTitle: "ou abonnez-vous aux alertes",
        postalCodeLabel: "Code Postal",
        emailLabel: "Adresse Courriel",
        chooseAlerts: "Choisissez vos alertes",
        snowAlertTitle: "Déneigement",
        snowAlertDesc: "Soyez avisé lorsque le déneigement est prévu dans votre secteur",
        wasteAlertTitle: "Collecte des Déchets",
        wasteAlertDesc: "Rappel la veille à 18h pour les ordures et le recyclage",
        subscribeBtn: "S'abonner aux alertes",

        // How it works
        howItWorks: "Comment ça fonctionne",
        infoBullet1: "Les alertes de déneigement sont envoyées lorsque des opérations sont prévues dans votre secteur",
        infoBullet2: "Les rappels de collecte sont envoyés la veille à 18h00",
        infoBullet3: "Désabonnez-vous en tout temps en un clic depuis n'importe quel courriel",

        // Unsubscribe
        alreadySubscribed: "Déjà abonné?",
        unsubscribeBtn: "Se désabonner de toutes les alertes",

        // Results
        snowRemoval: "Déneigement",
        garbageCollection: "Collecte des Ordures",
        recyclingCollection: "Collecte du Recyclage",
        statusActive: "En cours",
        statusClear: "Terminé",
        wantNotifications: "Voulez-vous recevoir des notifications automatiques?",
        getNotified: "Recevoir les notifications",

        // Footer
        dataFrom: "Données de",

        // Messages
        successSubscribed: "Inscription réussie! Vérifiez votre courriel pour la confirmation.",
        errorSelectAlert: "Veuillez sélectionner au moins un type d'alerte.",
        errorInvalidPostal: "Veuillez entrer un code postal valide",
        errorGeolocation: "La géolocalisation n'est pas supportée par votre navigateur",
        errorLocationDenied: "Accès à la position refusé. Veuillez entrer votre code postal.",
        errorNetwork: "Erreur réseau. Veuillez réessayer.",
        unsubscribeSuccess: "Vous avez été désabonné de toutes les alertes."
    }
};
```

### 3.2 Email Templates

Create French versions of all email templates:
- `confirmation_fr.html`
- `snow_urgent_fr.html`
- `snow_scheduled_fr.html`
- `snow_cleared_fr.html`
- `waste_reminder_fr.html`
- `snow_quebec_fr.html`
- `waste_reminder_quebec_fr.html`

**Alternative**: Use Jinja2 conditionals with translation dict passed from backend.

### 3.3 Backend Integration

Store subscriber language preference:
```python
class Subscriber(db.Model):
    language = db.Column(db.String(2), default='en')  # 'en' or 'fr'
```

Pass language to email service:
```python
def send_email(to, subject, template_name, language='en', **context):
    template = f"{template_name}_{language}.html"
    # ... render and send
```

---

## 4. City Auto-Detection from Geolocation

### 4.1 Detection Logic

```javascript
function detectCityFromCoordinates(lat, lon) {
    // Montreal: ~45.4-45.7 latitude
    // Quebec City: ~46.7-47.0 latitude

    if (lat >= 46.5 && lat <= 47.5 && lon >= -71.5 && lon <= -71.0) {
        return 'quebec';
    } else if (lat >= 45.3 && lat <= 45.8 && lon >= -74.0 && lon <= -73.3) {
        return 'montreal';
    }
    return null; // Outside supported cities
}
```

### 4.2 UX Flow

1. On page load, check if city preference is stored
2. If not stored and user clicks "Use My Location":
   - Request geolocation permission
   - Get coordinates
   - Auto-set city based on location
   - Update city toggle visually
   - Proceed with status check

3. If geolocation fails or is outside supported areas:
   - Fall back to default (Montreal)
   - Show appropriate message

### 4.3 Integration with Existing "Use My Location" Button

Enhance current geolocation flow:
```javascript
async function geolocateUser() {
    // ... existing code ...

    navigator.geolocation.getCurrentPosition(
        (position) => {
            const lat = position.coords.latitude;
            const lon = position.coords.longitude;

            // NEW: Auto-detect and set city
            const detectedCity = detectCityFromCoordinates(lat, lon);
            if (detectedCity && detectedCity !== currentCity) {
                setCity(detectedCity);
            }

            // Continue with existing logic...
            checkStatusWithCoordinates(lat, lon);
        },
        // ... error handling ...
    );
}
```

---

## 5. Technical Specifications

### 5.1 Browser Language Detection

```javascript
function detectBrowserLanguage() {
    // Check navigator.language first (most reliable)
    const browserLang = navigator.language || navigator.userLanguage || 'en';

    // Handle variants: fr-CA, fr-FR → fr
    const primaryLang = browserLang.split('-')[0].toLowerCase();

    // Only support en and fr
    return primaryLang === 'fr' ? 'fr' : 'en';
}
```

### 5.2 HTML Lang Attribute

Update `<html>` tag dynamically:
```javascript
function applyLanguage(lang) {
    document.documentElement.lang = lang;
    // ... apply translations ...
}
```

### 5.3 API Language Parameter

Pass language preference to API for error messages:
```javascript
fetch(`/api/subscribe`, {
    body: JSON.stringify({
        email,
        postal_code,
        city: currentCity,
        language: currentLanguage,  // NEW
        // ...
    })
});
```

---

## 6. User Stories

1. **As a French-speaking user**, I want the site to automatically display in French based on my browser settings, so I can use the service in my preferred language.

2. **As a user**, I want to toggle between English and French at any time, so I can switch languages if the auto-detected one is wrong.

3. **As a subscriber**, I want to receive email alerts in my chosen language, so I can understand the notifications easily.

4. **As a user in Quebec City**, I want the app to automatically detect my city when I use geolocation, so I don't have to manually switch from Montreal.

5. **As a user outside Montreal/Quebec**, I want to see a helpful message explaining the service area, so I understand why I can't subscribe.

---

## 7. Success Metrics

- Language toggle usage rate
- Auto-detection accuracy (% correct from browser language)
- City auto-detection usage via geolocation
- French vs English subscription ratio
- Error rate by language

---

## 8. Out of Scope

- Languages other than English and French
- RTL language support
- Date/time format localization (already uses locale-aware formatting)
- Currency formatting (not applicable)

---

## 9. Dependencies

- No external i18n libraries required (simple config object approach)
- Geolocation API (already in use)
- localStorage (already in use)

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Browser blocks geolocation | Fall back to postal code input |
| User outside service area | Show clear message with service boundaries |
| Translation errors | Have native French speaker review |
| localStorage disabled | Use session fallback, default to English |
