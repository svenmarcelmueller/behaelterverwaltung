<#
.SYNOPSIS
  Überträgt die App vollständig nach Home Assistant (SSH-App muss laufen).

.EXAMPLE
  .\deploy.ps1 -Ziel 192.168.1.10
  .\deploy.ps1 -Ziel 192.168.1.10 -Port 22222 -Benutzer root
#>
param(
    [Parameter(Mandatory = $true)][string]$Ziel,
    [int]$Port = 22,
    [string]$Benutzer = "hassio"
)

$ErrorActionPreference = "Stop"
# Die App liegt im Unterordner (Aufbau eines Home-Assistant-App-Repositorys)
Set-Location (Join-Path $PSScriptRoot "behaelterverwaltung")

# Genau das, was in den Container gehört – nichts aus tests, konzept, .venv, dev-data
$inhalt = @("config.yaml", "Dockerfile", "run.sh", "requirements.txt", "DOCS.md", "CHANGELOG.md", "translations", "app")
foreach ($pfad in $inhalt) {
    if (-not (Test-Path $pfad)) { throw "Fehlt im Projektordner: $pfad" }
}
foreach ($bild in "icon.png", "logo.png", "LICENSE") {
    if (Test-Path $bild) { $inhalt += $bild }
}

$version = (Select-String -Path config.yaml -Pattern '^version:\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "Packe Behälterverwaltung $version ..."

$archiv = Join-Path $env:TEMP "behaelterverwaltung-deploy.tar"
if (Test-Path $archiv) { Remove-Item $archiv }
tar --exclude "__pycache__" --exclude "*.pyc" -cf $archiv @inhalt
if ($LASTEXITCODE -ne 0) { throw "tar ist fehlgeschlagen" }
Write-Host ("  {0} Dateien" -f (tar -tf $archiv | Where-Object { -not $_.EndsWith("/") }).Count)

Write-Host "Übertrage nach ${Benutzer}@${Ziel} (Port $Port) ..."
# Ohne scp: das Archiv geht über ssh als Eingabe direkt in tar auf HA. Erst in einen neuen Ordner
# entpacken, dann tauschen – bricht etwas ab, bleibt der alte Stand erhalten.
# /local_apps (neu) oder /addons (alt) wird automatisch gefunden; als Nicht-root (z. B. hassio) mit sudo.
$befehl = 'set -e; if [ -d /local_apps ]; then b=/local_apps; elif [ -d /addons ]; then b=/addons; else echo FEHLER: weder /local_apps noch /addons gefunden >&2; exit 3; fi; if [ $(id -u) -ne 0 ]; then S=sudo; else S=; fi; z=$b/behaelterverwaltung; $S rm -rf $z.neu; $S mkdir -p $z.neu; $S tar -xf - -C $z.neu; $S rm -rf $z; $S mv $z.neu $z; echo Entpackt nach $z:; ls $z'
# cmd statt PowerShell-Pipe: nur so kommt die Binärdatei unverändert bei ssh an.
# -c/-m: Windows-OpenSSH bricht bei größeren Übertragungen mit chacha20/umac gelegentlich mit
# "Corrupted MAC on input" ab; aes128-ctr + hmac-sha2-256(-etm) ist davon nicht betroffen.
# Die HA-SSH-App bietet nur die -etm-Varianten an, daher beide zur Auswahl.
$befehlSh = "sh -c '" + $befehl.Replace("'", "'\''") + "'"
cmd /c "ssh -c aes128-ctr -m hmac-sha2-256-etm@openssh.com,hmac-sha2-256 -p $Port ${Benutzer}@${Ziel} `"$befehlSh`" < `"$archiv`""
$ergebnis = $LASTEXITCODE
Remove-Item $archiv
if ($ergebnis -ne 0) {
    Write-Host ""
    Write-Host "Übertragung fehlgeschlagen (Exitcode $ergebnis). Die Meldung von ssh steht oben. Häufige Ursachen:" -ForegroundColor Red
    Write-Host "  - 'Connection refused' / 'timed out': SSH-App läuft nicht oder anderer Port -> -Port angeben (siehe App > Konfiguration > Netzwerk)"
    Write-Host "  - 'Permission denied': Passwort oder Schlüssel in der SSH-App nicht eingerichtet bzw. falsch"
    Write-Host "  - 'Host key verification failed': einmal 'ssh -p $Port ${Benutzer}@${Ziel}' von Hand aufrufen und mit 'yes' bestätigen"
    Write-Host "  - 'no matching cipher/MAC found': SSH-App kennt aes128-ctr/hmac-sha2-256 nicht -> Ausgabe an Claude schicken"
    Write-Host "  - 'tar: not found' oder Exitcode 3: bitte Ausgabe an Claude schicken"
    exit 1
}

Write-Host ""
Write-Host "Fertig. In Home Assistant: Einstellungen > Apps > App installieren > Menü > 'Nach Updates suchen'," -ForegroundColor Green
Write-Host "dann bei der Behälterverwaltung 'Aktualisieren' (Version $version)." -ForegroundColor Green
