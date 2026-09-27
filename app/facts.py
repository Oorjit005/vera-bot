import re
from datetime import datetime

NUM_RE = re.compile(r"\d[\d,]*\.?\d*")
ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}):(\d{2}))?")
MONTH_ABBR = [None, "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS = {abbr.lower(): i for i, abbr in enumerate(MONTH_ABBR) if abbr}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

PEER_MAP = {"views": "avg_views_30d", "calls": "avg_calls_30d", "directions": "avg_directions_30d",
            "ctr": "avg_ctr", "reviews": "avg_review_count"}
PLAIN_MAP = {"ctr": "profile CTR", "views": "profile views", "calls": "calls",
             "directions": "direction requests", "review_count": "Google reviews"}
METRIC_ORDER = ["views", "calls", "ctr"]

# SPEC-GAP: catalog_offer's CATALOG_PICK table (PLAN §6.3) is playbook data, but
# facts.py owns catalog_offer(), so the table lives here as the single source of truth;
# app/playbook imports it from here rather than duplicating it.
CATALOG_PICK = {
    "dentists": {"default": "Free Consultation", "cleaning": "Dental Cleaning @ ₹299",
                 "aligner": "Aligner Consultation @ ₹499", "kids": "Pediatric Dental Checkup @ ₹199"},
    "salons": {"default": "Haircut @ ₹99", "bridal": "Bridal Trial @ ₹999",
               "haircare": "Hair Spa @ ₹499"},
    "restaurants": {"default": "Free Delivery > ₹500", "weekday": "Weekday Lunch Thali @ ₹149",
                     "ipl": "Match-night Combo @ ₹399"},
    "gyms": {"default": "3 FREE Trial Classes", "winback": "First Month @ ₹499",
             "pt": "Personal Training Demo @ ₹199"},
    "pharmacies": {"default": "Free Home Delivery > ₹499",
                    "chronic": "Subscription refill reminder + delivery (chronic Rx)",
                    "senior": "Senior Citizen 15% OFF (60+ age)"},
}


def _parse_iso(s):
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d")
        except Exception:
            return None


class FactSet:
    def __init__(self, category, merchant, trigger, customer, now_iso):
        self.category = category or {}
        self.merchant = merchant or {}
        self.trigger = trigger or {}
        self.customer = customer or {}
        self.now_iso = now_iso
        self.ref_now = _parse_iso(now_iso) if now_iso else None
        self.numbers = set()
        self.derived = {}
        for ctx in (self.category, self.merchant, self.trigger, self.customer):
            self._walk(ctx)

    # ---- number registry ----

    def _walk(self, obj):
        if isinstance(obj, dict):
            for v in obj.values():
                self._walk(v)
        elif isinstance(obj, list):
            for v in obj:
                self._walk(v)
        elif isinstance(obj, bool):
            return
        elif isinstance(obj, str):
            self._extract_from_string(obj)
            self._maybe_register_date(obj)
        elif isinstance(obj, (int, float)):
            self._extract_from_string(str(obj))
            if isinstance(obj, float) and 0 < abs(obj) < 1:
                self.numbers.add(str(round(abs(obj) * 100)))
                self.numbers.add(str(round(abs(obj) * 100, 1)))

    def _register_token(self, token: str):
        token = token.replace(",", "")
        if not token:
            return
        if "." in token:
            int_part = token.split(".")[0] or "0"
            self.numbers.add(int_part)
            self.numbers.add(token)
        else:
            self.numbers.add(token)

    def _extract_from_string(self, s: str):
        for m in NUM_RE.findall(s):
            self._register_token(m)

    def _maybe_register_date(self, s: str):
        m = ISO_DATE_RE.match(s)
        if not m:
            return
        year, month, day, hour = m.group(1), m.group(2), m.group(3), m.group(4)
        self.numbers.add(str(int(day)))
        self.numbers.add(str(int(month)))
        self.numbers.add(year)
        if hour is not None:
            h24 = int(hour)
            self.numbers.add(str(h24))
            h12 = h24 % 12 or 12
            self.numbers.add(str(h12))

    def derive(self, name, value):
        self.derived[name] = value
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            self._extract_from_string(str(value))
            if isinstance(value, float) and 0 < abs(value) < 1:
                self.numbers.add(str(round(abs(value) * 100)))
                self.numbers.add(str(round(abs(value) * 100, 1)))
        elif isinstance(value, str):
            self._extract_from_string(value)
        return value

    def has_number(self, tok) -> bool:
        if tok is None:
            return False
        t = str(tok).strip().replace("₹", "").replace("%", "").replace(",", "")
        if t.endswith(".0"):
            t = t[:-2]
        return t in self.numbers

    # ---- accessors ----

    def salutation(self):
        owner = (self.merchant.get("identity", {}) or {}).get("owner_first_name")
        if owner:
            owner = owner.strip()
            if self.category.get("slug") == "dentists":
                return owner if owner.startswith("Dr.") else f"Dr. {owner}"
            return owner
        name = self.merchant_name()
        if name:
            return f"{name} team"
        return None

    def merchant_name(self):
        return (self.merchant.get("identity", {}) or {}).get("name")

    def short_name(self):
        name = self.merchant_name()
        if not name:
            return None
        owner = self.owner_first()
        if owner:
            owner_bare = owner.replace("Dr.", "").strip()
            if owner_bare and owner_bare.lower() in name.lower():
                idx = name.lower().find("'s")
                if idx != -1:
                    return name[:idx]
        return name

    def owner_first(self):
        return (self.merchant.get("identity", {}) or {}).get("owner_first_name")

    def locality(self):
        return (self.merchant.get("identity", {}) or {}).get("locality")

    def city(self):
        return (self.merchant.get("identity", {}) or {}).get("city")

    def active_offers(self):
        offers = self.merchant.get("offers") or []
        return [o.get("title") for o in offers if o.get("status") == "active" and o.get("title")]

    def catalog_offer(self, key):
        slug = self.category.get("slug")
        picks = CATALOG_PICK.get(slug)
        if not picks:
            return None
        title = picks.get(key) or picks.get("default")
        if not title:
            return None
        catalog_titles = {o.get("title") for o in (self.category.get("offer_catalog") or [])}
        if title in catalog_titles and not title.lower().startswith("flat"):
            return title
        return None

    def peer(self, metric):
        key = PEER_MAP.get(metric)
        if not key:
            return None
        return (self.category.get("peer_stats") or {}).get(key)

    def perf(self, metric):
        return (self.merchant.get("performance") or {}).get(metric)

    def peer_gap(self, metric):
        mine = self.perf(metric)
        peer = self.peer(metric)
        if mine is None or peer is None or peer == 0:
            return None
        diff = mine - peer
        pct = diff / peer
        direction = "above" if diff >= 0 else "below"
        self.derive(f"peer_gap_{metric}_diff", round(abs(diff), 2) if isinstance(diff, float) else abs(diff))
        self.derive(f"peer_gap_{metric}_pct", round(abs(pct) * 100))
        return {"mine": mine, "peer": peer, "diff": diff, "pct": pct, "direction": direction}

    def delta(self, metric):
        return (self.merchant.get("performance") or {}).get("delta_7d", {}).get(f"{metric}_pct")

    def strongest_negative(self):
        best = None
        for metric in METRIC_ORDER:
            d = self.delta(metric)
            if d is not None and d < 0 and (best is None or d < best[2]):
                best = ("delta", metric, d)
        if best:
            return best
        best_peer = None
        for metric in METRIC_ORDER:
            pg = self.peer_gap(metric)
            if pg and pg["direction"] == "below":
                if best_peer is None or pg["pct"] < best_peer[2]["pct"]:
                    best_peer = ("peer", metric, pg)
        return best_peer

    def strongest_positive(self):
        best = None
        for metric in METRIC_ORDER:
            d = self.delta(metric)
            if d is not None and d > 0 and (best is None or d > best[2]):
                best = ("delta", metric, d)
        if best:
            return best
        best_peer = None
        for metric in METRIC_ORDER:
            pg = self.peer_gap(metric)
            if pg and pg["direction"] == "above":
                if best_peer is None or pg["pct"] > best_peer[2]["pct"]:
                    best_peer = ("peer", metric, pg)
        return best_peer

    def digest(self, item_id):
        for item in self.category.get("digest") or []:
            if item.get("id") == item_id:
                return item
        return None

    def digest_by_kind(self, kind):
        for item in self.category.get("digest") or []:
            if item.get("kind") == kind:
                return item
        return None

    def seasonal_beat(self, month: int):
        for beat in self.category.get("seasonal_beats") or []:
            rng = self._parse_month_range(beat.get("month_range", ""))
            if not rng:
                continue
            start, end = rng
            if start <= end:
                if start <= month <= end:
                    return beat
            else:
                if month >= start or month <= end:
                    return beat
        return None

    @staticmethod
    def _parse_month_range(s):
        s = (s or "").strip()
        if not s:
            return None
        parts = s.split("-")
        if len(parts) == 1:
            tok = parts[0].strip().split()[0][:3].lower()
            mon = MONTHS.get(tok)
            return (mon, mon) if mon else None
        start_tok = parts[0].strip().split()[0][:3].lower()
        end_tok = parts[1].strip().split()[0][:3].lower()
        start, end = MONTHS.get(start_tok), MONTHS.get(end_tok)
        return (start, end) if start and end else None

    def trend_top(self):
        signals = self.category.get("trend_signals") or []
        if not signals:
            return None
        best = signals[0]
        for s in signals[1:]:
            if (s.get("delta_yoy") or float("-inf")) > (best.get("delta_yoy") or float("-inf")):
                best = s
        return best

    def review_theme(self, kind):
        themes = [t for t in (self.merchant.get("review_themes") or []) if t.get("sentiment") == kind]
        if not themes:
            return None
        best = themes[0]
        for t in themes[1:]:
            if (t.get("occurrences_30d") or 0) > (best.get("occurrences_30d") or 0):
                best = t
        return best

    def signal(self, prefix):
        for s in self.merchant.get("signals") or []:
            if s == prefix or s.startswith(prefix + ":") or s.startswith(prefix + "_"):
                m = re.search(r"(\d+)", s)
                return (s, int(m.group(1)) if m else None)
        return None

    def days_between(self, a_iso, b_iso):
        a, b = _parse_iso(a_iso), _parse_iso(b_iso)
        if not a or not b:
            return None
        return abs((b.date() if hasattr(b, "date") else b) - (a.date() if hasattr(a, "date") else a)).days

    def months_since(self, date_iso):
        d = _parse_iso(date_iso)
        if not d or not self.ref_now:
            return None
        d_date, now_date = d.date(), self.ref_now.date()
        months = (now_date.year - d_date.year) * 12 + (now_date.month - d_date.month)
        if now_date.day < d_date.day:
            months -= 1
        return max(months, 0)

    def fmt_inr(self, n):
        if n is None:
            return None
        neg = n < 0
        n = abs(int(round(n)))
        s = str(n)
        if len(s) <= 3:
            grouped = s
        else:
            last3, rest = s[-3:], s[:-3]
            parts = []
            while len(rest) > 2:
                parts.insert(0, rest[-2:])
                rest = rest[:-2]
            if rest:
                parts.insert(0, rest)
            grouped = ",".join(parts) + "," + last3
        return ("-" if neg else "") + "₹" + grouped

    def fmt_pct(self, x):
        if x is None:
            return None
        return f"{round(x * 100)}%"

    def fmt_date(self, iso):
        d = _parse_iso(iso)
        if not d:
            return None
        return f"{d.day} {MONTH_ABBR[d.month]} {d.year}"

    def fmt_day_time(self, iso):
        d = _parse_iso(iso)
        if not d:
            return None
        wd = WEEKDAYS[d.weekday()]
        hour, minute = d.hour, d.minute
        ampm = "am" if hour < 12 else "pm"
        h12 = hour % 12 or 12
        time_str = f"{h12}{ampm}" if minute == 0 else f"{h12}:{minute:02d}{ampm}"
        return f"{wd} {d.day} {MONTH_ABBR[d.month]}, {time_str}"

    def plain(self, metric):
        return PLAIN_MAP.get(metric, metric)
