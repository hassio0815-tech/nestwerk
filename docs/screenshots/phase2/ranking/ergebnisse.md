# Automatische Prüfung (Rohdaten)

| Seite | Konsole | CSP | Requests | Extern | Weitere Hinweise |
|---|---|---|---|---|---|
| eltern-login | 0 | 0 | 0 | 0 | - |
| ranking-schaufenster-eltern | 0 | 0 | 0 | 0 | - |
| ranking-schaufenster-tablet | 0 | 2 | 0 | 0 | handy: Horizontaler Überlauf: 419 > 390; handy: 3 Textelemente unter 14px; tablet: 3 Textelemente unter 14px |
| ranking-schaufenster-kind | 0 | 0 | 0 | 0 | handy: 3 Textelemente unter 14px; tablet: 3 Textelemente unter 14px |
| ranking-held-eltern | 0 | 0 | 0 | 0 | - |
| ranking-held-tablet | 0 | 2 | 0 | 0 | handy: Horizontaler Überlauf: 419 > 390; handy: 1 Textelemente unter 14px; tablet: 1 Textelemente unter 14px |
| ranking-held-kind | 0 | 0 | 0 | 0 | handy: 1 Textelemente unter 14px; tablet: 1 Textelemente unter 14px |
| ranking-rohpunkte-eltern | 0 | 0 | 0 | 0 | - |
| ranking-rohpunkte-tablet | 0 | 2 | 0 | 0 | handy: Horizontaler Überlauf: 419 > 390 |
| ranking-rohpunkte-kind | 0 | 0 | 0 | 0 | - |

## Details

- `ranking-schaufenster-tablet` [csp] error: EvalError: Evaluating a string as JavaScript violates the following Content Security Policy directive because 'unsafe-eval' is not an allowed source of script: script-src 'self'".

- `ranking-schaufenster-tablet` [csp] script-src blockiert eval (http://127.0.0.1:8766/static/vendor/htmx.min.js:1)
- `ranking-held-tablet` [csp] error: EvalError: Evaluating a string as JavaScript violates the following Content Security Policy directive because 'unsafe-eval' is not an allowed source of script: script-src 'self'".

- `ranking-held-tablet` [csp] script-src blockiert eval (http://127.0.0.1:8766/static/vendor/htmx.min.js:1)
- `ranking-rohpunkte-tablet` [csp] error: EvalError: Evaluating a string as JavaScript violates the following Content Security Policy directive because 'unsafe-eval' is not an allowed source of script: script-src 'self'".

- `ranking-rohpunkte-tablet` [csp] script-src blockiert eval (http://127.0.0.1:8766/static/vendor/htmx.min.js:1)
