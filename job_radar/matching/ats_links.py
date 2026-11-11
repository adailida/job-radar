"""Reading the employer's own id for an opening from a link to its hiring system."""

import re
from urllib.parse import urlparse


class AtsLinks:
    """Turns a link to a known applicant tracking system into a key for the opening.

    `https://boards.greenhouse.io/recidiviz/jobs/4664444006` is
    `greenhouse:recidiviz:4664444006`, whichever board or aggregator linked to
    it. Lever, Ashby and Workable are read the same way; any other link gives
    no key. Stateless.
    """

    PATTERNS = (
        ("greenhouse", r"(?:job-)?boards(?:\.eu)?\.greenhouse\.io", r"/([^/]+)/jobs/(\d+)"),
        ("lever", r"jobs(?:\.eu)?\.lever\.co", r"/([^/]+)/([0-9a-f-]{36})"),
        ("ashby", r"jobs\.ashbyhq\.com", r"/([^/]+)/([0-9a-f-]{36})"),
        ("workable", r"apply\.workable\.com", r"/([^/]+)/j/([0-9A-Z]+)"),
    )

    def key(self, url: str) -> str | None:
        """The opening's key, such as "ashby:educationsuperhighway:<id>", or None."""
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()
        for name, hosts, path in self.PATTERNS:
            if re.fullmatch(hosts, host) and (found := re.match(path, parsed.path)):
                company, opening = found.groups()
                return f"{name}:{company.lower()}:{opening.lower()}"
        return None
