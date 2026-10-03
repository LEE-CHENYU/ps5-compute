"""Private console settings shared by the uploader and local dashboard."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_settings():
    path = ROOT / 'config.local.json'
    config = json.loads(path.read_text()) if path.exists() else {}
    host = os.environ.get('PS5_HOST', config.get('ps5_host', '')).strip()
    if any(c.isspace() or ord(c) < 32 for c in host):
        raise ValueError('PS5_HOST must be a hostname or IP address')
    result = {'host': host}
    for key, default in [('ftp_port', 2121), ('shell_port', 2323)]:
        value = int(os.environ.get('PS5_' + key.upper(), config.get(key, default)))
        if not 1 <= value <= 65535:
            raise ValueError(f'{key} must be between 1 and 65535')
        result[key] = value
    return result


def require_host():
    config = load_settings()
    if not config['host']:
        raise ValueError('Set PS5_HOST or ps5_host in config.local.json first')
    return config
