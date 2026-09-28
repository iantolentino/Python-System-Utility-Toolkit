"""Download and verify installer assets hosted in a GitHub Release."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import time
import http.client
import urllib.error
import urllib.request
from pathlib import Path


class InstallerStoreError(RuntimeError):
    pass


def load_catalog(path: str | os.PathLike) -> dict:
    with open(path, encoding="utf-8-sig") as handle:
        catalog = json.load(handle)
    required = {"repository", "release_tag", "installers"}
    missing = required.difference(catalog)
    if missing:
        raise InstallerStoreError(f"Catalog is missing: {', '.join(sorted(missing))}")
    return catalog


def _release_base(catalog: dict) -> str:
    repository = catalog["repository"].strip("/")
    tag = catalog["release_tag"]
    return f"https://github.com/{repository}/releases/download/{tag}"


def _download_once(url: str, destination: Path, log=lambda message: None) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Python-System-Utility-Toolkit"})
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=120) as response, open(temporary, "wb") as output:
            total = int(response.headers.get("Content-Length", 0))
            received = 0
            last_report = -10
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                received += len(chunk)
                percent = int(received * 100 / total) if total else 0
                if total and percent >= last_report + 10:
                    log(f"Downloading {destination.name}: {percent}% ({received // 1048576} MB)")
                    last_report = percent
        os.replace(temporary, destination)
    except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:
        temporary.unlink(missing_ok=True)
        raise InstallerStoreError(f"Download failed: {url} ({exc})") from exc


def _download(url: str, destination: Path, log=lambda message: None) -> None:
    for attempt in range(1, 4):
        try:
            _download_once(url, destination, log)
            return
        except InstallerStoreError as exc:
            cause = exc.__cause__
            reason = getattr(cause, "reason", cause)
            if isinstance(reason, ssl.SSLCertVerificationError):
                raise InstallerStoreError("HTTPS certificate verification failed. Check the Windows date and time, then use Check / Sync Time and Retry Last Task. " + str(exc)) from exc
            if isinstance(cause, urllib.error.HTTPError) and cause.code not in (408, 429, 500, 502, 503, 504):
                raise
            if attempt == 3:
                raise InstallerStoreError("Download failed after 3 attempts. Check internet/proxy access and use Retry Last Task. " + str(exc)) from exc
            delay = 2 ** attempt
            log(f"Connection interrupted for {destination.name}. Retry {attempt + 1}/3 in {delay}s...")
            time.sleep(delay)


def _checksums(catalog: dict, cache_dir: Path) -> dict[str, str]:
    checksum_file = cache_dir / "SHA256SUMS"
    _download(f"{_release_base(catalog)}/SHA256SUMS", checksum_file)
    result = {}
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2:
            result[parts[1].lstrip("*")] = parts[0].lower()
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_installers(catalog: dict, cache_dir: str | os.PathLike, log=lambda message: None) -> list[dict]:
    """Return catalog entries with verified local_path values."""
    cache = Path(cache_dir) / catalog["release_tag"]
    cache.mkdir(parents=True, exist_ok=True)
    checksums = {entry["asset"]: entry["sha256"] for entry in catalog["installers"] if entry.get("sha256")}
    if len(checksums) != len(catalog["installers"]):
        checksums = _checksums(catalog, cache)
    prepared = []

    for entry in catalog["installers"]:
        filename = entry["asset"]
        if Path(filename).name != filename or "/" in filename or "\\" in filename:
            raise InstallerStoreError(f"Invalid installer filename: {filename}")
        expected = checksums.get(filename)
        if not expected:
            raise InstallerStoreError(f"SHA256SUMS has no checksum for {filename}")
        destination = cache / filename
        if not destination.exists() or sha256(destination) != expected:
            log(f"Downloading {entry['name']}...")
            _download(f"{_release_base(catalog)}/{filename}", destination, log)
        else:
            log(f"Using cached installer: {entry['name']}")
        if sha256(destination) != expected:
            destination.unlink(missing_ok=True)
            raise InstallerStoreError(f"Checksum verification failed for {filename}")
        prepared.append({**entry, "local_path": str(destination)})
        log(f"Verified SHA256: {entry['name']}")
    return prepared
