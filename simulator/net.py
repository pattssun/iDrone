"""LAN IP detection and self-signed cert generation."""

from __future__ import annotations

import datetime
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def detect_lan_ip() -> str:
    """Return the most likely LAN-facing IPv4 address.

    Uses the connect-but-don't-send trick so we don't depend on hostname
    resolution (which on macOS often returns something useless).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 1.1.1.1 chosen arbitrarily; no packet is actually sent for UDP.
        s.connect(("1.1.1.1", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip


def is_private_ipv4(ip: str) -> bool:
    try:
        return ipaddress.IPv4Address(ip).is_private
    except ValueError:
        return False


def ensure_cert(cert_dir: Path, lan_ip: str, regenerate: bool = False) -> tuple[Path, Path]:
    """Return (cert_path, key_path), generating a self-signed cert if missing.

    The SAN includes the given LAN IP plus localhost / 127.0.0.1 so the same
    cert works for the operator's desktop and the phone on the LAN.
    """
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"

    if cert_path.exists() and key_path.exists() and not regenerate:
        if _cert_covers_ip(cert_path, lan_ip):
            return cert_path, key_path
        # SAN stale — regenerate transparently.

    key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "idrone.local"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "iDrone Simulator"),
        ]
    )
    san = x509.SubjectAlternativeName(
        [
            x509.DNSName("localhost"),
            x509.DNSName("idrone.local"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            x509.IPAddress(ipaddress.IPv4Address(lan_ip)),
        ]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(san, critical=False)
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def _cert_covers_ip(cert_path: Path, lan_ip: str) -> bool:
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        ips = [str(v) for v in ext.value.get_values_for_type(x509.IPAddress)]
        return lan_ip in ips
    except Exception:
        return False
