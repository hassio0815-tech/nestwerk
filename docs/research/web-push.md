# Web Push für Nestwerk (iOS, Android, Kiosk-Tablet, Django)

Stand: 23.10.2026. Quellen per WebFetch am 23.10.2026 abgerufen (Quellendatum jeweils dabei).
Kennzeichnung: **[verifiziert]** = in Quelle gelesen. **[ungeprüft]** = Annahme/Altwissen, vor Umsetzung auf Gerät testen.
Hinweis: Die Apple-Developer-Doku-Seite war per Tool nicht lesbar (JS-Seite); Aussagen daraus wurden NICHT übernommen.

## 1. Web Push auf iOS/iPadOS

- Mindestversion iOS/iPadOS **16.4** [verifiziert]
  - https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/ (16.02.2023)
- Push nur für **Web-Apps vom Home-Bildschirm**, nicht für Safari-Tabs [verifiziert]
  - MDN/BCD: PushManager Safari iOS 16.4 "Notifications are supported in web apps saved to the home screen"
  - https://github.com/mdn/browser-compat-data/blob/main/api/PushManager.json (main, abgerufen 23.10.2026)
- Manifest bis iOS 18: `display` = `standalone` oder `fullscreen`, sonst nur Lesezeichen [verifiziert]
  - https://webkit.org/blog/13878/ (16.02.2023)
- **iOS 26 (Safari 26.0)**: Home-Bildschirm-Seiten öffnen standardmäßig als Web-App ("Open as Web App" an). Manifest nicht mehr nötig ("zero requirements for installability") [verifiziert]
  - https://webkit.org/blog/17333/webkit-features-in-safari-26-0/ (15.09.2025)
  - Der Blog sagt NICHTS dazu, dass Push ohne Home-Bildschirm geht. Home-Bildschirm-Pflicht bleibt also **[Annahme: bleibt]**; Nutzer kann "Open as Web App" abschalten, dann kein Web-App-Modus.
  - Trotzdem Manifest mit `display: standalone`, Name, Icons behalten (robust, Icons).
- Berechtigungsabfrage nur nach **direkter Nutzergeste** (Tap auf "Benachrichtigungen aktivieren") [verifiziert]
  - https://webkit.org/blog/13878/ (16.02.2023)
- `userVisibleOnly: true` Pflicht; **keine stillen Pushes** [verifiziert]
  - https://webkit.org/blog/16535/meet-declarative-web-push/ (27.03.2025)
- Standard-Web-Push mit **VAPID**; kein Apple-Developer-Account nötig [verifiziert]
- Zustellung über APNs. Ausgehende Firewall: **`*.push.apple.com`** (Endpoint-Host u. a. `web.push.apple.com`) HTTPS 443 [verifiziert für `*.push.apple.com`]
  - https://webkit.org/blog/13878/ (16.02.2023)
  - Endpoint-URL als opak behandeln, nicht parsen.
- Server braucht nur **ausgehend** 443 zu den Push-Diensten, keinen eingehenden Zugang.

### Was iOS 18.4 (Declarative Web Push) änderte [verifiziert]
- https://webkit.org/blog/16535/meet-declarative-web-push/ (27.03.2025, Test auf iOS/iPadOS 18.4)
- Push-Payload kann **ohne Service-Worker-JS** angezeigt werden.
- Payload-Format: JSON mit `"web_push": 8030` und `"notification": {title (Pflicht), navigate (Pflicht, URL), body, ...}`
- Subscribe weiterhin per `pushManager.subscribe()` mit `userVisibleOnly:true` + `applicationServerKey`.
- Service Worker optional; darf Inhalt ersetzen, sonst greift die deklarative Anzeige als Fallback.
- Vorteil: Keine "silent push penalties" (Entzug der Subscription, wenn SW keine Notification zeigt). Ein Entfernen der SW-Registrierung (z. B. ITP) zerstört die Subscription nicht.
- Älteren Browsern ist das Format egal: dort verarbeitet der SW-`push`-Handler es imperativ -> SW-Handler trotzdem implementieren, der `web_push`-Format versteht (Android!).
- Badge: Feld **`app_badge`** in der Nachricht möglich [verifiziert, im Beispiel "1"].
- iOS 26: laut Safari-26-Blog keine Push-spezifischen Änderungen genannt [verifiziert: nicht erwähnt].
- Offen [ungeprüft]: erlaubte `navigate`-Origin (vermutlich gleiche Origin), Content-Type-Header für Declarative. Per Spec/Test klären.

## 2. Actions und Badges auf iOS

- **Notification Actions (Buttons): NICHT unterstützt auf Safari/iOS** [verifiziert]
  - MDN/BCD `Notification.actions`: Safari `false`, Safari iOS spiegelt Safari (= false), Android WebView `false`, Chrome Android ja.
  - https://github.com/mdn/browser-compat-data/blob/main/api/Notification.json (main, 23.10.2026)
  - Declarative-Format (WebKit-Post) kennt nur `navigate`, keine Buttons.
  - Konsequenz: "Bestätigen" nicht als Button. Stattdessen Tap auf Notification -> `navigate` auf Bestätigungsseite (Deep Link).
- **Badging API**: `navigator.setAppBadge()` / `clearAppBadge()` ab iOS 16.4 für Home-Bildschirm-Web-Apps [verifiziert]
  - https://webkit.org/blog/13878/ (16.02.2023); BCD Navigator.json (23.10.2026)
  - Funktioniert auch im Push-Handler im Hintergrund. Badge-Berechtigung in iOS-Einstellungen > Mitteilungen.
  - `0` löscht das Badge.
  - Deklarativ: `app_badge` im Payload.
- Chrome Android: `setAppBadge` laut BCD **nicht** unterstützt [verifiziert BCD]. Android zeigt Badge über Notification-Punkt selbst.

## 3. Android, Kiosk-Tablet

- Chrome Android: Web Push funktioniert **auch im normalen Tab**, Installation als PWA nicht Pflicht (HTTPS, Service Worker, VAPID, Nutzergeste empfohlen). Zustellung über FCM (`fcm.googleapis.com`). [teils verifiziert]
  - https://web.dev/articles/push-notifications-overview (abgerufen 23.10.2026): VAPID bei Chrome praktisch nötig, Browser-Hersteller wählt Push-Dienst, TTL steuert Queue.
  - Nutzergeste und "Installation nicht nötig": [ungeprüft/Altwissen].
  - Firewall: ausgehend `fcm.googleapis.com` 443 (und für Gerät Google-Mobilfunkdienste 5228-5230 -- Gerät, nicht Server) [ungeprüft].
- **Android WebView unterstützt Push API nicht** [verifiziert]
  - BCD PushManager: `webview_android: version_added false` (23.10.2026)
  - Fully Kiosk Browser basiert auf WebView -> **kein Web Push, keine Notification-Actions** (BCD `Notification.actions` WebView = false).
  - Fully-Kiosk-Doku nennt kein Web Push/Service-Worker-Feature (Docs durchsucht 23.10.2026: https://www.fully-kiosk.com/docs/en/).
- Alternativen für das Flur-Tablet:
  1. **Gar kein Push** (Empfehlung): Display ist geteilt und dauerhaft sichtbar. Seite aktualisiert sich per **HTMX-Polling / SSE**, zeigt offene Aufgaben/Bestätigungen live.
  2. Fully Kiosk **REST-API/Remote Admin (PLUS-Lizenz)**: Server kann `/screenOn`, `/setOverlayMessage?text=`, `/textToSpeech?text=`, `/playSound?url=`, `/loadUrl` aufrufen -> Display aufwecken, Hinweis/Ton bei Ereignissen.
     - https://www.fully-kiosk.com/docs/en/api/rest (abgerufen 23.10.2026). Doku-Seite ist als "PLUS" markiert.
     - Gerät im Heimnetz: Server -> Tablet `http://<ip>:2323` (LAN, passt). Passwort nötig, Tablet feste IP.
  3. Fully **MQTT** (PLUS) falls ein Broker existiert. Overkill.
  4. Chrome im Kiosk/Screen-Pinning: Push ginge nur mit Chrome (kein Fully), Kiosk-Härtung dort schwächer. Nur falls echte Push-Meldungen am Tablet gewünscht. [ungeprüft]
- Fully-Kiosk-Hinweis: WebView-Version kann veraltet sein (FAQ-Titel "outdated Webview"); HTMX/SSE braucht aktuelles Android System WebView -> auf dem Tablet aktuell halten.

## 4. Server-Bibliotheken (Django)

| Bibliothek | Letzte Version | Datum | Status |
|---|---|---|---|
| **pywebpush** | 2.5.0 | 29.08.2026 | aktiv (2.4.0 06.08.2026, 2.3.0 02.2026, 2.1.x 2025); Python >= 3.10; Maintainer allein, PyPI "Critical Project" |
| **py-vapid** | 1.9.6 | 14.10.2026 | aktiv (1.9.4 05.01.2026); 1.9.3 yanked |
| django-webpush | 0.3.6 | 30.04.2024 | kaum gepflegt, Django-Klassifier nur 1.8, setzt pywebpush>=1.14 |

- Quellen: https://pypi.org/pypi/pywebpush/json , https://pypi.org/pypi/py-vapid/json , https://pypi.org/pypi/django-webpush/json (alle 23.10.2026), https://github.com/web-push-libs/pywebpush (README, 23.10.2026)
- pywebpush: Verschlüsselung aes128gcm (RFC 8188) Standard, `ttl`, eigene `headers`, 429/503 `retry_after`, `WebPushException` (Response-Code 404/410 -> Subscription löschen). **Urgency/Topic nicht dokumentiert**, aber über `headers={"Urgency":..., "Topic":...}` setzbar [ungeprüft].
- **Declarative Web Push**: kein Eigen-Support in pywebpush, nötig ist es auch nicht. `data` ist beliebiger String -> einfach das Declarative-JSON (`web_push: 8030`) senden [Schlussfolgerung; Content-Type-Header-Anforderung prüfen].
- Empfehlung: **pywebpush direkt** + eigenes kleines Django-Modell `PushSubscription(user, device_label, endpoint, p256dh, auth, created, last_ok, failed_count)`. django-webpush meiden (veraltet, 1-Entwickler-Altlast, wenig Kontrolle über Payload).
- Versand asynchron (Celery/Huey/Django-Q o. ä. oder Thread/Management-Command), nicht im Request.

## 5. Heimnetz-only: Funktioniert das?

- **Ja.** Push-Registrierung braucht nur: App über HTTPS im Heimnetz laden (gültiges Let's-Encrypt-Zertifikat, Domain per Split-DNS/lokal auflösbar), Subscription an den Server posten. Zustellung läuft Server -> Apple/Google-Push-Dienst -> Gerät über Internet. Gerät muss den Server **nicht** erreichen. [Schlussfolgerung aus Architektur, Push-Overview web.dev]
- Fallstricke:
  - **Tippen auf die Notification** öffnet `https://nestwerk.<domain>/...`. Unterwegs nicht erreichbar (kein VPN/Split-DNS) -> Fehlerseite. Optionen: WireGuard/Tailscale auf Handys, oder Notification-Text selbsterklärend ("Aufgabe X erledigt"), nur Info statt Aktion.
  - Selbstsigniertes/ungültiges Zertifikat bricht Service Worker/Push -> LE-Zertifikat rechtzeitig erneuern (NPM-Auto-Renew überwachen). DNS-Challenge löst das ohne öffentlichen Zugang.
  - Service-Worker-Update: SW-Datei nie lange cachen (`Cache-Control: no-cache` für `/sw.js` in NPM und Django), `skipWaiting`/`clients.claim` bewusst einsetzen, Cache-Version im Dateinamen/Konstante. Scope = `/` (SW unter Root ausliefern).
  - Subscriptions laufen aus bzw. werden ungültig: 404/410 vom Push-Dienst -> sofort löschen. `expirationTime` ist meist null [web.dev]. iOS: App-Neuinstallation/Löschen vom Home-Bildschirm = neue Subscription nötig. Bei App-Start `pushManager.getSubscription()` mit Server abgleichen, ggf. neu abonnieren (`pushsubscriptionchange` unzuverlässig).
  - Pro Gerät eine Subscription; mehrere Geräte pro Nutzer speichern; Doppel-Endpoints deduplizieren.
  - Jede Push-Nachricht MUSS (iOS) eine sichtbare Notification erzeugen, sonst Entzug (bei klassischem SW-Modell). Declarative-Format schützt davor.
  - VAPID-Schlüsselpaar einmal erzeugen und **sicher dauerhaft** speichern (Verlust = alle Subscriptions neu). `sub`-Claim `mailto:` setzen.
  - NPM: Weiterleitung nicht am Manifest/SW vorbeileiten, kein Auth-Redirect für `/sw.js`, `/manifest.json` (sonst fehlschlagender SW-Registrierung). Falls NPM Access-List nutzt: Pfade ausnehmen.
  - Ausgehende Firewall: `*.push.apple.com`, `fcm.googleapis.com` (+ ggf. `updates.push.services.mozilla.com`, nur falls Firefox).

## Nachrecherche iOS 26 (Websuche, 23.10.2026)

Hinweis: WebSearch lief in dieser Sitzung in einen Timeout (keine Freigabe), daher nur WebFetch auf Primärquellen. Alles Nicht-Gelesene bleibt **[ungeprüft]**.

1. **Push im normalen Safari-Tab auf iOS 26: nicht belegt, Annahme bleibt "nein".**
   - MDN/BCD `PushManager` (main, 23.10.2026): Safari iOS 16.4, Hinweis weiterhin "Notifications are supported in web apps saved to the home screen". Kein Eintrag für iOS 26 mit Änderung.
     - https://github.com/mdn/browser-compat-data/blob/main/api/PushManager.json
   - Safari-26.0-Blog (15.09.2025) erwähnt Push gar nicht. Änderung betrifft nur: jede Home-Bildschirm-Seite öffnet standardmäßig als Web-App, Nutzer kann "Open as Web App" abschalten, "zero requirements for installability", Manifest nicht mehr nötig [verifiziert].
     - https://webkit.org/blog/17333/webkit-features-in-safari-26-0/
   - Apple-Release-Notes-Seite (developer.apple.com) per Tool nicht lesbar [ungeprüft].
   - Folge: Home-Bildschirm-Installation bleibt Voraussetzung. Neu: jede Seite wird beim "Zum Home-Bildschirm" automatisch Web-App, solange der Schalter an ist.
2. **Declarative Web Push, Format** (Push-API-Spec-Entwurf, 23.10.2026: https://w3c.github.io/push-api/ ; WebKit-Blog https://webkit.org/blog/16535/meet-declarative-web-push/):
   - Erkennung am **entschlüsselten** Payload: JSON-Objekt, `web_push` == 8030, `notification` ist Objekt. Sonst normaler Push an den Service Worker [verifiziert].
   - Pflicht in `notification`: `title` (nicht leer) und `navigate` (String, muss zu gültiger URL werden; relative URL wird gegen Subscription-Scope aufgelöst). Fehlt/ungültig -> Parse schlägt fehl -> normaler Push-Event (auf iOS ohne SW = Problem) [verifiziert].
   - Alle weiteren Felder optional (`body`, `lang`, `dir`, `silent`, `app_badge`, ...) [verifiziert].
   - **Content-Type: Spec nennt keinen** (Parser arbeitet auf Bytes, nur `Content-Encoding: aes128gcm` wie bei normalem Push). Sendeweg laut WebKit "exactly as before" [verifiziert]. Ob APNs einen zusätzlichen Header verlangt: **[ungeprüft]**, auf dem Gerät testen.
   - **navigate-Origin**: Spec-Auszug nennt keine explizite Same-Origin-Prüfung (delegiert an Notifications-Spec, nicht gelesen) [ungeprüft]. Planung: immer relative Pfade oder URL auf eigener Origin senden.
   - Spec kennt auch `actions` (Einträge mit `action`, `title`, `navigate`); siehe Punkt 4.
3. **pywebpush 2.5.x, Urgency/Topic** (Quellcode `pywebpush/__init__.py` main, 23.10.2026; README):
   - Keine eigenen Parameter, aber `headers`-Dict wird durchgereicht (case-insensitive). Setzen: `webpush(..., headers={"Urgency": "high", "Topic": "chore-123"}, ttl=86400)` [Code gelesen; Ende-zu-Ende gegen APNs ungeprüft].
   - VAPID-Header überschreiben gleichnamige Caller-Header. `ttl`-Argument setzt TTL-Header (Default 0!). Content-Type wird nie gesetzt, `Content-Encoding` automatisch.
   - Achtung: `webpush()`-Signatur im README listet `headers` nicht in der One-Call-Doku; im Code wird `headers` kopiert, also vorhanden [Details beim Einbau prüfen].
   - Urgency-Werte (very-low|low|normal|high) und Topic (max 32 Zeichen URL-safe) stammen aus RFC 8030 [Altwissen, ungeprüft]. Apple-Verhalten zu Urgency/Topic [ungeprüft].
4. **Notification-Actions auf iOS 26: weiterhin nicht belegt/unterstützt.**
   - BCD `Notification.actions`: Safari `false`, Safari iOS spiegelt (= false) (main, 23.10.2026). https://github.com/mdn/browser-compat-data/blob/main/api/Notification.json
   - Neu: BCD `Notification.navigate` Safari/iOS **18.5** [verifiziert].
   - Das Push-API-Spec kennt `actions` im Declarative-Format; ob iOS 26 sie anzeigt, ist **[ungeprüft]**. Nicht darauf bauen, auf iPhone testen.

## Empfehlung für Nestwerk

1. **Push nur für iPhones** (Eltern + Kinder) als Home-Bildschirm-Web-App. Setup-Anleitung: Safari -> Teilen -> Zum Home-Bildschirm -> "Als Web-App öffnen" an -> App öffnen -> Button "Benachrichtigungen aktivieren" (Nutzergeste).
2. **Flur-Tablet (Fully Kiosk): kein Web Push.** Stattdessen HTMX-Polling/SSE für Live-Anzeige; optional Fully-REST (PLUS) für `screenOn` + `setOverlayMessage`/`textToSpeech` bei wichtigen Ereignissen. Lizenzkosten PLUS vorher prüfen.
3. **Keine Action-Buttons.** Notification-Tap -> Deep Link (`navigate`) auf Bestätigungsseite. Bestätigen innerhalb der App.
4. **Payload im Declarative-Format** (`web_push: 8030`, `title`, `body`, `navigate`, `app_badge`) senden, **zusätzlich** SW-`push`-Handler mit `showNotification` + `setAppBadge` (Fallback älteres iOS/Android/Desktop).
5. **Badge**: `app_badge` = Zahl offener Bestätigungen (Eltern) bzw. offener Aufgaben (Kinder); bei App-Öffnen `clearAppBadge()`/neu setzen.
6. Server: **pywebpush 2.5.x + py-vapid**, eigenes Modell, asynchroner Versand, 404/410 -> löschen, `ttl` setzen (z. B. 1 Tag für Erinnerungen), Fehlerzähler.
7. **Kein django-webpush.**
8. Subscription beim App-Start gegen Server abgleichen; Test-Button "Test-Push senden" in den Einstellungen.
9. Manifest trotz iOS 26 behalten (`display: standalone`, Icons 180/192/512, `start_url`, `scope`). `/sw.js` und `/manifest.json` ohne Cache und ohne Auth/Redirect ausliefern.
10. Zugriff unterwegs klären: VPN/WireGuard auf Eltern-Handys, sonst Notification-Texte ohne nötigen App-Aufruf formulieren.
11. Firewall ausgehend: `*.push.apple.com`, `fcm.googleapis.com`, 443.
12. **Vor Start auf echtem iPhone (iOS 26) testen**: Push ohne Home-Bildschirm (erwartet: nein), `navigate`-Verhalten (nur eigene Origin/relativ senden), Badge via `app_badge`, ob APNs für Declarative einen Extra-Header braucht (Spec: keiner), ob `actions` im Declarative-Format erscheinen (nicht verlassen).
13. **Urgency/Topic** über `headers={"Urgency":..., "Topic":...}` in pywebpush setzen (z. B. `high` für Bestätigungsanfragen, `normal` für Erinnerungen; Topic = Objekt-ID, damit neuere Nachricht ältere ersetzt) und `ttl` explizit übergeben (Default 0). Wirkung bei Apple ungeprüft.
14. Setup-Anleitung (Punkt 1) ergänzen: iOS 26 setzt "Als Web-App öffnen" standardmäßig an; Schalter im Auge behalten.
