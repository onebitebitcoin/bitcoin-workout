"""Best-effort subtitle generation for uploaded videos.

This module intentionally uses only stdlib + system ffmpeg/ffprobe so it fits the
existing worker runtime. OpenAI transcription is optional: if OPENAI_API_KEY is
missing or the API fails, callers receive a failed result and the upload flow can
continue without subtitles.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import R2_BUCKET_NAME, R2_PUBLIC_URL

logger = logging.getLogger(__name__)

OPENAI_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"
DEFAULT_TRANSCRIPTION_MODEL = os.environ.get("OPENAI_TRANSCRIPTION_MODEL", "whisper-1")
DEFAULT_TRANSCRIPTION_LANGUAGE = os.environ.get("OPENAI_TRANSCRIPTION_LANGUAGE", "ko")
# Whisper hallucinates stock YouTube-outro phrases (e.g. "시청해주셔서 감사합니다") on
# silent/ambiguous audio. A topic-priming prompt + temperature=0 measurably reduces it.
DEFAULT_TRANSCRIPTION_PROMPT = os.environ.get(
    "OPENAI_TRANSCRIPTION_PROMPT",
    "이것은 사용자가 직접 녹음한 일상 기록 음성 메모입니다. 실제로 들리는 발화만 받아 적으세요.",
)
DEFAULT_TRANSCRIPTION_TEMPERATURE = float(os.environ.get("OPENAI_TRANSCRIPTION_TEMPERATURE", "0"))
SUBTITLE_ENABLED = os.environ.get("SUBTITLE_ENABLED", "1").lower() not in {"0", "false", "no", "off"}
SUBTITLE_MAX_DURATION_SEC = float(os.environ.get("SUBTITLE_MAX_DURATION_SEC", "65"))
SUBTITLE_HTTP_TIMEOUT_SEC = int(os.environ.get("SUBTITLE_HTTP_TIMEOUT_SEC", "300"))
SUBTITLE_SILENCE_NOISE_DB = float(os.environ.get("SUBTITLE_SILENCE_NOISE_DB", "-30"))
SUBTITLE_SILENCE_MIN_DURATION_SEC = float(os.environ.get("SUBTITLE_SILENCE_MIN_DURATION_SEC", "1.0"))
SUBTITLE_BURN_IN_FONT_SIZE = int(os.environ.get("SUBTITLE_BURN_IN_FONT_SIZE", "14"))
SUBTITLE_BURN_IN_MARGIN_V = int(os.environ.get("SUBTITLE_BURN_IN_MARGIN_V", "90"))
# 좌우 여백(px, libass PlayRes 좌표계). 세로 영상에서 자막이 화면 끝까지 퍼져
# 좌우가 잘리는 것을 막기 위해 안쪽으로 들인다. (이전 하드코딩 30 → 50)
SUBTITLE_BURN_IN_MARGIN_H = int(os.environ.get("SUBTITLE_BURN_IN_MARGIN_H", "50"))
# ASS alpha is inverse opacity: 00 opaque, FF transparent. 20% transparent = 80% opaque.
SUBTITLE_BURN_IN_BACK_ALPHA_HEX = os.environ.get("SUBTITLE_BURN_IN_BACK_ALPHA_HEX", "33")
# Whisper verbose_json includes no_speech_prob, avg_logprob, compression_ratio per segment.
# Segments are dropped if ANY condition is met:
#   • no_speech_prob     >= 0.45  → Whisper thinks there's no speech
#   • avg_logprob        < -0.75  → model is uncertain → likely hallucination
#   • compression_ratio  > 2.4   → repetitive output (music/noise hallucination pattern)
#   • chars_per_sec      < 2.0   → too few chars for segment duration (e.g. "유료광고" hallucination)
# After per-segment filtering: if avg no_speech_prob across all segments > 0.45, skip all.
SUBTITLE_NO_SPEECH_THRESHOLD = float(os.environ.get("SUBTITLE_NO_SPEECH_THRESHOLD", "0.45"))
SUBTITLE_AVG_LOGPROB_THRESHOLD = float(os.environ.get("SUBTITLE_AVG_LOGPROB_THRESHOLD", "-0.75"))
SUBTITLE_COMPRESSION_RATIO_MAX = float(os.environ.get("SUBTITLE_COMPRESSION_RATIO_MAX", "2.4"))
SUBTITLE_AVG_NO_SPEECH_GLOBAL_THRESHOLD = float(os.environ.get("SUBTITLE_AVG_NO_SPEECH_GLOBAL_THRESHOLD", "0.45"))
SUBTITLE_MIN_CHARS_PER_SEC = float(os.environ.get("SUBTITLE_MIN_CHARS_PER_SEC", "2.0"))
# English text has more characters per second than Korean (Latin charset density).
# Apply a ~2.5x multiplier so the chars_per_sec filter does not over-drop English.
SUBTITLE_MIN_CHARS_PER_SEC_EN = float(os.environ.get("SUBTITLE_MIN_CHARS_PER_SEC_EN", "5.0"))

# Hallucination signatures: each entry is a tuple of tokens that must ALL appear
# in the normalised text to flag a segment as a YouTube-outro hallucination.
# Whisper renders these as "구독, 좋아요, 댓글 부탁드립니다" or "구독과 좋아요" etc.,
# so substring matching on a single fixed phrase ("구독과 좋아요") missed the
# comma-separated form. Token co-occurrence catches every separator/조사 variant.
_HALLUCINATION_SIGNATURES_KO: tuple[tuple[str, ...], ...] = (
    ("구독", "좋아요"),
    ("구독", "부탁"),
    ("좋아요", "부탁"),
    ("구독", "알림"),
    ("좋아요", "댓글"),
    ("시청", "감사"),
    ("채널", "구독"),
    ("다음", "영상", "만나"),
)
# English hallucination signatures (YouTube-outro patterns)
_HALLUCINATION_SIGNATURES_EN: tuple[tuple[str, ...], ...] = (
    ("subscribe",),
    ("thanks", "watching"),
    ("like", "subscribe"),
    ("see", "next", "video"),
    ("turn", "notification"),
    ("hit", "bell"),
)

# Collapse every non-word char (punctuation, whitespace) so that token membership
# is independent of commas, particles, and spacing.
_NON_WORD_RE = re.compile(r"[^0-9a-z가-힣]+")

# Whisper verbose_json reports the detected language as a full name ("english",
# "korean"), while the UI/API passes short codes ("en", "ko", "auto"). Normalise
# both forms to one code so every language-aware filter compares reliably.
_LANGUAGE_ALIASES = {
    "en": "en", "english": "en", "eng": "en",
    "ko": "ko", "korean": "ko", "kor": "ko",
}


def _effective_language(language: str | None, detected_language: str | None = None) -> str | None:
    """Resolve the language used by language-aware filters.

    'auto' resolves to the Whisper-detected language when available, and both
    full-name and short-code forms are normalised ('english' → 'en'). Without a
    detection the value is returned as-is (so 'auto' stays the conservative KO
    default downstream).
    """
    raw = detected_language if (language == "auto" and detected_language) else language
    if not raw:
        return raw
    lowered = raw.lower()
    return _LANGUAGE_ALIASES.get(lowered, lowered)


def _normalize_for_match(text: str) -> str:
    return _NON_WORD_RE.sub(" ", text.lower()).strip()


def _contains_hallucination_phrase(
    text: str, language: str | None, detected_language: str | None = None
) -> bool:
    """Return True if text matches a known hallucination signature (token co-occurrence).

    The signature set is language-aware via the *effective* language: an 'auto'
    job that Whisper detected as English must use the English signatures, else
    English YouTube-outro hallucinations slip through (the KO set was previously
    applied to every value that was not literally 'en').
    """
    norm = _normalize_for_match(text)
    effective = _effective_language(language, detected_language)
    signatures = _HALLUCINATION_SIGNATURES_EN if effective == "en" else _HALLUCINATION_SIGNATURES_KO
    return any(all(token in norm for token in signature) for signature in signatures)


def _chars_per_sec_threshold(
    language: str | None,
    detected_language: str | None = None,
    ko_default: float = SUBTITLE_MIN_CHARS_PER_SEC,
) -> float:
    """Return the appropriate chars_per_sec threshold for the given language.

    'auto' resolves to the Whisper-detected language when available.
    English gets a ~2.5x higher threshold than Korean because Latin text
    has more characters per second than Korean syllable blocks. ``ko_default``
    lets the caller override the non-English (Korean) threshold.
    """
    if _effective_language(language, detected_language) == "en":
        return SUBTITLE_MIN_CHARS_PER_SEC_EN
    return ko_default


@dataclass(frozen=True)
class SubtitleResult:
    status: str
    subtitle_r2_key: str | None = None
    subtitle_url: str | None = None
    subtitle_text: str | None = None
    burned_video_r2_key: str | None = None
    burned_video_url: str | None = None
    error: str | None = None
    metrics: dict[str, Any] | None = None


def _make_tmp(suffix: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        return f.name


def _run_cmd(cmd: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed exit={result.returncode}: {' '.join(cmd)}\n"
            f"stderr={result.stderr[-1000:]}"
        )
    return result


def _ensure_tool(name: str) -> None:
    if not shutil.which(name):
        raise RuntimeError(f"required binary not found: {name}")


_DECODE_TIME_RE = re.compile(r"time=\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")


def _probe_duration_by_decode(path: str) -> float:
    """Recover duration by fully decoding the stream and reading the last timestamp.

    MediaRecorder webm/opus uploads frequently lack duration metadata (it stays
    'N/A' until the container is remuxed), so ffprobe's header probes return 0.
    Decoding to null streams the whole file and ffmpeg prints a running
    ``time=HH:MM:SS.ss`` on stderr; the maximum is the real duration. Best-effort:
    any failure yields 0.0 so the caller can fall back to its own handling.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", path, "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("decode-based duration probe failed for %s: %s", path, exc)
        return 0.0
    last = 0.0
    for m in _DECODE_TIME_RE.finditer(result.stderr):
        seconds = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        last = max(last, seconds)
    return last


def _probe_duration(path: str) -> float:
    for extra in (
        ["-show_entries", "format=duration"],
        ["-select_streams", "v:0", "-show_entries", "stream=duration"],
        ["-select_streams", "a:0", "-show_entries", "stream=duration"],
    ):
        result = subprocess.run(
            ["ffprobe", "-v", "error"] + extra + ["-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        raw = result.stdout.strip() if result.returncode == 0 else ""
        if raw and raw != "N/A":
            try:
                value = float(raw)
                if value > 0:
                    return value
            except ValueError:
                pass
    # Header probes failed (e.g. MediaRecorder webm without duration metadata):
    # fall back to a decode pass so the silence guard is not silently disabled.
    return _probe_duration_by_decode(path)


def _has_audio_stream(video_path: str) -> bool:
    """Return True if the video contains at least one audio stream."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=index",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _extract_audio(video_path: str, audio_path: str) -> float:
    started = time.perf_counter()
    _run_cmd(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "aac",
            "-b:a", "128k",
            audio_path,
        ],
        timeout=300,
    )
    return time.perf_counter() - started


_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(-?[\d.]+)")


def _detect_silence_ranges(audio_path: str, duration: float) -> list[tuple[float, float]]:
    """Return [(start, end), ...] silent stretches via ffmpeg's silencedetect filter.

    Best-effort: detection failures should never block transcription, so any error
    here yields an empty list rather than raising.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-i", audio_path,
                "-af", f"silencedetect=noise={SUBTITLE_SILENCE_NOISE_DB}dB:d={SUBTITLE_SILENCE_MIN_DURATION_SEC}",
                "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("silence detection failed for %s: %s", audio_path, exc)
        return []

    ranges: list[tuple[float, float]] = []
    pending_start: float | None = None
    for line in result.stderr.splitlines():
        start_match = _SILENCE_START_RE.search(line)
        if start_match:
            pending_start = float(start_match.group(1))
            continue
        end_match = _SILENCE_END_RE.search(line)
        if end_match and pending_start is not None:
            ranges.append((pending_start, float(end_match.group(1))))
            pending_start = None
    if pending_start is not None and duration > pending_start:
        ranges.append((pending_start, duration))
    return ranges


def _encode_multipart(fields: dict[str, str], file_field: str, file_path: str) -> tuple[bytes, str]:
    boundary = f"----stackhealth-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode(),
            b"\r\n",
        ])
    file_name = Path(file_path).name
    parts.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\n'.encode(),
        b"Content-Type: audio/mp4\r\n\r\n",
        Path(file_path).read_bytes(),
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return b"".join(parts), boundary


def _transcribe_srt(
    audio_path: str,
    *,
    api_key: str,
    model: str,
    language: str | None,
    prompt: str | None = None,
    temperature: float | None = None,
) -> tuple[str, float]:
    fields = {"model": model, "response_format": "srt"}
    if language:
        fields["language"] = language
    if prompt:
        fields["prompt"] = prompt
    if temperature is not None:
        fields["temperature"] = str(temperature)
    body, boundary = _encode_multipart(fields, "file", audio_path)
    request = urllib.request.Request(
        OPENAI_TRANSCRIPTIONS_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=SUBTITLE_HTTP_TIMEOUT_SEC) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI transcription failed: HTTP {exc.code} {detail[:500]}") from exc
    return payload, time.perf_counter() - started


def _transcribe_verbose_json(
    audio_path: str,
    *,
    api_key: str,
    model: str,
    language: str | None,
    prompt: str | None = None,
    temperature: float | None = None,
) -> tuple[dict, float]:
    """Call Whisper with verbose_json to get per-segment no_speech_prob."""
    fields = {"model": model, "response_format": "verbose_json"}
    if language:
        fields["language"] = language
    if prompt:
        fields["prompt"] = prompt
    if temperature is not None:
        fields["temperature"] = str(temperature)
    body, boundary = _encode_multipart(fields, "file", audio_path)
    request = urllib.request.Request(
        OPENAI_TRANSCRIPTIONS_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=SUBTITLE_HTTP_TIMEOUT_SEC) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI transcription failed: HTTP {exc.code} {detail[:500]}") from exc
    return payload, time.perf_counter() - started


def _segments_to_srt(
    segments: list[dict],
    no_speech_threshold: float,
    avg_logprob_threshold: float,
    compression_ratio_max: float = 2.4,
    avg_no_speech_global_threshold: float = 0.45,
    min_chars_per_sec: float = 2.0,
    language: str | None = None,
    detected_language: str | None = None,
) -> str:
    """Convert verbose_json segments to SRT, dropping hallucinated/non-speech segments.

    Five per-segment filters (any match → drop):
      • no_speech_prob >= threshold        (Whisper sees no speech)
      • avg_logprob    <  threshold        (model is uncertain → hallucination)
      • compression_ratio > max            (repetitive output → music/noise hallucination)
      • chars_per_sec  <  min             (too sparse → stock-phrase hallucination;
                                           threshold is language-aware: EN ~2.5x KO)
      • hallucination phrase match         (known YouTube-outro stock phrases)

    One global filter: if the mean no_speech_prob across all segments exceeds the
    global threshold, the entire transcription is discarded as non-speech.
    """
    if not segments:
        return ""

    # Global check: average no_speech_prob across all segments
    mean_no_speech = sum(seg.get("no_speech_prob", 0.0) for seg in segments) / len(segments)
    if mean_no_speech >= avg_no_speech_global_threshold:
        return ""

    effective_min_cps = _chars_per_sec_threshold(language, detected_language, ko_default=min_chars_per_sec)

    kept: list[tuple[float, float, str]] = []
    for seg in segments:
        if seg.get("no_speech_prob", 0.0) >= no_speech_threshold:
            continue
        if seg.get("avg_logprob", 0.0) < avg_logprob_threshold:
            continue
        if seg.get("compression_ratio", 0.0) > compression_ratio_max:
            continue
        text = seg.get("text", "").strip()
        if not text:
            continue
        if _contains_hallucination_phrase(text, language, detected_language):
            continue
        seg_duration = float(seg.get("end", 0)) - float(seg.get("start", 0))
        if seg_duration > 0 and len(text) / seg_duration < effective_min_cps:
            continue
        kept.append((float(seg["start"]), float(seg["end"]), text))
    if not kept:
        return ""
    lines: list[str] = []
    for i, (start, end, text) in enumerate(kept, start=1):
        lines.append(str(i))
        lines.append(f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _filter_srt_by_silence(
    srt_text: str,
    silence_ranges: list[tuple[float, float]],
) -> tuple[str, int]:
    """Drop SRT cues whose midpoint falls within a detected silence range.

    Returns (filtered_srt, dropped_count).  When silence_ranges is empty
    the original text is returned unchanged.
    """
    if not silence_ranges or not srt_text.strip():
        return srt_text, 0

    def _midpoint_in_silence(start: float, end: float) -> bool:
        mid = (start + end) / 2.0
        return any(s <= mid <= e for s, e in silence_ranges)

    blocks = [b for b in srt_text.strip().split("\n\n") if b.strip()]
    kept_blocks: list[str] = []
    dropped = 0
    for block in blocks:
        lines = block.strip().splitlines()
        ts_line = next(
            (line for line in lines if _SRT_TIMESTAMP_LINE_RE.search(line)),
            None,
        )
        if ts_line is None:
            kept_blocks.append(block)
            continue
        m = _SRT_TIMESTAMP_LINE_RE.search(ts_line)
        if m is None:
            kept_blocks.append(block)
            continue
        start = _parse_srt_timestamp(m.group(1))
        end = _parse_srt_timestamp(m.group(2))
        if _midpoint_in_silence(start, end):
            dropped += 1
        else:
            kept_blocks.append(block)

    if dropped == 0:
        return srt_text, 0

    # Re-number cues from 1
    renumbered: list[str] = []
    for idx, block in enumerate(kept_blocks, start=1):
        lines = block.strip().splitlines()
        # Replace first numeric-only line with new index
        if lines and _SRT_INDEX_LINE_RE.match(lines[0]):
            lines[0] = str(idx)
        renumbered.append("\n".join(lines))
    return "\n\n".join(renumbered) + "\n", dropped


def _parse_srt_timestamp(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def _format_srt_timestamp(value: float) -> str:
    value = max(0.0, value)
    total_ms = round(value * 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _clamp_srt_to_duration(srt_text: str, duration: float) -> tuple[str, bool]:
    if duration <= 0:
        return srt_text, False
    changed = False

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        start = min(_parse_srt_timestamp(match.group(1)), duration)
        end = min(_parse_srt_timestamp(match.group(2)), duration)
        if end < start:
            end = start
        replacement = f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}"
        changed = changed or replacement != match.group(0)
        return replacement

    updated = re.sub(
        r"(\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2},\d{3})",
        replace,
        srt_text,
    )
    return updated, changed


_SRT_TIMESTAMP_LINE_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2},\d{3})"
)
_SRT_INDEX_LINE_RE = re.compile(r"^\d+\s*$")



def _srt_to_vtt(srt_text: str) -> str:
    timestamp_re = re.compile(
        r"(\d{2}:\d{2}:\d{2}),(\d{3})\s+-->\s+"
        r"(\d{2}:\d{2}:\d{2}),(\d{3})"
    )
    lines = [
        timestamp_re.sub(r"\1.\2 --> \3.\4", line)
        for line in srt_text.lstrip().splitlines()
    ]
    return "WEBVTT\n\n" + "\n".join(lines) + "\n"




def _escape_filter_path(path: str) -> str:
    # FFmpeg subtitles filter treats ':' and '\' specially. Single quotes are
    # not expected in our mktemp paths, but escape defensively.
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


FONT_SIZE_MAP = {"small": 14, "large": 18}
# 폰트가 클수록 한 줄 글자수를 줄여 자막이 항상 한 줄에 들어가게 한다(어절 중간 끊김 방지).
SUBTITLE_MAX_CHARS_MAP = {"small": 12, "large": 9}
ALIGNMENT_MAP = {"bottom": 2, "center": 10, "top": 6}
MARGIN_V_MAP = {"bottom": SUBTITLE_BURN_IN_MARGIN_V, "center": 0, "top": 40}


def _burn_subtitles_into_video(
    video_path: str,
    srt_path: str,
    output_path: str,
    font_size: int = SUBTITLE_BURN_IN_FONT_SIZE,
    alignment: int = 2,
    margin_v: int = SUBTITLE_BURN_IN_MARGIN_V,
    margin_h: int = SUBTITLE_BURN_IN_MARGIN_H,
) -> float:
    """Render subtitles onto video pixels with an 80% opaque black box."""
    started = time.perf_counter()
    style = ",".join([
        "BorderStyle=4",  # opaque box behind each subtitle cue
        f"BackColour=&H{SUBTITLE_BURN_IN_BACK_ALPHA_HEX}000000",
        "Outline=0",
        "Shadow=0",
        f"FontSize={font_size}",
        f"Alignment={alignment}",
        f"MarginV={margin_v}",
        f"MarginL={margin_h}",
        f"MarginR={margin_h}",
        "PrimaryColour=&H00FFFFFF",
        "WrapStyle=0",
    ])
    vf = f"subtitles='{_escape_filter_path(srt_path)}':force_style='{style}'"
    _run_cmd(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", vf,
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ],
        timeout=300,
    )
    return time.perf_counter() - started

def _plain_text_from_srt(srt_text: str) -> str:
    lines: list[str] = []
    timestamp_re = re.compile(r"\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}")
    for raw in srt_text.splitlines():
        line = raw.strip()
        if not line or line.isdigit() or timestamp_re.fullmatch(line):
            continue
        lines.append(line)
    return " ".join(lines).strip()


_SENTENCE_SPLIT_RE = re.compile(r"[^.!?。！？\n]+[.!?。！？]?")
# 한 cue = 한 줄로 만들어 libass의 글자단위 자동 줄바꿈(어절 중간 끊김)을 막는다.
# 14pt 기준 세로영상 한 줄에 안전하게 들어가는 폭. _chunk_by_chars가 어절(공백)
# 경계로 나누므로, 이 값을 넘는 문장은 어절 단위로 분할되어 다음 cue로 넘어간다.
TEXT_SUBTITLE_MAX_CHARS = 12
TEXT_SUBTITLE_MAX_INPUT = 500


def _chunk_by_chars(part: str, max_chars: int) -> list[str]:
    """한 조각을 공백 경계 기준 max_chars 이하 청크로 나눈다(긴 단어는 강제 절단)."""
    if len(part) <= max_chars:
        return [part]
    chunks: list[str] = []
    cur = ""
    for word in part.split(" "):
        cand = word if not cur else f"{cur} {word}"
        if len(cand) <= max_chars:
            cur = cand
            continue
        if cur:
            chunks.append(cur)
            cur = ""
        while len(word) > max_chars:
            chunks.append(word[:max_chars])
            word = word[max_chars:]
        cur = word
    if cur:
        chunks.append(cur)
    return chunks


def build_srt_from_text(text: str, total_sec: float, *, max_chars: int = TEXT_SUBTITLE_MAX_CHARS) -> str:
    """사용자가 입력한 운동 후기 텍스트를 영상 길이에 균등 분배한 SRT로 변환한다.

    - 줄바꿈/문장 종결부호로 1차 분할 후, 각 조각을 max_chars 이하로 재분할한다.
    - 조각 수 M으로 total_sec를 균등 분배한다(마지막 조각의 끝은 total_sec에 정확히 맞춤).
    - 빈 텍스트면 빈 문자열을 반환한다(자막 skip).
    """
    text = (text or "").strip()[:TEXT_SUBTITLE_MAX_INPUT]
    if not text:
        return ""

    segments: list[str] = []
    for piece in _SENTENCE_SPLIT_RE.findall(text):
        piece = " ".join(piece.split())  # 내부 공백/줄바꿈 정규화
        if piece:
            segments.extend(_chunk_by_chars(piece, max_chars))
    if not segments:
        return ""

    m = len(segments)
    per = (total_sec / m) if total_sec and total_sec > 0 else 2.0
    out: list[str] = []
    for i, seg in enumerate(segments):
        start = i * per
        end = total_sec if (i == m - 1 and total_sec and total_sec > 0) else (i + 1) * per
        out.append(str(i + 1))
        out.append(f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}")
        out.append(seg)
        out.append("")
    return "\n".join(out).strip() + "\n"


def burn_user_srt(
    r2,
    video_key: str,
    srt_key: str,
    *,
    font_size: int = SUBTITLE_BURN_IN_FONT_SIZE,
    alignment: int = 2,
    margin_v: int = SUBTITLE_BURN_IN_MARGIN_V,
) -> SubtitleResult:
    """사용자가 업로드한 SRT를 R2에서 다운로드해 영상에 burn-in한다."""
    tmp_video = tmp_srt = tmp_burned = None
    metrics: dict[str, Any] = {"source": "user_srt", "font_size": font_size, "alignment": alignment}
    try:
        _ensure_tool("ffmpeg")
        tmp_video = _make_tmp(".mp4")
        tmp_srt = _make_tmp(".srt")
        tmp_burned = _make_tmp(".mp4")

        resp = r2.get_object(Bucket=R2_BUCKET_NAME, Key=video_key)
        with open(tmp_video, "wb") as f:
            f.write(resp["Body"].read())

        resp = r2.get_object(Bucket=R2_BUCKET_NAME, Key=srt_key)
        srt_text = resp["Body"].read().decode("utf-8")

        duration = _probe_duration(tmp_video)
        if duration > 0:
            srt_text, _ = _clamp_srt_to_duration(srt_text, duration)

        subtitle_text = _plain_text_from_srt(srt_text)
        vtt_text = _srt_to_vtt(srt_text)

        subtitle_key = f"subtitles/s-{uuid.uuid4()}.vtt"
        r2.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=subtitle_key,
            Body=vtt_text.encode("utf-8"),
            ContentType="text/vtt; charset=utf-8",
            CacheControl="public, max-age=31536000, immutable",
        )

        Path(tmp_srt).write_text(srt_text, encoding="utf-8")
        metrics["burn_in_seconds"] = round(
            _burn_subtitles_into_video(tmp_video, tmp_srt, tmp_burned, font_size, alignment, margin_v), 3
        )

        burned_key = f"videos/subtitled-{uuid.uuid4()}.mp4"
        with open(tmp_burned, "rb") as f:
            r2.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=burned_key,
                Body=f,
                ContentType="video/mp4",
                CacheControl="public, max-age=31536000, immutable",
            )

        return SubtitleResult(
            status="completed",
            subtitle_r2_key=subtitle_key,
            subtitle_url=f"{R2_PUBLIC_URL}/{subtitle_key}",
            subtitle_text=subtitle_text,
            burned_video_r2_key=burned_key,
            burned_video_url=f"{R2_PUBLIC_URL}/{burned_key}",
            metrics=metrics,
        )
    except Exception as exc:
        logger.warning("User SRT burn-in failed for %s: %s", video_key, exc)
        return SubtitleResult(status="failed", error=str(exc), metrics=metrics)
    finally:
        for tmp in (tmp_video, tmp_srt, tmp_burned):
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)


def generate_subtitle_for_video(
    r2,
    video_key: str,
    *,
    model: str = DEFAULT_TRANSCRIPTION_MODEL,
    language: str | None = DEFAULT_TRANSCRIPTION_LANGUAGE,
    api_key: str | None = None,
    font_size: int = SUBTITLE_BURN_IN_FONT_SIZE,
    alignment: int = 2,
    margin_v: int = SUBTITLE_BURN_IN_MARGIN_V,
) -> SubtitleResult:
    """Download a video from R2, transcribe audio, upload SRT, and return metadata.

    This function never mutates the source video. Callers should treat failed/skipped
    results as non-fatal to preserve the original upload flow.
    """
    if not SUBTITLE_ENABLED:
        return SubtitleResult(status="skipped", error="subtitle generation disabled")

    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return SubtitleResult(status="skipped", error="OPENAI_API_KEY not configured")

    tmp_video = tmp_audio = tmp_srt = tmp_burned = None
    metrics: dict[str, Any] = {"model": model, "language": language}
    try:
        _ensure_tool("ffmpeg")
        _ensure_tool("ffprobe")
        tmp_video = _make_tmp(".mp4")
        tmp_audio = _make_tmp(".m4a")
        tmp_srt = _make_tmp(".srt")
        tmp_burned = _make_tmp(".mp4")

        resp = r2.get_object(Bucket=R2_BUCKET_NAME, Key=video_key)
        with open(tmp_video, "wb") as f:
            f.write(resp["Body"].read())

        duration = _probe_duration(tmp_video)
        metrics["duration_sec"] = round(duration, 3)
        if duration <= 0:
            return SubtitleResult(status="failed", error="cannot determine video duration", metrics=metrics)
        if duration > SUBTITLE_MAX_DURATION_SEC:
            return SubtitleResult(status="skipped", error=f"duration exceeds subtitle limit: {duration:.1f}s", metrics=metrics)

        if not _has_audio_stream(tmp_video):
            return SubtitleResult(
                status="skipped",
                error="no audio stream found in video",
                metrics=metrics,
            )

        metrics["extract_audio_seconds"] = round(_extract_audio(tmp_video, tmp_audio), 3)
        silence_ranges = _detect_silence_ranges(tmp_audio, duration)
        metrics["silence_ranges_detected"] = len(silence_ranges)

        if silence_ranges and duration > 0:
            total_silence = sum(end - start for start, end in silence_ranges)
            silence_ratio = total_silence / duration
            metrics["silence_ratio"] = round(silence_ratio, 3)
            if silence_ratio >= 0.90:
                return SubtitleResult(
                    status="skipped",
                    error=f"audio is {silence_ratio:.0%} silent — skipping transcription to avoid hallucination",
                    metrics=metrics,
                )

        # 'auto' → pass language=None to Whisper so it auto-detects
        whisper_language: str | None = None if language == "auto" else language
        verbose_data, transcribe_seconds = _transcribe_verbose_json(
            tmp_audio,
            api_key=api_key,
            model=model,
            language=whisper_language,
            prompt=DEFAULT_TRANSCRIPTION_PROMPT,
            temperature=DEFAULT_TRANSCRIPTION_TEMPERATURE,
        )
        metrics["transcribe_seconds"] = round(transcribe_seconds, 3)
        segments = verbose_data.get("segments", [])
        metrics["segments_total"] = len(segments)
        detected_language: str | None = verbose_data.get("language")
        if detected_language:
            metrics["detected_language"] = detected_language

        srt_text = _segments_to_srt(
            segments,
            SUBTITLE_NO_SPEECH_THRESHOLD,
            SUBTITLE_AVG_LOGPROB_THRESHOLD,
            SUBTITLE_COMPRESSION_RATIO_MAX,
            SUBTITLE_AVG_NO_SPEECH_GLOBAL_THRESHOLD,
            SUBTITLE_MIN_CHARS_PER_SEC,
            language=language,
            detected_language=detected_language,
        )
        # Drop any cue whose midpoint sits inside a detected silence stretch: Whisper
        # still emits stock phrases over pauses that the global 90% guard does not
        # catch in a partially-silent recording.
        if srt_text.strip() and silence_ranges:
            srt_text, silence_dropped = _filter_srt_by_silence(srt_text, silence_ranges)
            metrics["segments_dropped_in_silence"] = silence_dropped
        kept_count = len([s for s in srt_text.strip().split("\n\n") if s.strip()]) if srt_text.strip() else 0
        metrics["segments_kept"] = kept_count
        metrics["segments_filtered"] = len(segments) - kept_count

        if not srt_text.strip():
            return SubtitleResult(
                status="skipped",
                error="no speech detected — all segments filtered by no_speech_prob",
                metrics=metrics,
            )

        srt_text, clamped = _clamp_srt_to_duration(srt_text, duration)
        metrics["srt_clamped_to_source_duration"] = clamped
        subtitle_text = _plain_text_from_srt(srt_text)
        vtt_text = _srt_to_vtt(srt_text)

        subtitle_key = f"subtitles/s-{uuid.uuid4()}.vtt"
        r2.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=subtitle_key,
            Body=vtt_text.encode("utf-8"),
            ContentType="text/vtt; charset=utf-8",
            CacheControl="public, max-age=31536000, immutable",
        )

        Path(tmp_srt).write_text(srt_text, encoding="utf-8")
        metrics["burn_in_seconds"] = round(
            _burn_subtitles_into_video(tmp_video, tmp_srt, tmp_burned, font_size, alignment, margin_v), 3
        )
        burned_key = f"videos/subtitled-{uuid.uuid4()}.mp4"
        with open(tmp_burned, "rb") as f:
            r2.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=burned_key,
                Body=f,
                ContentType="video/mp4",
                CacheControl="public, max-age=31536000, immutable",
            )
        burned_url = f"{R2_PUBLIC_URL}/{burned_key}"
        metrics["burn_in_required"] = True
        metrics["burn_in_back_opacity"] = 0.8

        return SubtitleResult(
            status="completed",
            subtitle_r2_key=subtitle_key,
            subtitle_url=f"{R2_PUBLIC_URL}/{subtitle_key}",
            subtitle_text=subtitle_text,
            burned_video_r2_key=burned_key,
            burned_video_url=burned_url,
            metrics=metrics,
        )
    except Exception as exc:
        logger.warning("Subtitle generation failed for %s: %s", video_key, exc)
        return SubtitleResult(status="failed", error=str(exc), metrics=metrics)
    finally:
        for tmp in (tmp_video, tmp_audio, tmp_srt, tmp_burned):
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)


def subtitle_metrics_json(result: SubtitleResult) -> str | None:
    if not result.metrics:
        return None
    return json.dumps(result.metrics, ensure_ascii=False)
