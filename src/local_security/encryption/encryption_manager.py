"""
High-level Encryption Manager and disk encryption verification utilities.
"""
import math
from pathlib import Path


class EncryptionManager:
    """Verifies and audits database encryption state on disk and in memory."""

    @staticmethod
    def calculate_shannon_entropy(data: bytes) -> float:
        """
        Calculates Shannon entropy of byte data (0.0 to 8.0).
        Properly encrypted ciphertext typically exhibits high entropy (> 7.5).
        """
        if not data:
            return 0.0
        entropy = 0.0
        length = len(data)
        counts = [0] * 256
        for byte in data:
            counts[byte] += 1
        for count in counts:
            if count > 0:
                p = count / length
                entropy -= p * math.log2(p)
        return entropy

    @classmethod
    def verify_disk_encryption(cls, db_path: Path, forbidden_plaintexts: list[str]) -> tuple[bool, list[str]]:
        """
        Audits physical file on disk:
        1. Checks whether standard unencrypted SQLite magic header is present.
        2. Searches raw bytes for forbidden plaintext strings.
        3. Measures Shannon entropy of the file.
        Returns: (is_secure, audit_findings)
        """
        findings: list[str] = []
        if not db_path.exists():
            return False, ["Database file does not exist on disk."]

        file_bytes = db_path.read_bytes()
        if len(file_bytes) == 0:
            return False, ["Database file is 0 bytes."]

        # 1. Magic header check
        # Standard unencrypted SQLite always begins with 'SQLite format 3\x00'
        if file_bytes.startswith(b"SQLite format 3\x00"):
            findings.append("VULNERABILITY: Database file has plaintext SQLite header!")
        else:
            findings.append("CONFIRMED: Plaintext SQLite magic header is absent.")

        # 2. Plaintext leak check
        leaks_found = 0
        for text in forbidden_plaintexts:
            if text and text.encode("utf-8") in file_bytes:
                findings.append(f"VULNERABILITY: Plaintext leak detected for '{text}'!")
                leaks_found += 1

        if leaks_found == 0:
            findings.append("CONFIRMED: No sensitive plaintext strings found in raw disk ciphertext.")

        # 3. Entropy check
        entropy = cls.calculate_shannon_entropy(file_bytes)
        findings.append(f"Shannon entropy: {entropy:.3f} / 8.000")
        if entropy < 6.5:
            findings.append("WARNING: File entropy is lower than typical encrypted ciphertext.")
        else:
            findings.append("CONFIRMED: High entropy ciphertext detected.")

        is_secure = (not file_bytes.startswith(b"SQLite format 3\x00")) and (leaks_found == 0) and (entropy >= 6.5)
        return is_secure, findings
