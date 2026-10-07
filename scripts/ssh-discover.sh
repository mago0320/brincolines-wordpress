#!/usr/bin/env bash
# Run on the Actions runner. No production files are written.
set -euo pipefail
umask 077
fail() {
  local code=$1 message=$2
  printf '::error title=Diagnóstico SSH::%s\n' "$message" >&2
  exit "$code"
}
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p .local/audit

missing=0
for entry in 'BH_HOST:BANAHOST_SSH_HOST' 'BH_USER:BANAHOST_SSH_USER' 'BH_KEY:BANAHOST_SSH_PRIVATE_KEY'; do
  variable=${entry%%:*}
  label=${entry#*:}
  if [[ -z ${!variable:-} ]]; then
    printf '::error title=Secret requerido::Falta el secret %s o uno de sus alias documentados.\n' "$label" >&2
    missing=1
  fi
done
[[ $missing == 0 ]] || exit 2
[[ $BH_HOST =~ ^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$ ]] || fail 2 'Hostname SSH no válido.'
[[ $BH_USER =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$ ]] || fail 2 'Usuario SSH no válido.'
BH_PORT=${BH_PORT:-22}
[[ $BH_PORT =~ ^[0-9]{1,5}$ ]] && ((10#$BH_PORT >= 1 && 10#$BH_PORT <= 65535)) || fail 2 'Puerto SSH no válido.'

# Reuse the current run's read-only protocol diagnosis when it found a supported
# alternate port on this exact host; server identity verification still follows.
if [[ -f .local/audit/ssh-connectivity.json ]]; then
  export BH_HOST
  detected_port=$(python3 - <<'PY'
import json, os, pathlib
r=json.loads(pathlib.Path('.local/audit/ssh-connectivity.json').read_text())
port=r.get('reachable_port')
if r.get('hostname') == os.environ['BH_HOST'] and r.get('status') == 'ssh_reachable' and port in (22, 2222, 22022, 4650):
    print(port)
PY
)
  if [[ -n $detected_port ]]; then BH_PORT=$detected_port; fi
fi

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
    fail 3 'El secret known_hosts no contiene el servidor y puerto configurados.'
  }
else
  # A scan alone does not establish server identity. Authenticate only after
  # matching a fingerprint independently supplied through GitHub settings.
  if ! ssh-keyscan -T 10 -p "$BH_PORT" -- "$BH_HOST" > "$state/scanned_hosts" 2> "$state/scan-error"; then
    export BH_PORT BH_HOST
    reason=$(python3 - "$state/scan-error" <<'PY'
import pathlib, socket, sys
s = pathlib.Path(sys.argv[1]).read_text(errors='replace').lower()
reasons = (('connection refused', 'El puerto rechaza la conexión.'),
           ('timed out', 'El servidor no respondió dentro del plazo.'),
           ('no route to host', 'No existe ruta de red hacia el servidor.'),
           ('name or service not known', 'El hostname no se pudo resolver.'),
           ('temporary failure in name resolution', 'Falló la resolución DNS.'))
reason = next((text for marker, text in reasons if marker in s), None)
if reason is None:
    import os
    try:
        with socket.create_connection((os.environ['BH_HOST'], int(os.environ['BH_PORT'])), timeout=10) as connection:
            connection.settimeout(5)
            banner = connection.recv(255)
            reason = 'El puerto responde como SSH, pero falló el intercambio de claves.' if banner.startswith(b'SSH-') else 'El puerto respondió sin una cabecera SSH.'
    except ConnectionRefusedError:
        reason = 'El puerto rechaza la conexión TCP.'
    except (TimeoutError, socket.timeout):
        reason = 'La conexión TCP o la cabecera SSH agotó el plazo.'
    except socket.gaierror:
        reason = 'El hostname no se pudo resolver por DNS.'
    except OSError as error:
        reason = 'La conexión TCP falló (errno ' + str(error.errno) + ').'
print(reason)
PY
)
    fail 3 "No se pudo consultar la clave pública del servidor SSH. $reason"
  fi
  [[ -s $state/scanned_hosts ]] || fail 3 'El servidor SSH no respondió al consultar su clave pública.'
  ssh-keygen -lf "$state/scanned_hosts" | awk '{print $2}' > .local/audit/host-key-fingerprints.txt
  if [[ -z ${BH_FINGERPRINT:-} ]]; then
    echo 'Huellas observadas (aún sin verificar con BanaHosting):' >&2
    while IFS= read -r fingerprint; do printf '::notice title=Huella SSH observada::%s\n' "$fingerprint" >&2; done < .local/audit/host-key-fingerprints.txt
    fail 3 'Falta confianza del servidor: BANAHOST_SSH_KNOWN_HOSTS o BANAHOST_SSH_FINGERPRINT.'
  fi
  export BH_FINGERPRINT
  python3 - "$state/scanned_hosts" "$state/known_hosts" <<'PY'
import hmac, os, pathlib, re, subprocess, sys, tempfile
expected = os.environ['BH_FINGERPRINT'].strip()
if not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}', expected):
    raise SystemExit('::error title=Identidad SSH::La huella debe tener formato SHA256:...')
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
    raise SystemExit('::error title=Identidad SSH::La huella del servidor NO coincide con la configurada. Se canceló la conexión.')
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
  fail 4 'No se pudo cargar la clave privada. Comprueba el formato y la passphrase, si está cifrada.'
}
ssh-add -L > "$state/private_key.pub"
chmod 600 "$state/private_key.pub"

root_hint=${BH_ROOT_HINT:-}
# Quote the optional path for the remote shell; never interpolate secret values
# into shell source or log the resulting command.
printf -v quoted_hint '%q' "$root_hint"
if ! ssh -p "$BH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="$state/known_hosts" -o GlobalKnownHostsFile=/dev/null \
  -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 \
  -o ForwardAgent=no -o IdentitiesOnly=yes -i "$state/private_key" \
  "$BH_USER@$BH_HOST" "bash -s -- brincolinesjumping.com $quoted_hint" \
  < scripts/discover-wordpress.sh > .local/audit/wordpress-inventory.json 2> "$state/ssh-error"; then
  reason=$(python3 - "$state/ssh-error" <<'PY'
import pathlib, sys
s = pathlib.Path(sys.argv[1]).read_text(errors='replace')
markers = (('Permission denied', 'El servidor rechazó la autenticación con la clave autorizada.'),
           ('Host key verification failed', 'La clave pública del servidor no coincide.'),
           ('Connection refused', 'El puerto SSH rechaza la conexión.'),
           ('Connection timed out', 'La conexión SSH agotó el plazo.'),
           ('no corresponde', 'La ruta configurada no corresponde al dominio autorizado.'),
           ('instalaciones coincidentes', 'No se encontró una única instalación del dominio autorizado.'),
           ('multisite', 'La instalación es multisite y necesita un alcance por sitio.'),
           ('WP-CLI no se encuentra', 'WP-CLI no se encuentra en las rutas habituales.'),
           ('búsqueda de instalaciones quedó incompleta', 'La búsqueda de instalaciones quedó incompleta.'))
print(next((text for marker, text in markers if marker in s), 'Falló la conexión o el inventario remoto; revisa el log del paso SSH.'))
PY
)
  fail 5 "$reason"
fi

python3 - <<'PY'
import json, os, pathlib
p = pathlib.Path('.local/audit/wordpress-inventory.json')
report = json.loads(p.read_text())
assert report['target_domain'] == 'brincolinesjumping.com'
assert report['match_verified'] is True
print('Conexión SSH y dominio verificados. Inventario disponible en el artifact de esta ejecución.')
print('WordPress:', report['wordpress_version'])
print('Tema activo:', report['active_stylesheet'])
print('Plugins inventariados:', len(report['plugins']))
if os.environ.get('GITHUB_ACTIONS') == 'true':
    for field in ('ssh_user','home_dir','wordpress_root','content_dir','themes_dir'):
        if field in report: report[field]='[private]'
    p.write_text(json.dumps(report,indent=2)+'\n')
PY
