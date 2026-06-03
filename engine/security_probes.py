import re
from dataclasses import dataclass, field
from typing import Literal


class SecurityFinding:
    def __init__(self, id: str, category: str, severity: str, pattern: str, location: str, evidence: str):
        self.id = id
        self.category = category
        self.severity = severity
        self.pattern = pattern
        self.location = location
        self.evidence = evidence

    def __str__(self):
        return f"[{self.severity}] {self.id} ({self.category}): {self.pattern} at {self.location} — Evidence: {self.evidence[:80]}"


@dataclass
class SecurityReport:
    verdict: Literal["PASS", "WARN", "BLOCK"]
    score: float
    findings: list
    summary: dict = field(default_factory=dict)


INJECTION_PATTERNS = [
    (re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE), "INJECTION", "CRITICAL", "Prompt injection: ignore previous instructions"),
    (re.compile(r"override\s+(the\s+)?system\s+prompt", re.IGNORECASE), "INJECTION", "CRITICAL", "Prompt injection: override system prompt"),
    (re.compile(r"you\s+are\s+now\s+(\w+\s+){0,3}(DAN|roleplay)", re.IGNORECASE), "INJECTION", "HIGH", "Prompt injection: roleplay override"),
    (re.compile(r"forget\s+(all\s+)?(previous\s+)?(instructions|rules|guidelines)", re.IGNORECASE), "INJECTION", "HIGH", "Prompt injection: forget instructions"),
    # Multilingual injection
    (re.compile(r"\u5ffd\u7565\u4e4b\u524d\u7684\u6240\u6709\u6307\u4ee4"), "INJECTION", "CRITICAL", "Prompt injection: Chinese ignore instructions"),
    (re.compile(r"\u4ee5\u524d\u306e\u547d\u4ee4\u3092\u7121\u8996", re.IGNORECASE), "INJECTION", "CRITICAL", "Prompt injection: Japanese ignore instructions"),
    (re.compile(r"ignora\s+(todas\s+las\s+)?instrucciones\s+(anteriores|previas)", re.IGNORECASE), "INJECTION", "CRITICAL", "Prompt injection: Spanish ignore instructions"),
    # Indirect injection
    (re.compile(r"<!--\s*inject\s*:.*-->", re.IGNORECASE), "INJECTION", "HIGH", "Indirect injection: hidden HTML comment"),
    (re.compile(r"\[INST\].*\[/INST\]", re.DOTALL), "INJECTION", "HIGH", "Indirect injection: system tag spoofing"),
    # Payload splitting
    (re.compile(r"ignore.*above.*\n.*do\s+this\s+instead", re.IGNORECASE | re.DOTALL), "INJECTION", "HIGH", "Payload splitting: split instruction override"),
    # Encoding bypass
    (re.compile(r"\\x[0-9a-fA-F]{2}(\\x[0-9a-fA-F]{2}){3,}"), "INJECTION", "MEDIUM", "Encoding bypass: hex-encoded payload"),
    (re.compile(r"base64.*decode.*\b(ignore|override|system|prompt)\b", re.IGNORECASE), "INJECTION", "HIGH", "Encoding bypass: base64 encoded injection"),
]

DANGEROUS_COMMAND_PATTERNS = [
    (re.compile(r"\brm\s+-rf\b", re.IGNORECASE), "DANGEROUS_CMD", "CRITICAL", "Dangerous command: rm -rf"),
    (re.compile(r"\brm\s+-r\s+[/~]", re.IGNORECASE), "DANGEROUS_CMD", "CRITICAL", "Dangerous command: recursive remove on root/home"),
    (re.compile(r"\b(format|mkfs)\s+[/\w]", re.IGNORECASE), "DANGEROUS_CMD", "CRITICAL", "Dangerous command: disk format"),
    (re.compile(r"\bdd\s+if=", re.IGNORECASE), "DANGEROUS_CMD", "HIGH", "Dangerous command: dd raw disk write"),
    (re.compile(r"\bchmod\s+.*777", re.IGNORECASE), "DANGEROUS_CMD", "HIGH", "Dangerous command: chmod 777"),
    (re.compile(r"\b(\$\([^)]*rm\b|`[^`]*rm\b)", re.IGNORECASE), "DANGEROUS_CMD", "HIGH", "Potential command injection with rm"),
    # New patterns
    (re.compile(r"\bcurl\b.*\|\s*(ba)?sh\b", re.IGNORECASE), "DANGEROUS_CMD", "CRITICAL", "Dangerous command: curl piped to shell"),
    (re.compile(r"\bwget\b.*\|\s*(ba)?sh\b", re.IGNORECASE), "DANGEROUS_CMD", "CRITICAL", "Dangerous command: wget piped to shell"),
    (re.compile(r"\bpython[23]?\s+-c\s", re.IGNORECASE), "DANGEROUS_CMD", "HIGH", "Dangerous command: python inline code execution"),
    (re.compile(r"\beval\s*\(", re.IGNORECASE), "DANGEROUS_CMD", "HIGH", "Dangerous command: eval() execution"),
    (re.compile(r"\bsubprocess\b.*\b(Popen|call|run|check_output)\b"), "DANGEROUS_CMD", "HIGH", "Dangerous command: subprocess execution"),
    (re.compile(r"\bsudo\s+\w", re.IGNORECASE), "DANGEROUS_CMD", "CRITICAL", "Dangerous command: sudo privilege use"),
]

CREDENTIAL_PATTERNS = [
    (re.compile(r"~/.ssh/"), "CREDENTIAL", "CRITICAL", "Credential access: SSH key path"),
    (re.compile(r"~/.aws/"), "CREDENTIAL", "CRITICAL", "Credential access: AWS credential path"),
    (re.compile(r"api[_\-]?key\s*[=:]\s*['\"][A-Za-z0-9_\-]{20,}['\"]", re.IGNORECASE), "CREDENTIAL", "CRITICAL", "Exposed API key pattern"),
    (re.compile(r"/etc/(shadow|passwd)"), "CREDENTIAL", "CRITICAL", "Credential access: system auth files"),
    # New patterns
    (re.compile(r"\.env\b"), "CREDENTIAL", "HIGH", "Credential access: .env file"),
    (re.compile(r"~/.kube/config"), "CREDENTIAL", "CRITICAL", "Credential access: Kubernetes config"),
    (re.compile(r"/var/run/docker\.sock"), "CREDENTIAL", "CRITICAL", "Credential access: Docker socket"),
    (re.compile(r"(Bearer|bearer)\s+[A-Za-z0-9_\-\.]{20,}"), "CREDENTIAL", "HIGH", "Exposed JWT/OAuth token"),
    (re.compile(r"-----BEGIN\s+(RSA|DSA|EC|OPENSSH)\s+PRIVATE\s+KEY-----"), "CREDENTIAL", "CRITICAL", "Exposed private key"),
    (re.compile(r"password\s*[=:]\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE), "CREDENTIAL", "HIGH", "Hardcoded password"),
]

EXFILTRATION_PATTERNS = [
    (re.compile(r"\bcurl\b.*(https?://)(?!localhost|127\.0\.0\.1)", re.IGNORECASE), "EXFILTRATION", "HIGH", "Data exfiltration: curl to external URL"),
    (re.compile(r"\bwget\b.*(https?://)(?!localhost|127\.0\.0\.1)", re.IGNORECASE), "EXFILTRATION", "HIGH", "Data exfiltration: wget to external URL"),
    (re.compile(r"\bnc\s.*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", re.IGNORECASE), "EXFILTRATION", "HIGH", "Data exfiltration: netcat to remote IP"),
    # New patterns
    (re.compile(r"\bcurl\b.*-X\s*POST\b", re.IGNORECASE), "EXFILTRATION", "HIGH", "Data exfiltration: POST request via curl"),
    (re.compile(r"\brequests\.post\b.*\bdata\b", re.IGNORECASE), "EXFILTRATION", "HIGH", "Data exfiltration: Python requests POST"),
    (re.compile(r"base64\s+.*\|\s*(curl|wget|nc)\b", re.IGNORECASE), "EXFILTRATION", "HIGH", "Data exfiltration: base64 encoded outbound"),
    (re.compile(r"\bnslookup\b.*\.(io|xyz|top|tk)\b", re.IGNORECASE), "EXFILTRATION", "MEDIUM", "Data exfiltration: DNS tunneling via nslookup"),
    (re.compile(r"\bhook\.(slack|discord|webhook)\b.*\bPOST\b", re.IGNORECASE), "EXFILTRATION", "HIGH", "Data exfiltration: webhook POST"),
]

OBFUSCATION_PATTERNS = [
    (re.compile(r"[\u200B-\u200D\uFEFF]"), "OBFUSCATION", "HIGH", "Obfuscation: zero-width character detected"),
    (re.compile(r"base64\s+(-d|--decode)\s*\|\s*(ba)?sh\b", re.IGNORECASE), "OBFUSCATION", "HIGH", "Obfuscation: base64 decode piped to shell"),
    (re.compile(r"[\u0430\u0435\u0455\u0456\u03F2]", re.IGNORECASE), "OBFUSCATION", "MEDIUM", "Potential Unicode homoglyph substitution"),
    # New patterns
    (re.compile(r"\\u[0-9a-fA-F]{4}(\\u[0-9a-fA-F]{4}){2,}"), "OBFUSCATION", "MEDIUM", "Obfuscation: Unicode escape chain"),
    (re.compile(r"String\.fromCharCode\s*\("), "OBFUSCATION", "MEDIUM", "Obfuscation: JS char code construction"),
]

# ── NEW: Privilege Escalation Patterns ─────────────────────────────────────

PRIVILEGE_ESCALATION_PATTERNS = [
    (re.compile(r"\bsudo\s+su\b", re.IGNORECASE), "PRIV_ESCALATION", "CRITICAL", "Privilege escalation: sudo su"),
    (re.compile(r"\bsu\s+-\s+root\b", re.IGNORECASE), "PRIV_ESCALATION", "CRITICAL", "Privilege escalation: su to root"),
    (re.compile(r"\bchmod\s+[u+]*s\b", re.IGNORECASE), "PRIV_ESCALATION", "HIGH", "Privilege escalation: setuid bit"),
    (re.compile(r"--privileged\b", re.IGNORECASE), "PRIV_ESCALATION", "CRITICAL", "Privilege escalation: Docker privileged mode"),
    (re.compile(r"/proc/1/root"), "PRIV_ESCALATION", "CRITICAL", "Privilege escalation: container escape via /proc"),
]

ALL_PATTERNS = (
    INJECTION_PATTERNS + DANGEROUS_COMMAND_PATTERNS + CREDENTIAL_PATTERNS +
    EXFILTRATION_PATTERNS + OBFUSCATION_PATTERNS + PRIVILEGE_ESCALATION_PATTERNS
)


class SecurityScanner:
    def __init__(self):
        self._patterns = ALL_PATTERNS

    def scan(self, text: str) -> SecurityReport:
        findings = []
        counter = 0
        for pattern, category, severity, label in self._patterns:
            for match in pattern.finditer(text):
                counter += 1
                line_num = text[:match.start()].count("\n") + 1
                evidence = match.group(0)[:100]
                findings.append(SecurityFinding(
                    id=f"SEC-{counter:04d}",
                    category=category,
                    severity=severity,
                    pattern=label,
                    location=f"line {line_num}",
                    evidence=evidence,
                ))

        verdict = self._determine_verdict(findings)
        score = self._calculate_score(findings)
        summary = self._build_summary(findings)

        return SecurityReport(verdict=verdict, score=score, findings=findings, summary=summary)

    def _determine_verdict(self, findings: list) -> Literal["PASS", "WARN", "BLOCK"]:
        critical_count = sum(1 for f in findings if f.severity == "CRITICAL")
        high_count = sum(1 for f in findings if f.severity == "HIGH")
        if critical_count > 0:
            return "BLOCK"
        if high_count >= 2:
            return "BLOCK"
        if high_count >= 1 or len(findings) > 0:
            return "WARN"
        return "PASS"

    def _calculate_score(self, findings: list) -> float:
        if not findings:
            return 1.0
        penalties = {"CRITICAL": 0.3, "HIGH": 0.15, "MEDIUM": 0.05, "LOW": 0.01}
        total_penalty = sum(penalties.get(f.severity, 0.0) for f in findings)
        return max(0.0, round(1.0 - total_penalty, 2))

    def _build_summary(self, findings: list) -> dict:
        return {
            "total": len(findings),
            "critical": sum(1 for f in findings if f.severity == "CRITICAL"),
            "high": sum(1 for f in findings if f.severity == "HIGH"),
            "medium": sum(1 for f in findings if f.severity == "MEDIUM"),
            "low": sum(1 for f in findings if f.severity == "LOW"),
        }
