"""Optional, fail-closed social discovery connectors.

Only official APIs are queried. A missing credential or failed request produces no
signal and never raises a candidate's score.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import urllib.parse
import urllib.request

from .config import Settings


@dataclass(frozen=True)
class SocialEvidence:
    mentions: int = 0
    engagement: int = 0
    sources: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return bool(self.sources)

    @property
    def velocity_score(self) -> float:
        # A bounded attention-strength proxy, not a fabricated change-over-time percentage.
        return min(100.0, self.mentions * 4 + self.engagement / 20)


def _json_request(url: str, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(
        url, headers={"User-Agent": "DegenDetector/1.0", **(headers or {})}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        value = json.loads(response.read())
    return value if isinstance(value, dict) else {}


def _query(symbol: str, mint: str) -> str:
    clean = "".join(ch for ch in symbol if ch.isalnum())[:16]
    return f'("${clean}" OR "{mint}") -is:retweet' if clean else f'"{mint}" -is:retweet'


def x_recent_evidence(symbol: str, mint: str, bearer_token: str) -> SocialEvidence:
    if not bearer_token:
        return SocialEvidence()
    params = urllib.parse.urlencode({
        "query": _query(symbol, mint),
        "max_results": 100,
        "tweet.fields": "public_metrics,created_at",
    })
    payload = _json_request(
        "https://api.x.com/2/tweets/search/recent?" + params,
        {"Authorization": f"Bearer {bearer_token}"},
    )
    posts = payload.get("data") or []
    engagement = sum(
        sum(int((post.get("public_metrics") or {}).get(key) or 0) for key in
            ("like_count", "reply_count", "retweet_count", "quote_count"))
        for post in posts if isinstance(post, dict)
    )
    return SocialEvidence(len(posts), engagement, ("X",))


def youtube_recent_evidence(symbol: str, mint: str, api_key: str) -> SocialEvidence:
    if not api_key:
        return SocialEvidence()
    after = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    query = f"${symbol} {mint}" if symbol else mint
    params = urllib.parse.urlencode({
        "part": "snippet", "type": "video", "order": "date", "maxResults": 50,
        "publishedAfter": after, "q": query, "key": api_key,
    })
    payload = _json_request("https://www.googleapis.com/youtube/v3/search?" + params)
    items = payload.get("items") or []
    return SocialEvidence(len(items), 0, ("YouTube",))


def collect_social_evidence(symbol: str, mint: str, settings: Settings) -> SocialEvidence:
    evidence: list[SocialEvidence] = []
    connectors = (
        (x_recent_evidence, settings.x_bearer_token),
        (youtube_recent_evidence, settings.youtube_api_key),
    )
    for connector, credential in connectors:
        if not credential:
            continue
        try:
            evidence.append(connector(symbol, mint, credential))
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
    return SocialEvidence(
        mentions=sum(item.mentions for item in evidence),
        engagement=sum(item.engagement for item in evidence),
        sources=tuple(source for item in evidence for source in item.sources),
    )
