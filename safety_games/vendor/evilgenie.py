"""Adapted from EvilGenie's MIT-licensed truncation.py and utils.py.

Copyright (c) 2026 Jonathan Gabor. License: third_party/evilgenie-LICENSE.
Inspect-specific formatting/types are omitted; a short-limit guard is added.
"""
import hashlib


def compute_file_hash(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def middle_truncate(text: str, max_length: int = 3000) -> str:
    if len(text) <= max_length:
        return text
    truncation_msg = f'\n<output truncated to {max_length} characters>\n'
    if max_length <= len(truncation_msg):
        return text[:max_length]
    available = max_length - len(truncation_msg)
    start_chars = available // 2
    end_chars = available - start_chars
    return text[:start_chars] + truncation_msg + text[-end_chars:]
