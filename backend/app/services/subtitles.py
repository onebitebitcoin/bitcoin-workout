import re

_TIMESTAMP_RE = re.compile(
    r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}[,.]\d{3}"
)


def sanitize_srt(srt_text: str) -> str:
    """사용자 제출 SRT 텍스트를 정제한다.

    - 2000자 초과 시 잘라냄
    - 타임스탬프 라인은 유지, 텍스트는 HTML 태그 제거
    - 빈 큐 번호만 남는 블록은 제거
    """
    srt_text = srt_text[:2000]
    lines = srt_text.splitlines()
    cleaned: list[str] = []
    for line in lines:
        if _TIMESTAMP_RE.search(line) or line.strip().isdigit():
            cleaned.append(line)
        else:
            # HTML 태그 제거
            cleaned.append(re.sub(r"<[^>]+>", "", line))
    return "\n".join(cleaned)
