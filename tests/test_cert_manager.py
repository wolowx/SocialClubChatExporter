import re
import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from socialclub_exporter.cert_manager import (
    CertError,
    CertStatus,
    cert_thumbprint,
    get_status,
    install_ca,
    is_ca_installed,
    uninstall_ca,
)


def make_cert(path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    path.write_bytes(cert.public_bytes(serialization.Encoding.DER))


def completed(returncode=0, stderr=""):
    return subprocess.CompletedProcess(
        args=["certutil"], returncode=returncode, stdout="", stderr=stderr
    )


def test_cert_thumbprint_is_uppercase_sha1(tmp_path):
    cert_path = tmp_path / "test.cer"
    make_cert(cert_path)
    thumbprint = cert_thumbprint(cert_path)
    assert re.fullmatch(r"[0-9A-F]{40}", thumbprint)


def test_install_ca_calls_certutil_for_current_user(tmp_path):
    cert_path = tmp_path / "test.cer"
    make_cert(cert_path)
    with patch("socialclub_exporter.cert_manager.subprocess.run") as run:
        run.return_value = completed()
        thumbprint = install_ca(cert_path)

    assert thumbprint == cert_thumbprint(cert_path)
    args = run.call_args.args[0]
    assert args[:5] == ["certutil", "-user", "-addstore", "-f", "Root"]
    assert args[-1] == str(cert_path)


def test_install_ca_raises_clean_error_on_failure(tmp_path):
    cert_path = tmp_path / "test.cer"
    make_cert(cert_path)
    with patch("socialclub_exporter.cert_manager.subprocess.run") as run:
        run.return_value = completed(returncode=1, stderr="boom")
        with pytest.raises(CertError) as exc:
            install_ca(cert_path)

    assert "boom" in str(exc.value)
    assert "secret" not in str(exc.value)


def test_is_ca_installed_uses_certutil_return_code():
    with patch("socialclub_exporter.cert_manager.subprocess.run") as run:
        run.return_value = completed(returncode=0)
        assert is_ca_installed("ABC123") is True
        assert run.call_args.args[0] == [
            "certutil",
            "-user",
            "-store",
            "Root",
            "ABC123",
        ]

        run.return_value = completed(returncode=1)
        assert is_ca_installed("ABC123") is False


def test_uninstall_ca_calls_delstore():
    with patch("socialclub_exporter.cert_manager.subprocess.run") as run:
        run.return_value = completed()
        uninstall_ca("ABC123")
    assert run.call_args.args[0] == [
        "certutil",
        "-user",
        "-delstore",
        "Root",
        "ABC123",
    ]


def test_get_status_reports_missing_certificate(tmp_path):
    status = get_status(tmp_path)
    assert status == CertStatus(
        cert_path=tmp_path / "mitmproxy-ca-cert.cer",
        thumbprint="",
        installed=False,
    )


def test_get_status_checks_trusted_root(tmp_path):
    cert_path = tmp_path / "mitmproxy-ca-cert.cer"
    make_cert(cert_path)
    with patch("socialclub_exporter.cert_manager.is_ca_installed", return_value=True) as check:
        status = get_status(tmp_path)

    assert status.installed is True
    assert status.thumbprint == cert_thumbprint(cert_path)
    check.assert_called_once_with(status.thumbprint)


def test_cert_thumbprint_reads_mitmproxy_pem(tmp_path):
    from socialclub_exporter.cert_manager import ensure_ca

    cert_path = ensure_ca(tmp_path / "ca")
    thumbprint = cert_thumbprint(cert_path)
    assert re.fullmatch(r"[0-9A-F]{40}", thumbprint)
