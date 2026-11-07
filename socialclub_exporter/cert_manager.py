import subprocess
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from mitmproxy.certs import CertStore


class CertError(Exception):
    pass


@dataclass(frozen=True)
class CertStatus:
    cert_path: Path
    thumbprint: str
    installed: bool


def ensure_ca(confdir: Path) -> Path:
    confdir = Path(confdir)
    confdir.mkdir(parents=True, exist_ok=True)
    CertStore.from_store(confdir, "mitmproxy", 2048)
    cert_path = confdir / "mitmproxy-ca-cert.cer"
    if not cert_path.exists():
        raise CertError("mitmproxy CA certificate was not generated")
    return cert_path


def cert_thumbprint(cert_path: Path) -> str:
    data = Path(cert_path).read_bytes()
    if b"-----BEGIN CERTIFICATE-----" in data:
        cert = x509.load_pem_x509_certificate(data)
    else:
        cert = x509.load_der_x509_certificate(data)
    return cert.fingerprint(hashes.SHA1()).hex().upper()


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def install_ca(cert_path: Path) -> str:
    result = _run(
        ["certutil", "-user", "-addstore", "-f", "Root", str(cert_path)]
    )
    if result.returncode != 0:
        raise CertError(result.stderr.strip() or "certutil addstore failed")
    return cert_thumbprint(cert_path)


def is_ca_installed(thumbprint: str) -> bool:
    result = _run(["certutil", "-user", "-store", "Root", thumbprint])
    return result.returncode == 0


def uninstall_ca(thumbprint: str) -> None:
    result = _run(["certutil", "-user", "-delstore", "Root", thumbprint])
    if result.returncode != 0:
        raise CertError(result.stderr.strip() or "certutil delstore failed")


def get_status(confdir: Path) -> CertStatus:
    cert_path = Path(confdir) / "mitmproxy-ca-cert.cer"
    if not cert_path.exists():
        return CertStatus(cert_path=cert_path, thumbprint="", installed=False)
    thumbprint = cert_thumbprint(cert_path)
    return CertStatus(
        cert_path=cert_path,
        thumbprint=thumbprint,
        installed=is_ca_installed(thumbprint),
    )


class CertManager:
    def __init__(self, confdir: Path):
        self.confdir = Path(confdir)

    def status(self) -> CertStatus:
        return get_status(self.confdir)

    def install(self) -> CertStatus:
        cert_path = ensure_ca(self.confdir)
        thumbprint = install_ca(cert_path)
        return CertStatus(cert_path=cert_path, thumbprint=thumbprint, installed=True)

    def uninstall(self) -> None:
        status = self.status()
        if status.installed:
            uninstall_ca(status.thumbprint)
