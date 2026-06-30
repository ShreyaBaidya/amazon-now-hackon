"""Google Calendar integration service.

Handles OAuth 2.0 flow, event fetching, automatic hero-event selection,
and AI-based shopping intent inference via Amazon Bedrock.

Falls back to config/calendar.json gracefully on any failure so the
demo never breaks even without Google credentials.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Trigger the shared .env loader from bedrock.py so GOOGLE_* vars are available.
# bedrock.py reads ROOT/.env, ROOT/.env.local, ROOT/backend/.env, ROOT/backend/.env.local
try:
    from . import bedrock as _bedrock_env_loader  # noqa: F401 — side-effect import
except Exception:  # noqa: BLE001
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment / config  — read lazily so .env is loaded before first access
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


def _client_id() -> str:
    """Read GOOGLE_CLIENT_ID from env at call-time (never at import time)."""
    return os.environ.get("GOOGLE_CLIENT_ID", "")


def _client_secret() -> str:
    """Read GOOGLE_CLIENT_SECRET from env at call-time."""
    return os.environ.get("GOOGLE_CLIENT_SECRET", "")


def _redirect_uri() -> str:
    """Read GOOGLE_REDIRECT_URI from env at call-time."""
    return os.environ.get(
        "GOOGLE_REDIRECT_URI", "http://127.0.0.1:8010/api/calendar/callback"
    )


# Scope: read-only calendar access (minimal permission)
GCAL_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

# ---------------------------------------------------------------------------
# In-memory session token store
# In production, swap this with a proper session store / DB.
# ---------------------------------------------------------------------------

_token_store: dict[str, Any] = {
    "access_token": None,
    "refresh_token": None,
    "expiry": None,       # datetime in UTC
    "connected": False,
}


def is_connected() -> bool:
    """Return True when a valid (or refresh-able) Google token is stored."""
    return bool(_token_store.get("connected") and _token_store.get("refresh_token"))


def has_credentials() -> bool:
    """Return True if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are configured."""
    return bool(_client_id() and _client_secret())


def store_tokens(access_token: str, refresh_token: str | None,
                 expires_in: int | None = 3600) -> None:
    """Persist tokens to the in-memory store after OAuth callback."""
    _token_store["access_token"] = access_token
    if refresh_token:
        _token_store["refresh_token"] = refresh_token
    _token_store["expiry"] = datetime.now(tz=timezone.utc) + timedelta(
        seconds=(expires_in or 3600) - 60  # 1-min buffer
    )
    _token_store["connected"] = True
    logger.info("Google Calendar tokens stored, expires ~%s", _token_store["expiry"])


def clear_tokens() -> None:
    """Disconnect — wipe token store."""
    _token_store.update(
        access_token=None, refresh_token=None, expiry=None, connected=False
    )
    logger.info("Google Calendar tokens cleared")


def _ensure_valid_token() -> str | None:
    """Return a valid access token, refreshing if needed. Returns None on failure."""
    if not _token_store.get("refresh_token"):
        return None

    expiry = _token_store.get("expiry")
    if expiry and datetime.now(tz=timezone.utc) < expiry and _token_store.get("access_token"):
        return _token_store["access_token"]

    # Token expired — refresh it
    return _refresh_access_token()


def _refresh_access_token() -> str | None:
    """Exchange the refresh token for a new access token via Google's token endpoint."""
    import urllib.request

    cid = _client_id()
    csecret = _client_secret()
    if not cid or not csecret:
        logger.error("Cannot refresh token: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not set")
        return None

    try:
        payload = json.dumps({
            "client_id": cid,
            "client_secret": csecret,
            "refresh_token": _token_store["refresh_token"],
            "grant_type": "refresh_token",
        }).encode()

        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        new_token = data.get("access_token")
        if new_token:
            _token_store["access_token"] = new_token
            _token_store["expiry"] = datetime.now(tz=timezone.utc) + timedelta(
                seconds=int(data.get("expires_in", 3600)) - 60
            )
            logger.info("Google Calendar access token refreshed successfully")
            return new_token
        else:
            logger.error("Token refresh response missing access_token: %s", data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Token refresh failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# OAuth URL builder
# ---------------------------------------------------------------------------

def build_auth_url(state: str = "") -> str:
    """Generate the Google OAuth consent URL."""
    from urllib.parse import urlencode
    params = {
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": GCAL_SCOPE,
        "access_type": "offline",   # request refresh_token
        "prompt": "consent",        # always show consent to guarantee refresh_token
        "state": state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


def exchange_code(code: str) -> bool:
    """Exchange an OAuth authorisation code for access + refresh tokens.
    Returns True on success, False on failure."""
    import urllib.request
    from urllib.parse import urlencode

    cid = _client_id()
    csecret = _client_secret()
    ruri = _redirect_uri()

    if not cid or not csecret:
        logger.error("Cannot exchange code: credentials not configured")
        return False

    try:
        payload = urlencode({
            "client_id": cid,
            "client_secret": csecret,
            "code": code,
            "redirect_uri": ruri,
            "grant_type": "authorization_code",
        }).encode()

        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = int(data.get("expires_in", 3600))

        if not access_token:
            logger.error("Token exchange returned no access_token: %s", data)
            return False

        if not refresh_token:
            # This happens if the user already granted access and prompt=consent was skipped.
            # The token will still work for the current session.
            logger.warning("No refresh_token in exchange response — session only")

        store_tokens(access_token, refresh_token, expires_in)
        logger.info("Token exchange successful. refresh_token present: %s", bool(refresh_token))
        return True

    except Exception as exc:  # noqa: BLE001
        logger.error("Code exchange failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Google Calendar API fetching
# ---------------------------------------------------------------------------

def _gcal_request(path: str, params: dict | None = None) -> dict | None:
    """Make an authenticated GET request to the Google Calendar API."""
    import urllib.request
    from urllib.parse import urlencode

    token = _ensure_valid_token()
    if not token:
        logger.warning("_gcal_request: no valid token available")
        return None

    url = f"https://www.googleapis.com/calendar/v3{path}"
    if params:
        url += "?" + urlencode(params)

    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Google Calendar API error for %s: %s", path, exc)
        return None


def fetch_upcoming_events(days: int = 1) -> list[dict]:
    """Fetch events from the primary calendar for today only (midnight to midnight IST).

    The `days` param is kept for compatibility but defaults to 1 (today).
    """
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(tz=IST)

    # Today's window: from now until end of today (midnight IST)
    today_start = now_ist  # from current time
    today_end = now_ist.replace(hour=23, minute=59, second=59, microsecond=0)

    result = _gcal_request("/calendars/primary/events", {
        "timeMin": today_start.isoformat(),
        "timeMax": today_end.isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": 20,
    })
    if not result:
        logger.warning("fetch_upcoming_events: no result from API")
        return []

    items = result.get("items", [])
    logger.info("fetch_upcoming_events: got %d events for today", len(items))
    return items


# ---------------------------------------------------------------------------
# Event normalisation — Google Calendar format → app CalendarEvent format
# ---------------------------------------------------------------------------

def _parse_google_dt(dt_str: str | None, date_str: str | None) -> datetime | None:
    """Parse a Google Calendar dateTime or date string into an aware datetime."""
    if dt_str:
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            pass
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            return d.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _when_label(dt: datetime) -> str:
    """Human-readable time label relative to now (IST). Windows-safe."""
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(tz=IST)
    dt_ist = dt.astimezone(IST)

    delta_days = (dt_ist.date() - now_ist.date()).days

    # Use %I (12-hour with leading zero) then strip manually — cross-platform safe
    time_str = dt_ist.strftime("%I:%M %p").lstrip("0") or "12:00 AM"

    if delta_days == 0:
        return f"Today, {time_str}"
    elif delta_days == 1:
        return f"Tomorrow, {time_str}"
    elif 2 <= delta_days <= 6:
        return f"{dt_ist.strftime('%a')}, {time_str}"
    else:
        # e.g. "Sat Jun 28"
        day = str(dt_ist.day)  # no leading zero, cross-platform
        return f"{dt_ist.strftime('%a %b')} {day}"


def _infer_event_type(title: str, description: str = "") -> str:
    """Infer a simplified event type from title/description keywords."""
    text = (title + " " + description).lower()
    if any(w in text for w in ["party", "dinner", "lunch", "brunch", "birthday",
                                "anniversary", "wedding", "celebration", "potluck",
                                "bbq", "barbecue", "picnic", "gathering"]):
        return "social"
    if any(w in text for w in ["standup", "meeting", "sync", "review", "interview",
                                "presentation", "sprint", "workshop", "training"]):
        return "work"
    if any(w in text for w in ["gym", "yoga", "run", "walk", "fitness", "workout",
                                "swim", "cycle", "hike", "trek"]):
        return "personal"
    if any(w in text for w in ["doctor", "dentist", "hospital", "clinic",
                                "appointment", "checkup"]):
        return "health"
    return "personal"


def _extract_guest_count(description: str, title: str) -> int | None:
    """Try to extract guest count from event text using regex patterns."""
    text = title + " " + (description or "")
    m = re.search(r"\b(\d+)\s*(?:guests?|people|persons?|pax|attendees?)\b", text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"\bfor\s+(\d+)\b", text, re.I)
    if m:
        n = int(m.group(1))
        if 2 <= n <= 30:
            return n
    return None


def _needs_shopping(event_type: str, title: str, description: str = "") -> bool:
    """Heuristic: does this event likely require a grocery run?"""
    if event_type == "work":
        return False
    text = (title + " " + description).lower()
    shopping_keywords = [
        "party", "dinner", "lunch", "brunch", "birthday", "anniversary",
        "picnic", "bbq", "barbecue", "potluck", "gathering", "celebration",
        "wedding", "drinks", "cook", "meal", "food", "eat",
    ]
    return any(k in text for k in shopping_keywords)


def normalise_events(raw_events: list[dict]) -> list[dict]:
    """Convert raw Google Calendar event objects to the app's CalendarEvent format."""
    normalised = []
    for ev in raw_events:
        start_info = ev.get("start", {})
        dt = _parse_google_dt(start_info.get("dateTime"), start_info.get("date"))
        if not dt:
            continue

        title = ev.get("summary", "Untitled event")
        description = ev.get("description", "") or ""
        location = ev.get("location", "") or ""
        event_type = _infer_event_type(title, description)
        guest_count = _extract_guest_count(description, title)

        # Try to count attendees from Google's attendees list
        attendees = ev.get("attendees", [])
        if not guest_count and attendees:
            guest_count = len([a for a in attendees if not a.get("self", False)])

        normalised.append({
            "id": ev.get("id", ""),
            "title": title,
            "start": dt.isoformat(),
            "when_label": _when_label(dt),
            "type": event_type,
            "guests": guest_count,
            "is_hero": False,          # set by select_hero()
            "summary": description[:120] if description else None,
            "location": location or None,
            "needs_shopping": _needs_shopping(event_type, title, description),
            "needs": [],               # populated by AI / keyword inference
            "dt_utc": dt.isoformat(),  # for frontend countdown
        })

    logger.info("normalise_events: normalised %d events", len(normalised))
    return normalised


# ---------------------------------------------------------------------------
# Hero event selection — automatic, no is_hero flag needed
# ---------------------------------------------------------------------------

_EVENT_TYPE_SCORE = {"social": 10, "personal": 4, "health": 2, "work": 0}


def select_hero(events: list[dict]) -> dict | None:
    """Pick the single best hero event from today's events.

    Scores each event on:
    - Event type (social scores highest)
    - Time proximity (events happening sooner score higher)
    - Guest count (more guests = more shopping)
    - Shopping likelihood keyword match

    Only considers events happening today.
    """
    IST = timezone(timedelta(hours=5, minutes=30))
    today_ist = datetime.now(tz=IST).date()
    now_utc = datetime.now(tz=timezone.utc)
    best, best_score = None, -1

    for ev in events:
        try:
            dt = datetime.fromisoformat(ev["dt_utc"])
        except (KeyError, ValueError):
            continue

        # Strictly today only (IST)
        dt_ist_date = dt.astimezone(IST).date()
        if dt_ist_date != today_ist:
            continue

        hours_away = max(0, (dt - now_utc).total_seconds() / 3600)

        type_score = _EVENT_TYPE_SCORE.get(ev.get("type", "personal"), 2)
        shopping_score = 5 if ev.get("needs_shopping") else 0
        guest_score = min((ev.get("guests") or 0), 10)

        # Time proximity: sooner = higher score (events already started get 15)
        if hours_away == 0:
            time_score = 15  # already started / happening now
        elif hours_away <= 3:
            time_score = 20 - hours_away * 2
        elif hours_away <= 12:
            time_score = 14 - hours_away
        else:
            time_score = 2

        total = type_score + shopping_score + guest_score + time_score
        logger.debug("select_hero: '%s' score=%.1f", ev.get("title"), total)

        if total > best_score:
            best_score = total
            best = ev

    if best:
        best = dict(best)
        best["is_hero"] = True
        logger.info("select_hero: chose '%s' (score %.1f)", best.get("title"), best_score)

    return best


# ---------------------------------------------------------------------------
# AI shopping intent — infer needs[] via Amazon Bedrock
# ---------------------------------------------------------------------------

_PRODUCT_HINTS = """
Available catalog categories: fresh_produce, dairy_eggs, bakery, staples_grocery,
meat_seafood, beverages, snacks, frozen, medicine_health, personal_care,
household_cleaning, baby_care.

Verified product IDs — use ONLY these exact strings:
Pasta/Italian: spaghetti, penne, farfalle
Dairy: amul-milk-500ml, amul-paneer-200g, amul-butter-100g, parmesan-150g, mozzarella-200g, mascarpone-250g, fresh-cream-200ml
Drinks (non-alcoholic): orange-juice-1l, cola-750ml, water-1l, amul-milk-500ml
Drinks (alcoholic): red-wine, white-wine, beer-6
Snacks: digestive-biscuits, chips-classic, namkeen, dark-chocolate, milk-chocolate, popcorn, cashews-200g, almonds-200g
Bread/Bakery: white-bread, brown-bread, pav-buns, burger-buns, croissant
Cakes/Desserts: chocolate-cake, vanilla-cake, cupcakes-6, brownie-box, ice-cream
Vegetables: tomato-500g, onion-1kg, potato-1kg, capsicum, garlic-200g, ginger-150g, spinach, mushroom-200g
Fruits: banana-6, apple-4, lemon-4
Meat: chicken-currycut-1kg, chicken-breast-500g, bacon-200g, farm-eggs-12
Staples: basmati-rice-1kg, atta-5kg, sugar-1kg, salt-1kg, sunflower-oil-1l, olive-oil-500ml
Condiments: barbeque-sauce, tomato-ketchup, mayonnaise, honey
Party supplies: balloons-pack, birthday-candles, birthday-banner, party-streamers, party-plates, party-cups, party-poppers, return-gifts-bag
Household: tissue-box, garbage-bags
"""

_INTENT_SYSTEM = """You are a shopping assistant for Amazon Now, a quick-commerce grocery app in India.
Given a calendar event, infer what groceries and supplies the user likely needs to buy.

{hints}

Rules:
- Only recommend products from the catalog above (use exact product IDs).
- Scale quantities by guest count (guests=1 means just the user).
- For every 2 guests, increase qty by 1 for food items.
- Maximum qty = 5 for any single item.
- Return a JSON array ONLY. No markdown, no explanation.
- Format: [{{"product_id": "...", "qty": N, "reason": "short reason"}}]
- Include 4-8 items that make practical sense for the event.
- If no shopping is needed (e.g. work meeting), return [].
"""


def infer_needs_via_bedrock(event: dict) -> list[dict]:
    """Use Amazon Bedrock to infer a shopping list from event metadata.
    Falls back to keyword heuristics if Bedrock is unavailable.
    """
    try:
        from . import bedrock as bk

        guests = event.get("guests") or 2
        prompt = (
            f"Event: {event['title']}\n"
            f"Type: {event.get('type', 'social')}\n"
            f"Guests: {guests}\n"
            f"Time: {event.get('when_label', '')}\n"
            f"Description: {event.get('summary') or 'none'}\n"
            f"Location: {event.get('location') or 'home'}\n\n"
            "What groceries and supplies does this person need to buy? "
            "Return ONLY a JSON array as described."
        )

        messages = [{"role": "user", "content": [{"text": prompt}]}]
        system = _INTENT_SYSTEM.format(hints=_PRODUCT_HINTS)
        resp = bk.converse(messages, system=system)
        raw = resp["output"]["message"]["content"][0]["text"].strip()

        # Strip markdown code fences if present
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip("`").strip()

        needs = json.loads(raw)
        if isinstance(needs, list):
            valid = []
            for n in needs:
                if isinstance(n, dict) and n.get("product_id"):
                    valid.append({
                        "product_id": str(n["product_id"]),
                        "qty": max(1, min(5, int(n.get("qty", 1)))),
                        "reason": str(n.get("reason", "For the event"))[:80],
                    })
            logger.info("Bedrock inferred %d needs for '%s'", len(valid), event.get("title"))
            return valid

    except Exception as exc:  # noqa: BLE001
        logger.warning("Bedrock intent inference failed: %s — using keyword fallback", exc)

    return _keyword_needs(event)


# ---------------------------------------------------------------------------
# Keyword-based fallback for shopping intent
# ALL product IDs below are verified against the real catalog.
# ---------------------------------------------------------------------------

# For each event type: list of (product_id, base_qty, reason, scale_with_guests)
# scale_with_guests=True → qty grows with guest count; False → always base_qty
_KEYWORD_NEEDS_MAP = [
    # ── Italian dinner / pasta night ─────────────────────────────────────────
    (["dinner", "pasta", "carbonara", "italian", "spaghetti"],
     [
         ("spaghetti",        2, "Pasta for the meal",        True),
         ("parmesan-150g",    1, "Topping",                   False),
         ("amul-butter-100g", 1, "For cooking",               False),
         ("red-wine",         1, "Dinner drinks",             True),
         ("dark-chocolate",   1, "Dessert",                   False),
     ]),

    # ── Birthday party ────────────────────────────────────────────────────────
    (["birthday", "bday"],
     [
         ("chocolate-cake",   1, "Birthday cake",             False),
         ("birthday-candles", 1, "Candles for the cake",      False),
         ("balloons-pack",    1, "Party decorations",         False),
         ("birthday-banner",  1, "Happy Birthday banner",     False),
         ("cupcakes-6",       1, "Cupcakes for guests",       True),
         ("ice-cream",        1, "Ice cream for everyone",    True),
         ("chips-classic",    2, "Party snacks",              True),
         ("cola-750ml",       2, "Soft drinks",               True),
         ("party-plates",     1, "Disposable plates",         False),
         ("party-cups",       1, "Disposable cups",           False),
         ("party-poppers",    1, "Celebration poppers",       False),
     ]),

    # ── Potluck / office party ───────────────────────────────────────────────
    (["potluck", "office party", "work party"],
     [
         ("chips-classic",    2, "Snacks to share",           True),
         ("namkeen",          1, "Indian snack mix",          True),
         ("orange-juice-1l",  2, "Drinks for all",            True),
         ("dark-chocolate",   1, "Dessert",                   False),
         ("tissue-box",       1, "Napkins",                   False),
     ]),

    # ── Picnic ───────────────────────────────────────────────────────────────
    (["picnic", "outdoor", "park"],
     [
         ("chips-classic",    2, "Picnic snacks",             True),
         ("orange-juice-1l",  2, "Drinks",                    True),
         ("white-bread",      1, "Sandwiches",                False),
         ("amul-butter-100g", 1, "Spread",                    False),
         ("banana-6",         1, "Fresh fruit",               True),
         ("tissue-box",       1, "Cleanup",                   False),
     ]),

    # ── BBQ / Barbecue ───────────────────────────────────────────────────────
    (["bbq", "barbecue", "grill"],
     [
         ("chicken-currycut-1kg", 1, "For grilling",          True),
         ("onion-1kg",            1, "Skewers & sides",       False),
         ("capsicum",             1, "Skewers",               False),
         ("barbeque-sauce",       1, "Marinade & dipping",    False),
         ("cola-750ml",           2, "Cold drinks",           True),
         ("tissue-box",           1, "Cleanup",               False),
     ]),

    # ── General party / gathering / celebration ───────────────────────────────
    (["party", "gathering", "celebration", "get-together"],
     [
         ("balloons-pack",    1, "Party decorations",         False),
         ("party-streamers",  1, "Streamers & confetti",      False),
         ("chips-classic",    2, "Party snacks",              True),
         ("namkeen",          1, "Savoury mix",               True),
         ("cola-750ml",       2, "Soft drinks",               True),
         ("orange-juice-1l",  1, "Juice option",              True),
         ("dark-chocolate",   1, "Chocolate treats",          False),
         ("party-plates",     1, "Disposable plates",         False),
         ("party-cups",       1, "Disposable cups",           False),
     ]),

    # ── Breakfast / brunch ───────────────────────────────────────────────────
    (["breakfast", "brunch"],
     [
         ("farm-eggs-12",     1, "Eggs for breakfast",        True),
         ("white-bread",      1, "Toast",                     False),
         ("amul-butter-100g", 1, "Spread",                    False),
         ("orange-juice-1l",  1, "Fresh juice",               True),
         ("amul-milk-500ml",  1, "Tea / coffee",              False),
     ]),

    # ── Lunch ────────────────────────────────────────────────────────────────
    (["lunch"],
     [
         ("onion-1kg",        1, "Cooking base",              False),
         ("tomato-500g",      1, "Gravy",                     False),
         ("amul-paneer-200g", 1, "Protein",                   True),
         ("amul-butter-100g", 1, "Cooking",                   False),
         ("basmati-rice-1kg", 1, "Rice",                      True),
     ]),

    # ── Game night / movie night ──────────────────────────────────────────────
    (["game night", "movie", "netflix", "watch"],
     [
         ("popcorn",          2, "Movie snacks",              True),
         ("chips-classic",    1, "Crisps",                    True),
         ("cola-750ml",       2, "Cold drinks",               True),
         ("dark-chocolate",   1, "Chocolate",                 False),
     ]),
]


def _keyword_needs(event: dict) -> list[dict]:
    """Rule-based fallback: match event title/description to shopping lists.

    Quantity logic:
    - Items marked scale_with_guests grow proportionally with guest count
    - Non-food/disposables stay at base qty
    - Hard cap at 5 per item
    """
    text = (event.get("title", "") + " " + (event.get("summary") or "")).lower()
    guests = max(1, event.get("guests") or 2)
    # 1 pack per 3 guests for food, capped at 5
    food_factor = max(1, round(guests / 3))

    for keywords, base_needs in _KEYWORD_NEEDS_MAP:
        if any(k in text for k in keywords):
            return [
                {
                    "product_id": pid,
                    "qty": min(5, max(1, base_qty * food_factor)) if scale else base_qty,
                    "reason": reason,
                }
                for pid, base_qty, reason, scale in base_needs
            ]

    # Generic social event fallback
    if event.get("type") == "social" or event.get("needs_shopping"):
        return [
            {"product_id": "chips-classic",  "qty": min(5, food_factor * 2), "reason": "Snacks for guests"},
            {"product_id": "cola-750ml",     "qty": min(5, food_factor * 2), "reason": "Cold drinks"},
            {"product_id": "namkeen",        "qty": min(3, food_factor),     "reason": "Savoury snacks"},
            {"product_id": "dark-chocolate", "qty": 1,                       "reason": "Chocolate treats"},
            {"product_id": "tissue-box",     "qty": 1,                       "reason": "Party essentials"},
        ]

    return []


# ---------------------------------------------------------------------------
# Main public interface
# ---------------------------------------------------------------------------

def get_calendar_data(use_ai: bool = True) -> dict:
    """Fetch today's Google Calendar events and infer shopping needs.
    Raises RuntimeError if not connected or API fails — caller should fallback.
    Returns a valid response with empty events list if there are no events today.
    """
    if not is_connected():
        raise RuntimeError("Google Calendar not connected")

    raw_events = fetch_upcoming_events()
    if raw_events is None:
        raise RuntimeError("Google Calendar API request failed")

    events = normalise_events(raw_events)

    # Select the best hero event from today's events only
    hero = select_hero(events)

    if hero:
        if hero.get("needs_shopping", False):
            hero["needs"] = infer_needs_via_bedrock(hero) if use_ai else _keyword_needs(hero)
        else:
            hero["needs"] = _keyword_needs(hero)
        events = [hero if e["id"] == hero["id"] else e for e in events]

    return {
        "events": events,
        "source": "google",
        "connected": True,
        "has_events_today": len(events) > 0,
        "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def get_calendar_with_fallback() -> dict:
    """Primary entry point — returns today's Google Calendar events or mock data.

    If Google Calendar is connected, fetches only today's events.
    On any failure, transparently falls back to config/calendar.json.
    The fallback also filters to today's events only.
    """
    if is_connected():
        try:
            result = get_calendar_data()
            logger.info("get_calendar_with_fallback: returning live Google Calendar data (%d events today)",
                        len(result.get("events", [])))
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning("Google Calendar fetch failed, falling back to mock: %s", exc)

    # Fallback — load static calendar.json, filter to today's events
    logger.info("get_calendar_with_fallback: returning mock calendar data")
    with open(CONFIG_DIR / "calendar.json", encoding="utf-8") as f:
        cal = json.load(f)

    # Filter mock events to today only (IST)
    IST = timezone(timedelta(hours=5, minutes=30))
    today_ist = datetime.now(tz=IST).date()
    today_events = []
    for ev in cal.get("events", []):
        try:
            dt = datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
            if dt.astimezone(IST).date() == today_ist:
                today_events.append(ev)
        except (KeyError, ValueError):
            continue

    return {
        "events": today_events,
        "source": "mock",
        "connected": False,
        "has_events_today": len(today_events) > 0,
    }


def debug_status() -> dict:
    """Return diagnostic information for troubleshooting the integration."""
    token = _token_store.get("access_token")
    return {
        "is_connected": is_connected(),
        "has_credentials": has_credentials(),
        "client_id_set": bool(_client_id()),
        "client_secret_set": bool(_client_secret()),
        "redirect_uri": _redirect_uri(),
        "access_token_present": bool(token),
        "access_token_preview": (token[:12] + "...") if token else None,
        "refresh_token_present": bool(_token_store.get("refresh_token")),
        "token_expiry": str(_token_store.get("expiry")),
    }
