import re


def valid_nip(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{10}", value) or len(set(value)) == 1:
        return False
    checksum = (
        sum(int(n) * w for n, w in zip(value[:9], (6, 5, 7, 2, 3, 4, 5, 6, 7), strict=True)) % 11
    )
    return checksum != 10 and checksum == int(value[-1])
