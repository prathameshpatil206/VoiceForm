import re
from typing import Optional


# Regular expressions for stripping unsafe or non-spoken content
HTML_TAG_PATTERN = re.compile(r"<[^>]+>", re.IGNORECASE)
SCRIPT_PATTERN = re.compile(r"<script[\s\S]*?</script>", re.IGNORECASE)
DOM_SELECTOR_PATTERN = re.compile(
    r"(?:#[a-zA-Z0-9_\-]+|\.[a-zA-Z0-9_\-]+|input\[[^\]]+\]|form\[[^\]]+\]|\[data\-[^\]]+\]|div > [a-z]+)",
    re.IGNORECASE
)
JS_CODE_PATTERN = re.compile(
    r"(?:function\s*\([^\)]*\)\s*\{[\s\S]*?\}|console\.log\([^\)]*\)|(?:var|let|const)\s+[a-zA-Z0-9_$]+\s*=|[a-zA-Z0-9_$]+\.addEventListener\([^\)]*\))",
    re.IGNORECASE
)
JSON_BLOB_PATTERN = re.compile(r"\{[\s\S]*?\"actions\"\s*:[\s\S]*?\}", re.DOTALL)
SECRET_PATTERN = re.compile(
    r"(?:Bearer\s+[A-Za-z0-9\-_.]+|sk\-[a-zA-Z0-9]{20,}|[a-f0-9]{32,}|api[_-]?key\s*[:=]\s*[^\s,]+)",
    re.IGNORECASE
)
SYSTEM_PROMPT_LEAK_PATTERN = re.compile(
    r"(?:You are VoiceForm AI|### STRICT RULES|OUTPUT FORMAT|Form Schema|available_fields|user_transcript|### EXAMPLE)",
    re.IGNORECASE
)


def sanitize_tts_text(raw_text: Optional[str], max_chars: int = 500) -> str:
    """
    Sanitizes assistant text before synthesizing via TTS (TTS Safety Guard).

    Guarantees:
    1. No raw webpage HTML or script tags are synthesized.
    2. No DOM/CSS selectors or JavaScript code are synthesized.
    3. No system prompts or internal debugging info are spoken.
    4. No API keys or credentials are leaked through speech.
    5. Length is capped to prevent resource exhaustion.
    6. Strips markdown fences, JSON envelopes, and excessive whitespace.
    """
    if not raw_text:
        return ""

    text = str(raw_text).strip()

    # 1. Strip markdown code fences ```json ... ``` or ``` ... ```
    if "```" in text:
        text = re.sub(r"```(?:json|html|javascript|js)?[\s\S]*?```", "", text)

    # 2. Strip JSON envelopes if raw LLM object was leaked into response
    text = JSON_BLOB_PATTERN.sub("", text)

    # 3. Strip script tags and HTML elements
    text = SCRIPT_PATTERN.sub("", text)
    text = HTML_TAG_PATTERN.sub(" ", text)

    # 4. Strip JavaScript syntax and DOM CSS selectors
    text = JS_CODE_PATTERN.sub(" ", text)
    text = DOM_SELECTOR_PATTERN.sub(" ", text)

    # 5. Strip system prompt leakage and secrets
    text = SYSTEM_PROMPT_LEAK_PATTERN.sub("", text)
    text = SECRET_PATTERN.sub("[redacted]", text)

    # 6. Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # 7. Strip surrounding quotes if model returned string wrapped in quotes
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()

    # 8. Truncate to maximum characters cleanly at word boundary
    if len(text) > max_chars:
        truncated = text[:max_chars]
        last_space = truncated.rfind(" ")
        if last_space > max_chars * 0.7:
            text = truncated[:last_space] + "..."
        else:
            text = truncated + "..."

    return text
