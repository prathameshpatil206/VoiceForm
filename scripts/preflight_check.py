#!/usr/bin/env python3
"""
VoiceForm — Organizer Preflight Check & Configuration Hygiene Validator
Validates environment configuration, Rime TTS parameters, and secret hygiene
to ensure full compliance with organizer requirements.
"""

import os
import sys
import re
from pathlib import Path

# Configure stdout for UTF-8 on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
ENV_FILE = BACKEND_DIR / ".env"
ROOT_ENV_EXAMPLE = REPO_ROOT / ".env.example"
BACKEND_ENV_EXAMPLE = BACKEND_DIR / ".env.example"
GITIGNORE = REPO_ROOT / ".gitignore"

def print_header(title: str):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def check_env_hygiene() -> bool:
    """Ensure example files only contain placeholders and no real secrets."""
    print_header("1. Secret & Configuration Hygiene Check")
    passed = True

    # 1. Check .gitignore
    if not GITIGNORE.exists():
        print("[FAIL] .gitignore is missing!")
        return False
    
    gitignore_text = GITIGNORE.read_text(encoding="utf-8")
    if not any(pattern in gitignore_text for pattern in [".env", "backend/.env", "*.env"]):
        print("[FAIL] .gitignore does not ignore .env files!")
        passed = False
    else:
        print("[PASS] .gitignore correctly ignores sensitive .env files.")

    # 2. Check example files for leaked secrets
    secret_patterns = [
        re.compile(r"gsk_[a-zA-Z0-9]{20,}"),
        re.compile(r"sk-[a-zA-Z0-9]{20,}"),
        re.compile(r"xDoik[a-zA-Z0-9]{20,}"),
    ]

    for example_file in [ROOT_ENV_EXAMPLE, BACKEND_ENV_EXAMPLE]:
        if not example_file.exists():
            print(f"[FAIL] Missing example environment file: {example_file.name}")
            passed = False
            continue

        content = example_file.read_text(encoding="utf-8")
        has_leak = False
        for pattern in secret_patterns:
            if pattern.search(content):
                print(f"[FAIL] Real secret detected in {example_file.name}!")
                has_leak = True
                passed = False
                break
        
        if not has_leak:
            print(f"[PASS] {example_file.name} contains placeholders only (zero secret leaks).")

    return passed

def check_rime_configuration() -> bool:
    """Validate Rime TTS configuration against hackathon specifications."""
    print_header("2. Rime TTS Configuration Validation")

    # Load environment from .env if present
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    api_key = os.getenv("RIME_API_KEY", "").strip()
    base_url = os.getenv("RIME_BASE_URL", "https://users.rime.ai/v1/rime-tts").strip()
    speaker = os.getenv("RIME_SPEAKER", "marsh").strip()
    model_id = os.getenv("RIME_MODEL_ID", "mist").strip()
    audio_format = os.getenv("RIME_AUDIO_FORMAT", "pcm").strip()
    sample_rate = os.getenv("RIME_SAMPLING_RATE", "16000").strip()

    checks = []

    # API Key check
    if not api_key or api_key == "your_rime_api_key_here":
        print("[WARN] RIME_API_KEY is unset or placeholder (Mock TTS will be used for local testing).")
    else:
        masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
        print(f"[PASS] RIME_API_KEY is configured ({masked}).")

    # Base URL check
    if base_url.startswith("http://") or base_url.startswith("https://"):
        print(f"[PASS] RIME_BASE_URL is valid: {base_url}")
        checks.append(True)
    else:
        print(f"[FAIL] RIME_BASE_URL must be a valid HTTP/HTTPS URL: {base_url}")
        checks.append(False)

    # Speaker check
    if speaker:
        print(f"[PASS] RIME_SPEAKER is configured: {speaker}")
        checks.append(True)
    else:
        print("[FAIL] RIME_SPEAKER cannot be empty.")
        checks.append(False)

    # Model ID check
    if model_id in ["mist", "v1", "fast"]:
        print(f"[PASS] RIME_MODEL_ID is valid: {model_id}")
        checks.append(True)
    else:
        print(f"[WARN] RIME_MODEL_ID is '{model_id}' (expected 'mist' or 'v1').")
        checks.append(True)

    # Audio Format check
    if audio_format.lower() in ["pcm", "mp3", "wav"]:
        print(f"[PASS] RIME_AUDIO_FORMAT is valid: {audio_format.lower()}")
        checks.append(True)
    else:
        print(f"[FAIL] Invalid RIME_AUDIO_FORMAT: {audio_format} (expected pcm, mp3, or wav)")
        checks.append(False)

    # Sampling Rate check
    try:
        sr = int(sample_rate)
        if sr in [8000, 16000, 22050, 24000, 44100, 48000]:
            print(f"[PASS] RIME_SAMPLING_RATE is valid: {sr} Hz")
            checks.append(True)
        else:
            print(f"[WARN] Unusual RIME_SAMPLING_RATE: {sr} Hz (standard is 16000 or 22050)")
            checks.append(True)
    except ValueError:
        print(f"[FAIL] RIME_SAMPLING_RATE must be an integer: {sample_rate}")
        checks.append(False)

    return all(checks)

def main():
    print(">> VoiceForm Hackathon Submission Preflight Check")
    hygiene_ok = check_env_hygiene()
    rime_ok = check_rime_configuration()

    print_header("3. Summary")
    if hygiene_ok and rime_ok:
        print("[OK] PREFLIGHT CHECK PASSED: Configuration and secrets satisfy all organizer requirements!\n")
        sys.exit(0)
    else:
        print("[ERROR] PREFLIGHT CHECK FAILED: Please resolve the issues above before submitting.\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
