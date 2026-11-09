"""Saying a posting's facts and dates in plain words, the same way in every file a run writes."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from job_radar.model import Period, Posting, Salary, WorkMode


class Words:
    """Puts work modes, places, pay and dates into short plain words.

    Plain text only: words instead of symbols, "to" for ranges. Stateless.
    """

    WORK_MODES = {WorkMode.REMOTE: "Remote", WorkMode.HYBRID: "Hybrid", WorkMode.ONSITE: "On-site"}
    PERIODS = {Period.YEAR: "a year", Period.MONTH: "a month", Period.HOUR: "an hour"}

    def details(self, posting: Posting) -> str:
        """Work mode, places, salary and posted date, each left out when unknown.

        A place that only repeats the work mode ("Remote") is left out too.
        """
        mode = self.WORK_MODES.get(posting.work_mode, "")
        places = [loc.text for loc in posting.locations if loc.text.lower() != mode.lower()]
        parts = [
            mode,
            "; ".join(places),
            self.salary(posting.salary) if posting.salary else "",
            f"Posted {self.day(posting.posted_at)}" if posting.posted_at else "",
        ]
        return " ".join(f"{part}." for part in parts if part)

    def salary(self, salary: Salary) -> str:
        """A pay range in words: "$150k to $180k a year", "From EUR 50k a year"."""
        low, high = salary.min, salary.max
        period = self.PERIODS[salary.period]
        if low is not None and high is not None and low != high:
            pay = f"{self.money(low, salary.currency)} to {self.money(high, salary.currency)}"
        elif low is not None and high is None:
            pay = f"From {self.money(low, salary.currency)}"
        elif low is None and high is not None:
            pay = f"Up to {self.money(high, salary.currency)}"
        else:
            pay = self.money(low or high or Decimal(0), salary.currency)
        return f"{pay} {period}"

    @staticmethod
    def money(amount: Decimal, currency: str) -> str:
        """An amount with its currency, whole thousands as "k": "$150k", "EUR 53k", "$45.50"."""
        if amount >= 1000:
            number = f"{(amount / 1000).quantize(Decimal(1), ROUND_HALF_UP)}k"
        elif amount == amount.to_integral_value():
            number = f"{amount:.0f}"
        else:
            number = f"{amount:.2f}"
        return f"${number}" if currency == "USD" else f"{currency} {number}"

    @staticmethod
    def day(day: date, year: bool = False) -> str:
        """A day in words: "8 Nov", or "8 Nov 2026" with the year."""
        return f"{day.day} {day:%b}" + (f" {day.year}" if year else "")

    def span(self, start: date, end: date) -> str:
        """Two days as a range, the year said once when they share it."""
        if start == end:
            return self.day(end, year=True)
        if start.year == end.year:
            return f"{self.day(start)} to {self.day(end, year=True)}"
        return f"{self.day(start, year=True)} to {self.day(end, year=True)}"
