"""Deterministic security-sensitivity classifier for diffs."""
from __future__ import annotations


def check_security_sensitive(diff: str) -> dict:
    matches: list[dict] = []
    categories: set[str] = set()
    for line in diff.splitlines():
        if not line or line[0] not in "+-":
            continue
        body = line[1:].lower()
        for category, keywords in SECURITY_KEYWORDS.items():
            for kw in keywords:
                if kw in body:
                    matches.append({"category": category, "keyword": kw, "line": line})
                    categories.add(category)
    return {
        "sensitive": bool(matches),
        "categories": sorted(categories),
        "matches": matches,
    }

SECURITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "auth": (
        "password", "passwd", "login", "logout", "session", "token", "jwt",
        "credential", "oauth", "cookie", "csrf", "authenticate", "authorize",
    ),
    "crypto": (
        "cipher", "encrypt", "decrypt", "hash", "hmac", "secret", "tls", "ssl",
        "rsa", "aes", "sha256", "bcrypt", "scrypt",
    ),
    "subprocess": (
        "subprocess", "os.system", "exec(", "eval(", "shell=True", "popen",
        "check_output", "check_call",
    ),
    "sql": (
        "select ", "insert ", "update ", "delete from", "drop table",
        "cursor", "execute(", "executemany",
    ),
    "network": (
        "http", "urllib", "requests.", "fetch(", "socket", "urlopen",
    ),
    "deserialization": (
        "pickle", "yaml.load", "marshal", "shelve",
    ),
    "filesystem": (
        "chmod", "setuid", "sudo", "/etc/", "os.path", "open(", "shutil.rmtree",
    ),
}
