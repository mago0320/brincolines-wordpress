#!/usr/bin/env python3
"""Read-only DNS/TCP/SSH diagnosis. Never authenticates or reads credentials."""
import errno
import json
import os
from pathlib import Path
import socket
import time


def probe_address(family, address, timeout=5):
    result = {'ip': address[0], 'port': address[1]}
    try:
        with socket.socket(family, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(address)
            result['tcp_connected'] = True
            data = b''
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and len(data) < 4096:
                connection.settimeout(max(0.1, deadline - time.monotonic()))
                chunk = connection.recv(512)
                if not chunk:
                    result['status'] = 'closed_before_ssh_banner'
                    return result
                data += chunk
                for line in data.splitlines():
                    if line.startswith(b'SSH-'):
                        result['status'] = 'ssh_reachable'
                        # Only the public protocol banner, never arbitrary server output.
                        result['ssh_banner'] = line.decode('ascii', errors='replace')[:200]
                        return result
                if b'HTTP/' in data or b'<html' in data.lower():
                    result['status'] = 'different_protocol'
                    return result
            result['status'] = 'tcp_open_without_ssh_banner'
    except (TimeoutError, socket.timeout):
        result['status'] = 'tcp_open_without_ssh_banner' if result.get('tcp_connected') else 'tcp_timeout'
    except ConnectionRefusedError:
        result['status'] = 'tcp_refused'
    except OSError as error:
        result['status'] = 'network_error'
        result['errno_name'] = errno.errorcode.get(error.errno, str(error.errno))
    return result


def diagnose(host, port):
    report = {'hostname': host, 'primary_port': port, 'attempts': []}
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        report['status'] = 'dns_error'
        return report
    seen = set()
    unique = []
    for family, _, _, _, address in addresses:
        if (family, address[0]) not in seen:
            unique.append((family, address))
            seen.add((family, address[0]))
    report['dns_addresses'] = [address[0] for _, address in unique]
    # Only the port explicitly requested; never search for alternate ports.
    for candidate_port in [port]:
        for family, original_address in unique[:4]:
            address = (original_address[0], candidate_port, *original_address[2:])
            result = probe_address(family, address)
            report['attempts'].append(result)
            if result['status'] == 'ssh_reachable':
                report['status'] = 'ssh_reachable'
                report['reachable_port'] = candidate_port
                return report
    report['status'] = 'ssh_not_reachable'
    return report


def main():
    host = os.environ['BH_HOST']
    # Diagnostic requests are scoped to the endpoint explicitly authorized.
    if host not in ('single-4650.banahosting.com', '50.31.167.146'):
        raise SystemExit('Servidor fuera del alcance autorizado del diagnóstico.')
    port = int(os.environ.get('BH_PORT', '22'))
    if not 1 <= port <= 65535:
        raise SystemExit('Puerto fuera del intervalo permitido.')
    report = diagnose(host, port)
    output = Path('.local/audit')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'ssh-connectivity.json').write_text(json.dumps(report, indent=2) + '\n')
    print('::notice title=Diagnóstico de transporte SSH::' + json.dumps(report, separators=(',', ':')))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('ssh_reachable=' + str(report['status'] == 'ssh_reachable').lower() + '\n')


if __name__ == '__main__':
    main()
