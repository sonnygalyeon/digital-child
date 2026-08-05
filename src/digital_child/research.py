from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol

from digital_child.llm import CognitiveBackend
from digital_child.models import ResearchReport, ResearchResult, ResearchStatus

_TAG_RE = re.compile(r"<[^>]+>")


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, limit: int = 5) -> list[ResearchResult]:
        ...


class DisabledSearchProvider:
    name = "disabled"

    def search(self, query: str, limit: int = 5) -> list[ResearchResult]:
        return []


class WikipediaSearchProvider:
    """Simple read-only public search provider used as a zero-key fallback."""

    name = "wikipedia"

    def __init__(self, language: str = "ru", timeout: float = 10.0) -> None:
        self.language = language
        self.timeout = timeout

    def search(self, query: str, limit: int = 5) -> list[ResearchResult]:
        params = urllib.parse.urlencode(
            {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": max(1, min(limit, 10)),
                "format": "json",
                "utf8": 1,
            }
        )
        url = f"https://{self.language}.wikipedia.org/w/api.php?{params}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "DigitalChild/0.4.1 research"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        results: list[ResearchResult] = []
        for item in payload.get("query", {}).get("search", []):
            page_id = item.get("pageid")
            title = str(item.get("title", ""))
            snippet = html.unescape(_TAG_RE.sub("", str(item.get("snippet", ""))))
            results.append(
                ResearchResult(
                    title=title,
                    url=f"https://{self.language}.wikipedia.org/?curid={page_id}",
                    snippet=snippet,
                    provider=self.name,
                    source_reliability=0.62,
                )
            )
        return results


class GenericJsonSearchProvider:
    """Adapter for a user-controlled search proxy returning {results:[...]} JSON."""

    name = "generic-json"

    def __init__(self, endpoint: str, api_key: str | None = None, timeout: float = 15.0) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout = timeout

    def search(self, query: str, limit: int = 5) -> list[ResearchResult]:
        separator = "&" if "?" in self.endpoint else "?"
        url = f"{self.endpoint}{separator}{urllib.parse.urlencode({'q': query, 'limit': limit})}"
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, list):
            raw_results = payload
        elif isinstance(payload, dict):
            raw_results = payload.get("results", [])
        else:
            raw_results = []
        return [
            ResearchResult(
                title=str(item.get("title", "Без названия")),
                url=str(item.get("url", "")),
                snippet=str(item.get("snippet", item.get("content", ""))),
                provider=self.name,
                source_reliability=float(item.get("reliability", 0.6)),
            )
            for item in raw_results[:limit]
            if isinstance(item, dict)
        ]


class ResearchEngine:
    def __init__(self, provider: SearchProvider, backend: CognitiveBackend) -> None:
        self.provider = provider
        self.backend = backend

    def research(self, claim: str, limit: int = 5) -> ResearchReport:
        if isinstance(self.provider, DisabledSearchProvider):
            return ResearchReport(
                claim=claim,
                query=claim,
                status=ResearchStatus.DISABLED,
                summary="Интернет-поиск отключён; утверждение остаётся непроверенным.",
            )
        try:
            results = self.provider.search(claim, limit=limit)
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            OSError,
            ValueError,
        ) as exc:
            return ResearchReport(
                claim=claim,
                query=claim,
                status=ResearchStatus.FAILED,
                summary="Не удалось получить внешние источники.",
                error=str(exc),
            )
        if not results:
            return ResearchReport(
                claim=claim,
                query=claim,
                status=ResearchStatus.INCONCLUSIVE,
                summary="Поиск не вернул подходящих материалов.",
            )
        try:
            judgments = self.backend.assess_sources(claim, results)
        except RuntimeError as exc:
            return ResearchReport(
                claim=claim,
                query=claim,
                status=ResearchStatus.INCONCLUSIVE,
                results=results,
                summary=(
                    "Источники получены, но семантическая оценка недоступна; "
                    "материалы сохранены без вывода об истинности."
                ),
                error=str(exc),
            )
        clear = [item for item in judgments if item.stance.value != "unclear"]
        status = ResearchStatus.COMPLETED if clear else ResearchStatus.INCONCLUSIVE
        support = sum(item.stance.value == "support" for item in judgments)
        contradict = sum(item.stance.value == "contradict" for item in judgments)
        summary = (
            f"Получено источников: {len(results)}; оценено как поддерживающие: {support}; "
            f"противоречащие: {contradict}; неясные: {len(judgments) - support - contradict}."
        )
        return ResearchReport(
            claim=claim,
            query=claim,
            status=status,
            results=results,
            judgments=judgments,
            summary=summary,
        )


def build_search_provider() -> SearchProvider:
    provider = os.environ.get("DIGITAL_CHILD_RESEARCH_PROVIDER", "wikipedia").strip().lower()
    if provider in {"disabled", "off", "none"}:
        return DisabledSearchProvider()
    if provider == "generic":
        endpoint = os.environ.get("DIGITAL_CHILD_SEARCH_ENDPOINT", "").strip()
        if not endpoint:
            return DisabledSearchProvider()
        return GenericJsonSearchProvider(
            endpoint=endpoint,
            api_key=os.environ.get("DIGITAL_CHILD_SEARCH_API_KEY"),
        )
    language = os.environ.get("DIGITAL_CHILD_WIKIPEDIA_LANGUAGE", "ru")
    return WikipediaSearchProvider(language=language)
