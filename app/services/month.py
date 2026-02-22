import datetime as dt


def resolve_month_window(month: str | None) -> tuple[dt.date, dt.date, str]:
    if month:
        try:
            parsed = dt.datetime.strptime(month, "%Y-%m")
        except ValueError as exc:
            raise ValueError("Month must be in YYYY-MM format") from exc
        year = parsed.year
        month_value = parsed.month
    else:
        now = dt.date.today()
        year = now.year
        month_value = now.month

    start = dt.date(year, month_value, 1)
    if month_value == 12:
        end = dt.date(year + 1, 1, 1)
    else:
        end = dt.date(year, month_value + 1, 1)

    month_label = f"{year:04d}-{month_value:02d}"
    return start, end, month_label
