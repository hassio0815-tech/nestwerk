"""Sicherheits-Header (ARCHITECTURE 4.5): Content-Security-Policy ohne Inline-Skripte/-Styles.

Django 5.2 bringt keine CSP mit. Alles kommt von der eigenen Origin (selbst gehostete Schriften,
HTMX, SortableJS, eigene JS-Dateien). ``data:``/``blob:`` nur für Bilder (Nachweis-Vorschau im
Browser). Views dürfen eine eigene, strengere oder abweichende Policy setzen (z. B. die
Offline-Seite); sie wird dann nicht überschrieben.

``Referrer-Policy``, ``X-Content-Type-Options`` und ``X-Frame-Options`` setzen bereits Djangos
``SecurityMiddleware``/``XFrameOptionsMiddleware`` (Standardwerte), HSTS setzt der Proxy.
"""

CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "manifest-src 'self'",
        "worker-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)


class SicherheitsHeader:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        antwort = self.get_response(request)
        if "Content-Security-Policy" not in antwort:
            antwort["Content-Security-Policy"] = CSP
        return antwort
