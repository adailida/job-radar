"""Record a small, scrubbed test fixture from a real job board API.

    uv run python scripts/record_fixture.py jobspipe

Uses a neutral query ("software engineer", US), never the user's settings, and
keeps a handful of records. Emails and phone numbers in the text are replaced,
and no key or header is written. JobsPipe charges 1 credit per new job: this
records 5. Review the file before committing it.
"""

import json
import os
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE = re.compile(r"(?<![\w-])(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?![\w-])")


class Scrubber:
    """Replaces emails and phone numbers in every string of a JSON value. Stateless."""

    def clean(self, value: object) -> object:
        """The value with each string scrubbed, at any depth."""
        if isinstance(value, str):
            return PHONE.sub("+1 555 0100", EMAIL.sub("someone@example.org", value))
        if isinstance(value, list):
            return [self.clean(item) for item in value]
        if isinstance(value, dict):
            return {key: self.clean(item) for key, item in value.items()}
        return value


class JobsPipeRecorder:
    """Records one page of JobsPipe search results. Stateless: holds only the key."""

    URL = "https://api.jobspipe.dev/v1/jobs/search"
    QUERY = {"job_title_or": ["software engineer"], "job_country_code_or": ["US"], "limit": 5}

    def __init__(self, key: str) -> None:
        """Keep the API key."""
        self._key = key

    def record(self) -> dict:
        """One page of results, as the API sent it."""
        response = httpx.post(
            self.URL,
            json=self.QUERY,
            headers={
                "Authorization": f"Bearer {self._key}",
                "User-Agent": "job-radar (+https://github.com/adailida/job-radar)",
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()


def key_from_env(name: str) -> str:
    """The key from the environment, or from `config_local/.env`."""
    if os.environ.get(name):
        return os.environ[name]
    env = ROOT / "config_local" / ".env"
    for line in env.read_text(encoding="utf-8").splitlines() if env.is_file() else []:
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"{name} is not set (environment or config_local/.env)")


if __name__ == "__main__":
    if sys.argv[1:] != ["jobspipe"]:
        raise SystemExit("usage: record_fixture.py jobspipe")
    page = JobsPipeRecorder(key_from_env("JOBSPIPE_API_KEY")).record()
    metadata = page.get("metadata", {})
    charged, left = metadata.get("credits_charged"), metadata.get("credits_remaining")
    print(f"charged {charged} credits, {left} left")
    target = ROOT / "tests" / "fixtures" / "jobspipe" / "search_page.json"
    target.write_text(json.dumps(Scrubber().clean(page), indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {target.relative_to(ROOT)}: {len(page.get('data', []))} jobs")
