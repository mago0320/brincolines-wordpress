#!/usr/bin/env bash
# Run on the Actions runner. No production files are written.
set -euo pipefail
umask 077
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p .local/audit

missing=0
for entry in 'BH_HOST:BANAHOST_SSH_HOST' 'BH_USER:BANAHOST_SSH_USER' 'BH_KEY:BANAHOST_SSH_PRIVATE_KEY'; do
  variable=${entry%%:*}
  label=${entry#*:}
  if [[ -z ${!variable:-} ]]; then
    printf 'Falta el secret %s o uno de sus alias documentados.\n' "$label" >&2
    missing=1
  fi
done
[[ $missing == 0 ]] || exit 2
[[ $BH_HOST =~ ^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$ ]] || { echo 'Hostname SSH no válido.' >&2; exit 2; }
[[ $BH_USER =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$ ]] || { echo 'Usuario SSH no válido.' >&2; exit 2; }
BH_PORT=${BH_PORT:-22}
[[ $BH_PORT =~ ^[0-9]{1,5}$ ]] && ((10#$BH_PORT >= 1 && 10#$BH_PORT <= 65535)) || { echo 'Puerto SSH no válido.' >&2; exit 2; }

state=$(mktemp -d "${RUNNER_TEMP:-/tmp}/brincos-ssh.XXXXXXXX")
agent_started=0
cleanup() {
  if [[ $agent_started == 1 ]]; then ssh-agent -k >/dev/null 2>&1 || true; fi
  rm -rf -- "$state"
}
trap cleanup EXIT

if [[ -n ${BH_KNOWN_HOSTS:-} ]]; then
  printf '%s\n' "$BH_KNOWN_HOSTS" > "$state/known_hosts"
  lookup=$BH_HOST
  [[ $BH_PORT == 22 ]] || lookup="[$BH_HOST]:$BH_PORT"
  ssh-keygen -F "$lookup" -f "$state/known_hosts" >/dev/null || {
    echo 'El secret known_hosts no contiene el servidor y puerto configurados.' >&2; exit 3;
  }
else
  # A scan alone does not establish server identity. Authenticate only after
  # matching a fingerprint independently supplied through GitHub settings.
  if ! ssh-keyscan -T 10 -p "$BH_PORT" -- "$BH_HOST" > "$state/scanned_hosts" 2> "$state/scan-error"; then
    echo 'No se pudo consultar la clave pública del servidor SSH.' >&2; exit 3
  fi
  [[ -s $state/scanned_hosts ]] || { echo 'El servidor SSH no respondió al consultar su clave pública.' >&2; exit 3; }
  ssh-keygen -lf "$state/scanned_hosts" | awk '{print $2}' > .local/audit/host-key-fingerprints.txt
  if [[ -z ${BH_FINGERPRINT:-} ]]; then
    echo 'Falta confianza del servidor: BANAHOST_SSH_KNOWN_HOSTS o BANAHOST_SSH_FINGERPRINT.' >&2
    echo 'Huellas observadas (aún sin verificar con BanaHosting):' >&2
    cat .local/audit/host-key-fingerprints.txt >&2
    exit 3
  fi
  export BH_FINGERPRINT
  python3 - "$state/scanned_hosts" "$state/known_hosts" <<'PY'
import hmac, os, pathlib, re, subprocess, sys, tempfile
expected = os.environ['BH_FINGERPRINT'].strip()
if not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}', expected):
    raise SystemExit('La huella debe tener formato SHA256:...')
matches = []
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    if line.startswith('#') or not line.strip():
        continue
    with tempfile.NamedTemporaryFile(mode='w', dir=pathlib.Path(sys.argv[1]).parent) as key:
        key.write(line + '\n'); key.flush()
        result = subprocess.run(['ssh-keygen', '-lf', key.name], capture_output=True, text=True, check=True)
        fingerprint = result.stdout.split()[1]
    if hmac.compare_digest(fingerprint, expected):
        matches.append(line)
if not matches:
    raise SystemExit('La huella del servidor NO coincide con la configurada. Se canceló la conexión.')
pathlib.Path(sys.argv[2]).write_text('\n'.join(matches) + '\n')
PY
fi

printf '%s\n' "$BH_KEY" | tr -d '\r' > "$state/private_key"
chmod 600 "$state/private_key" "$state/known_hosts"
eval "$(ssh-agent -s)" >/dev/null
agent_started=1
cat > "$state/askpass" <<'SH'
#!/bin/sh
printf '%s' "${BH_PASSPHRASE:-}"
SH
chmod 700 "$state/askpass"
export BH_PASSPHRASE="${BH_PASSPHRASE:-}" SSH_ASKPASS="$state/askpass" SSH_ASKPASS_REQUIRE=force DISPLAY=brincos-ssh
ssh-add "$state/private_key" </dev/null > "$state/key-output" 2>&1 || {
  echo 'No se pudo cargar la clave privada. Comprueba el formato y la passphrase, si está cifrada.' >&2
  exit 4
}
ssh-add -L > "$state/private_key.pub"
chmod 600 "$state/private_key.pub"

root_hint=${BH_ROOT_HINT:-}
# Quote the optional path for the remote shell; never interpolate secret values
# into shell source or log the resulting command.
printf -v quoted_hint '%q' "$root_hint"
ssh -p "$BH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="$state/known_hosts" -o GlobalKnownHostsFile=/dev/null \
  -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 \
  -o ForwardAgent=no -o IdentitiesOnly=yes -i "$state/private_key" \
  "$BH_USER@$BH_HOST" "bash -s -- brincolinesjumping.com $quoted_hint" \
  < scripts/discover-wordpress.sh > .local/audit/wordpress-inventory.json

python3 - <<'PY'
import json, pathlib
p = pathlib.Path('.local/audit/wordpress-inventory.json')
report = json.loads(p.read_text())
assert report['target_domain'] == 'brincolinesjumping.com'
assert report['match_verified'] is True
print('Conexión SSH y dominio verificados. Inventario disponible en el artifact de esta ejecución.')
print('WordPress:', report['wordpress_version'])
print('Tema activo:', report['active_stylesheet'])
print('Plugins inventariados:', len(report['plugins']))
PY
