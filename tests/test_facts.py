import json
import os

from app.facts import FactSet


def _load(dataset_dir, *parts):
    with open(os.path.join(dataset_dir, *parts), encoding="utf-8") as f:
        return json.load(f)


def _fs(dataset_dir, category_slug=None, merchant_file=None, trigger_file=None, customer_file=None,
        now_iso="2026-04-26T10:00:00Z"):
    category = _load(dataset_dir, "categories", f"{category_slug}.json") if category_slug else None
    merchant = _load(dataset_dir, "merchants", merchant_file) if merchant_file else None
    trigger = _load(dataset_dir, "triggers", trigger_file) if trigger_file else None
    customer = _load(dataset_dir, "customers", customer_file) if customer_file else None
    return FactSet(category, merchant, trigger, customer, now_iso)


# --- salutation: "Dr. Dr." case ---

def test_salutation_no_double_dr(dataset_dir):
    fs = _fs(dataset_dir, "dentists", "m_011_dr_sameer_dentist_bangalore.json")
    assert fs.salutation() == "Dr. Sameer"


def test_salutation_adds_dr_prefix(dataset_dir):
    fs = _fs(dataset_dir, "dentists", "m_001_drmeera_dentist_delhi.json")
    assert fs.salutation() == "Dr. Meera"


def test_salutation_non_dentist_no_prefix(dataset_dir):
    fs = _fs(dataset_dir, "salons", "m_023_sushma_salon_pune.json")
    assert fs.salutation() == "Sushma"


def test_salutation_falls_back_to_team(dataset_dir):
    category = _load(dataset_dir, "categories", "dentists.json")
    merchant = {"category_slug": "dentists", "identity": {"name": "Some Clinic"}}
    fs = FactSet(category, merchant, None, None, "2026-04-26T10:00:00Z")
    assert fs.salutation() == "Some Clinic team"


# --- month-range wrap: "Nov-Feb" matches Jan ---

def test_seasonal_beat_wraparound(dataset_dir):
    fs = _fs(dataset_dir, "dentists", "m_001_drmeera_dentist_delhi.json")
    beat = fs.seasonal_beat(1)  # January
    assert beat is not None
    assert beat["month_range"] == "Nov-Feb"


def test_seasonal_beat_non_wrap(dataset_dir):
    fs = _fs(dataset_dir, "dentists", "m_001_drmeera_dentist_delhi.json")
    beat = fs.seasonal_beat(5)  # May, inside Apr-Jun
    assert beat is not None
    assert beat["month_range"] == "Apr-Jun"


# --- fmt_inr Indian grouping ---

def test_fmt_inr_grouping(dataset_dir):
    fs = _fs(dataset_dir, "dentists", "m_001_drmeera_dentist_delhi.json")
    assert fs.fmt_inr(1499) == "₹1,499"
    assert fs.fmt_inr(14999) == "₹14,999"
    assert fs.fmt_inr(120000) == "₹1,20,000"
    assert fs.fmt_inr(299) == "₹299"


def test_fmt_pct(dataset_dir):
    fs = _fs(dataset_dir, "dentists", "m_001_drmeera_dentist_delhi.json")
    assert fs.fmt_pct(0.38) == "38%"
    assert fs.fmt_pct(-0.5) == "-50%"


def test_fmt_date_and_day_time(dataset_dir):
    # NOTE: PLAN.md's illustrative T28 example labels these slots "Wed 5 Nov" /
    # "Thu 6 Nov", but 2026-11-05 is actually a Thursday and 2026-11-06 a Friday
    # (verified against the real Gregorian calendar). fmt_day_time() computes the
    # true weekday; the playbook uses the dataset's own payload "label" verbatim
    # for recall_due slots rather than recomputing it (PLAN D10), so this
    # discrepancy never reaches an actual message.
    fs = _fs(dataset_dir, "dentists", "m_001_drmeera_dentist_delhi.json")
    assert fs.fmt_date("2026-12-15") == "15 Dec 2026"
    assert fs.fmt_day_time("2026-11-05T18:00:00+05:30") == "Thu 5 Nov, 6pm"
    assert fs.fmt_day_time("2026-11-06T17:00:00+05:30") == "Fri 6 Nov, 5pm"


# --- number registry ---

def test_number_registry_fraction_promotion(dataset_dir):
    category = _load(dataset_dir, "categories", "dentists.json")
    merchant = {"category_slug": "dentists", "identity": {"name": "X"}, "performance": {"ctr": 0.38}}
    fs = FactSet(category, merchant, None, None, "2026-04-26T10:00:00Z")
    assert fs.has_number("38")

    merchant2 = {"category_slug": "dentists", "identity": {"name": "X"}, "performance": {"delta_7d": {"views_pct": -0.5}}}
    fs2 = FactSet(category, merchant2, None, None, "2026-04-26T10:00:00Z")
    assert fs2.has_number("50")


def test_number_registry_embedded_in_string(dataset_dir):
    category = _load(dataset_dir, "categories", "pharmacies.json")
    trigger = {"payload": {"trends": ["ORS_demand_+40", "cold_cough_demand_-60"]}}
    fs = FactSet(category, None, trigger, None, "2026-04-26T10:00:00Z")
    assert fs.has_number("40")
    assert fs.has_number("60")


def test_number_registry_signal_with_colon(dataset_dir):
    category = _load(dataset_dir, "categories", "dentists.json")
    merchant = {"category_slug": "dentists", "identity": {"name": "X"}, "signals": ["stale_posts:22d"]}
    fs = FactSet(category, merchant, None, None, "2026-04-26T10:00:00Z")
    assert fs.has_number("22")
    assert fs.signal("stale_posts") == ("stale_posts:22d", 22)


def test_number_registry_dates(dataset_dir):
    category = _load(dataset_dir, "categories", "dentists.json")
    merchant = {"category_slug": "dentists", "identity": {"name": "X"}, "subscription": {"renewed_at": "2026-12-15T18:00:00Z"}}
    fs = FactSet(category, merchant, None, None, "2026-04-26T10:00:00Z")
    assert fs.has_number("15")   # day
    assert fs.has_number("12")  # month
    assert fs.has_number("2026")  # year
    assert fs.has_number("18")  # hour 24h
    assert fs.has_number("6")   # hour 12h


def test_has_number_normalises_currency_and_percent(dataset_dir):
    category = _load(dataset_dir, "categories", "dentists.json")
    merchant = {"category_slug": "dentists", "identity": {"name": "X"}, "offers": [{"title": "Cleaning @ ₹299", "status": "active"}]}
    fs = FactSet(category, merchant, None, None, "2026-04-26T10:00:00Z")
    assert fs.has_number("₹299")
    assert fs.has_number("299%")
    assert fs.has_number("299.0")


# --- peer_gap on m_023: calls 22 vs salon peer 28 ---

def test_peer_gap_m023_calls(dataset_dir):
    fs = _fs(dataset_dir, "salons", "m_023_sushma_salon_pune.json")
    gap = fs.peer_gap("calls")
    assert gap["mine"] == 22
    assert gap["peer"] == 28
    assert gap["diff"] == -6
    assert gap["direction"] == "below"


# --- strongest_negative falls back to peer gap when all deltas positive (m_023) ---

def test_strongest_negative_falls_back_to_peer_gap(dataset_dir):
    fs = _fs(dataset_dir, "salons", "m_023_sushma_salon_pune.json")
    result = fs.strongest_negative()
    assert result is not None
    kind, metric, value = result
    assert kind == "peer"
    assert metric == "calls"
    assert value["direction"] == "below"


# --- sparse merchant accessors return None without raising ---

def test_sparse_merchant_accessors_safe(dataset_dir):
    fs = _fs(dataset_dir, "dentists", "m_011_dr_sameer_dentist_bangalore.json")
    assert fs.active_offers() == []
    assert fs.digest("nonexistent") is None
    assert fs.digest_by_kind("nonexistent") is None
    assert fs.review_theme("neg") is None
    assert fs.review_theme("pos") is None
    assert fs.signal("nonexistent_prefix") is None
    assert fs.catalog_offer("nonexistent_key") is not None or fs.catalog_offer("nonexistent_key") is None
    assert fs.peer_gap("nonexistent_metric") is None
    assert fs.days_between(None, None) is None
    assert fs.months_since(None) is None
    assert fs.fmt_inr(None) is None
    assert fs.fmt_date(None) is None
    assert fs.fmt_day_time(None) is None


def test_empty_factset_never_raises():
    fs = FactSet(None, None, None, None, None)
    assert fs.salutation() is None
    assert fs.merchant_name() is None
    assert fs.short_name() is None
    assert fs.owner_first() is None
    assert fs.locality() is None
    assert fs.city() is None
    assert fs.active_offers() == []
    assert fs.catalog_offer("default") is None
    assert fs.peer("views") is None
    assert fs.perf("views") is None
    assert fs.peer_gap("views") is None
    assert fs.delta("views") is None
    assert fs.strongest_negative() is None
    assert fs.strongest_positive() is None
    assert fs.digest("x") is None
    assert fs.digest_by_kind("x") is None
    assert fs.seasonal_beat(1) is None
    assert fs.trend_top() is None
    assert fs.review_theme("neg") is None
    assert fs.signal("x") is None
    assert fs.has_number("5") is False
    assert fs.plain("views") == "profile views"


# --- lang.py ---

def test_merchant_lang(dataset_dir):
    from app.lang import merchant_lang
    dentists = _load(dataset_dir, "categories", "dentists.json")
    gyms = _load(dataset_dir, "categories", "gyms.json")
    meera = _load(dataset_dir, "merchants", "m_001_drmeera_dentist_delhi.json")
    assert merchant_lang(meera, dentists) == "en+hi_cta"

    gym_merchant = {"identity": {"languages": ["en", "hi"]}}
    assert merchant_lang(gym_merchant, gyms) == "en"


def test_customer_lang():
    from app.lang import customer_lang
    assert customer_lang({"identity": {"language_pref": "hi-en mix"}}) == "hinglish"
    assert customer_lang({"identity": {"language_pref": "hi"}}) == "hindi"
    assert customer_lang({"identity": {"language_pref": "en"}}) == "en"
    assert customer_lang({"identity": {"language_pref": "english"}}) == "en"
    assert customer_lang({"identity": {"language_pref": "ta-en mix"}}) == ("en", "ta")
    assert customer_lang({"identity": {"language_pref": "te-en mix"}}) == ("en", "te")
    assert customer_lang({"identity": {"language_pref": "kn-en mix"}}) == ("en", "kn")
    assert customer_lang(None) == "en"


def test_detect_reply_lang():
    from app.lang import detect_reply_lang
    assert detect_reply_lang("Ok lets do it. Whats next?") == "en"
    assert detect_reply_lang("Haan theek hai, kar do") == "hinglish"
    assert detect_reply_lang("नमस्ते") == "hinglish"
    assert detect_reply_lang("") == "en"
    assert detect_reply_lang(None) == "en"
