<#
.SYNOPSIS
  Zeigt, wo auf Home Assistant Kopien der App liegen und welche Version sie haben.

.EXAMPLE
  .\diagnose.ps1 -Ziel 192.168.1.10
#>
param(
    [Parameter(Mandatory = $true)][string]$Ziel,
    [int]$Port = 22,
    [string]$Benutzer = "hassio"
)

# Läuft auf HA unter sh (die SSH-App nutzt zsh als Login-Shell, das versteht manches anders).
# Bewusst ohne einfache und doppelte Anführungszeichen, damit nichts unterwegs umgedeutet wird.
$befehl = 'if [ $(id -u) -ne 0 ]; then S=sudo; else S=; fi; echo Benutzer: $(id -un); for d in /local_apps /addons; do echo; echo [$d]; $S ls -la $d 2>&1; done; echo; echo [Kopien der Behaelterverwaltung]; $S find / -maxdepth 5 \( -path /proc -o -path /sys -o -path /dev \) -prune -o -name config.yaml -print 2>/dev/null | while read f; do if grep -q behaelterverwaltung $f 2>/dev/null; then echo; echo Datei: $f; grep -E ^version $f; echo Icons: $($S ls $(dirname $f)/app/templates/icons 2>&1 | xargs echo); fi; done'

ssh -c aes128-ctr -m hmac-sha2-256-etm@openssh.com,hmac-sha2-256 -p $Port "${Benutzer}@${Ziel}" "sh -c '$befehl'"
