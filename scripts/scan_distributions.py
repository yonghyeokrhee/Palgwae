"""Inspect release archives for required assets and private material."""

import pathlib
import re
import tarfile
import zipfile

repository = pathlib.Path.cwd()
sdists = list((repository / "dist").glob("*.tar.gz"))
if len(sdists) != 1:
    raise SystemExit(f"expected one sdist, found {len(sdists)}")

expected = {"CONTRIBUTING.md", "SECURITY.md"}
for directory in ("docs", "examples", "ontology", "web"):
    expected.update(
        path.relative_to(repository).as_posix()
        for path in (repository / directory).rglob("*")
        if path.is_file()
    )

with tarfile.open(sdists[0], "r:gz") as archive:
    members = [pathlib.PurePosixPath(name) for name in archive.getnames()]

roots = {member.parts[0] for member in members if member.parts}
if len(roots) != 1:
    raise SystemExit(f"expected one sdist root, found {sorted(roots)}")
root = roots.pop()
packaged = {member.relative_to(root).as_posix() for member in members if len(member.parts) > 1}
missing = sorted(expected - packaged)
if missing:
    raise SystemExit("sdist is missing required assets:\n" + "\n".join(missing))

print(f"verified {len(expected)} required assets in {sdists[0].name}")

patterns = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "credential assignment": re.compile(
        rb"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)"
        rb"\s*[:=]\s*['\"][^'\"\r\n]{8,}['\"]",
        re.IGNORECASE,
    ),
    "Unix home path": re.compile(rb"(?<![A-Za-z0-9_.-])/(?:Users|home)/[A-Za-z0-9._-]+/"),
    "Windows user path": re.compile(rb"(?i)\b[A-Z]:\\Users\\[^\\\r\n]+\\"),
    "private temporary path": re.compile(rb"/private/(?:tmp|var)/"),
}


def inspect(name, data):
    findings = []
    path = pathlib.PurePosixPath(name.replace("\\", "/"))
    if name.startswith(("/", "\\")) or ".." in path.parts:
        findings.append((name, "unsafe archive path"))
    for label, pattern in patterns.items():
        if pattern.search(data):
            findings.append((name, label))
    return findings


findings = []
archives = sorted(
    path
    for path in pathlib.Path("dist").iterdir()
    if path.name.endswith((".tar.gz", ".tgz")) or path.suffix == ".whl"
)
if not archives:
    raise SystemExit("no release archives found")
for archive_path in archives:
    if archive_path.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                if member.isfile():
                    extracted = archive.extractfile(member)
                    if extracted is not None:
                        findings.extend(inspect(member.name, extracted.read()))
    elif archive_path.suffix == ".whl":
        with zipfile.ZipFile(archive_path) as archive:
            for name in archive.namelist():
                if not name.endswith("/"):
                    findings.extend(inspect(name, archive.read(name)))

if findings:
    details = "\n".join(f"{archive_member}: {label}" for archive_member, label in findings)
    raise SystemExit("release archive privacy scan failed:\n" + details)

print(f"privacy scan passed for {len(archives)} release archives")
