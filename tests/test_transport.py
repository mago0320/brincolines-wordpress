"""Local socket checks for diagnostic classification, without hosting access."""
import importlib.util
from pathlib import Path
import socket
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('probe_ssh', Path(__file__).resolve().parents[1] / 'scripts/probe-ssh.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class TransportTests(unittest.TestCase):
    def server_result(self, data):
        server = socket.socket()
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        address = server.getsockname()
        def serve():
            with server:
                connection, _ = server.accept()
                with connection:
                    if data:
                        connection.sendall(data)
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        result = probe.probe_address(socket.AF_INET, address, timeout=1)
        thread.join(2)
        return result

    def test_ssh_banner_proves_ssh_transport(self):
        result = self.server_result(b'SSH-2.0-LocalFixture\r\n')
        self.assertEqual(result['status'], 'ssh_reachable')
        self.assertTrue(result['tcp_connected'])
        self.assertEqual(result['ssh_banner'], 'SSH-2.0-LocalFixture')

    def test_connection_closed_does_not_prove_ssh(self):
        self.assertEqual(self.server_result(b'')['status'], 'closed_before_ssh_banner')

    def test_http_listener_is_distinct_from_ssh(self):
        self.assertEqual(self.server_result(b'HTTP/1.1 200 OK\r\n')['status'], 'different_protocol')

    def test_closed_port_reports_refused(self):
        with socket.socket() as unused:
            unused.bind(('127.0.0.1', 0))
            address = unused.getsockname()
        result = probe.probe_address(socket.AF_INET, address, timeout=1)
        self.assertEqual(result['status'], 'tcp_refused')

    def test_dns_failure_does_not_guess_plan_restrictions(self):
        with patch.object(probe.socket, 'getaddrinfo', side_effect=socket.gaierror()):
            report = probe.diagnose('example.test', 22)
        self.assertEqual(report['status'], 'dns_error')
        self.assertEqual(report['attempts'], [])

    def test_timeout_is_distinct_from_refusal(self):
        with patch.object(probe.socket, 'socket') as constructor:
            constructor.return_value.__enter__.return_value.connect.side_effect = TimeoutError()
            result = probe.probe_address(socket.AF_INET, ('127.0.0.1', 22))
        self.assertEqual(result['status'], 'tcp_timeout')

    def test_open_socket_without_banner_is_distinct_from_filtered_tcp(self):
        with patch.object(probe.socket, 'socket') as constructor:
            constructor.return_value.__enter__.return_value.recv.side_effect = TimeoutError()
            result = probe.probe_address(socket.AF_INET, ('127.0.0.1', 22))
        self.assertEqual(result['status'], 'tcp_open_without_ssh_banner')

    def test_primary_ssh_does_not_probe_alternate_port(self):
        with patch.object(probe.socket, 'getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 22))]), patch.object(probe, 'probe_address', return_value={'status':'ssh_reachable'}) as check:
            report = probe.diagnose('example.test', 22)
        self.assertEqual(report['reachable_port'], 22)
        self.assertEqual(check.call_count, 1)

    def test_refused_primary_port_does_not_search_other_ports(self):
        with patch.object(probe.socket, 'getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 22))]), patch.object(probe, 'probe_address', return_value={'status':'tcp_refused'}) as check:
            report = probe.diagnose('example.test', 22)
        self.assertEqual(report['status'], 'ssh_not_reachable')
        self.assertEqual([call.args[1][1] for call in check.call_args_list], [22])

    def test_requested_port_is_checked_without_scanning_other_ports(self):
        with patch.object(probe.socket, 'getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 4650))]), patch.object(probe, 'probe_address', return_value={'status':'tcp_refused'}) as check:
            report = probe.diagnose('example.test', 4650)
        self.assertEqual(report['primary_port'], 4650)
        self.assertEqual(check.call_count, 1)
        self.assertEqual(check.call_args.args[1][1], 4650)


if __name__ == '__main__':
    unittest.main()
