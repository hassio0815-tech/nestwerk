# Übergabe: Lernassistent-Rettung → nestwerk-Integration

Stand: 2026-11-03 · Quelle: Session im Projekt `Proxmox` (LXC 400)

## Ziel
- Alten **Lernassistenten** (CloudCLI-Projekt) aus Proxmox-Backup retten
- Inhalt **analysieren**, Fehler finden
- **Integration in nestwerk** planen und weiterentwickeln (`/xxx`)
- Lernassistent war **nicht fertig** und hatte **noch Fehler**

## Was schon erledigt ist
- Backup-Stick: `/dev/sda1` (NTFS), auf dem PVE-Host eingehängt unter `/mnt/usb-a` (read-only)
- Backups von LXC 400 auf dem Stick:
  - `vzdump-lxc-400-2026_08_16-...tar.zst`: **intakt** (genutzt)
  - `vzdump-lxc-400-2026_08_18-...tar.dat`: **defekt** (Datenfehler bei 15 GiB)
  - `vzdump-lxc-400-2026_08_27-...tar.dat`: **abgeschnitten** bei 50,5 GiB (Kopie liegt noch in `/root/restore-link/` auf dem Host, 32 GB)
- Backup vom **16.08.** als **LXC 401** wiederhergestellt (Host: `local-btrfs`)
  - Netz abgeschaltet (`ip=manual,link_down=1`), `onboot: 0`, **nie gestartet**
  - Rootfs ist mit `pct mount 401` am Host eingehängt: `/var/lib/lxc/401/rootfs`
- Lernassistent-Quelle (neuester Stand im Backup): `/project/lernassistent/` im Klon (1,4 MB)
  - Ältere Kopien (ignorieren): `/project/lernassistent*.py`, `/root/lernassistent/`
  - Git-Repo liegt über ganz `/project` (`.git`, 12 MB), letzte Commits 12.08., Tags `v1.1`/`v1.2-MASTER`
- Export auf dem PVE-Host: `/var/lib/vz/lernassistent-export/lernassistent` (mit `.env.local`!)

## Offen: Schritt 12 (Übergabe nach LXC 400)
Ziel: `/xxx/lernassistent` in LXC 400, **ohne** `.env.local`, `__pycache__`, `.pytest_cache`.
Wurde als Host-Befehl (tar-Pipe + `pct exec 400`) vorgeschlagen, **Ausführung nicht bestätigt**.
→ Zuerst prüfen: `ls /xxx/lernassistent`
→ Fehlt der Ordner, muss der Befehl auf dem PVE-Host (nicht hier) laufen:

```
tar -C /var/lib/vz/lernassistent-export \
  --exclude='lernassistent/.env.local' --exclude='__pycache__' --exclude='.pytest_cache' \
  -cf - lernassistent \
| pct exec 400 -- bash -c 'mkdir -p /xxx && tar -xf - -C /xxx'
```

## Nächste Schritte
1. Prüfen, ob der Import da ist (siehe oben)
2. Lesen: `README.md`, `ARCHITECTURE.md`, `PROJECT_STATUS.md`, `CLAUDE.md` des Lernassistenten
3. `nestwerk` ansehen (Struktur, `CLAUDE.md`)
4. **Analyse- und Integrationsplan** schreiben, inkl. bekannter Fehler
5. Plan dem Nutzer zeigen, erst nach OK umsetzen

## Aufräumen (erst am Ende, mit OK des Nutzers)
- `pct unmount 401` (Host)
- Entscheiden: LXC 401 behalten oder löschen
- `/root/restore-link/` (32 GB Kopie) und `/var/lib/vz/lernassistent-export/` auf dem Host löschen
- Backup-Stick wieder aushängen: `umount /mnt/usb-a`

## Vorsicht
- **Nie `pct restore 400`**: überschreibt die laufende LXC 400
- **LXC 401 nicht starten**, ohne vorher Netz/Tailscale zu klären (gleiche IP `xxx`, gleicher Tailscale-Node wie LXC 400)
- **Secrets**: `.env.local` und `/project/.env` im Klon nicht auslesen oder weitergeben
- Destruktive Aktionen vorher bestätigen lassen
- Arbeitsweise des Nutzers: erst Bedarf klären, kompakter Plan, OK abwarten, Ausgabe kurz und ADHS-freundlich
