"""Direct HTTP client for the Hospitality Suite PMS.

The PMS web UI (https://fo.hospitality.mykg.id/) is an ASP.NET MVC shell
whose pages call a separate JSON REST API at api5b.hospitality.citiskg.com
using a bearer JWT. That JWT is minted by the ordinary HTML login form and
handed back as a plain cookie (``TOKEN``) - no browser/JS execution is
required to obtain it. This client replicates that login and calls the same
JSON endpoints the site's own Vue/axios code uses, instead of driving Chrome
through the UI.

This module is intentionally standalone: it does not import or modify the
existing Selenium-based scraper/updater code, so it can be exercised from a
separate test route without touching the production automation paths.
"""

import os

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://fo.hospitality.mykg.id"
API_BASE_URL = "https://api5b.hospitality.citiskg.com"


class PMSApiError(Exception):
    """Raised when the PMS login or a JSON API call fails."""


class PMSApiClient:
    """Authenticated session against the PMS HTML site + its JSON API."""

    def __init__(self, username=None, password=None):
        self.username = username or os.environ.get("PMS_USERNAME", "")
        self.password = password or os.environ.get("PMS_PASSWORD", "")
        if not self.username or not self.password:
            raise PMSApiError("PMS username and password are required")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (pms-api-client)"})
        self.hotel_id = None
        self.user_id = None
        self._token = None

    def login(self):
        """POST the login form and capture the JWT/hotel/user cookies it sets."""
        login_page = self.session.get(f"{BASE_URL}/")
        login_page.raise_for_status()
        soup = BeautifulSoup(login_page.text, "html.parser")
        form = soup.find("form", id="formLogin")
        if not form:
            raise PMSApiError("Login form not found on PMS home page")
        token_input = form.find("input", {"name": "__RequestVerificationToken"})
        if not token_input or not token_input.get("value"):
            raise PMSApiError("Anti-forgery token not found in login form")

        resp = self.session.post(
            f"{BASE_URL}/Login/Login",
            data={
                "__RequestVerificationToken": token_input["value"],
                "UserId": self.username,
                "UserPassword": self.password,
            },
        )
        resp.raise_for_status()

        bearer = self.session.cookies.get("TOKEN")
        hotel_id = self.session.cookies.get("HOTELID")
        user_id = self.session.cookies.get("USERID")
        if not bearer or not hotel_id or not user_id or "Login" in resp.url:
            raise PMSApiError("PMS login failed - check username/password")

        self._token = bearer
        self.hotel_id = int(hotel_id)
        self.user_id = user_id
        return self

    def _api_post(self, path, payload):
        if not self._token:
            raise PMSApiError("Not logged in - call login() first")
        resp = self.session.post(
            f"{API_BASE_URL}/api/{path}",
            json=payload,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        if resp.status_code >= 400:
            message = resp.text
            try:
                message = resp.json().get("Message", resp.text)
            except ValueError:
                pass
            raise PMSApiError(f"PMS API {path} failed ({resp.status_code}): {message}")
        return resp.json()

    def get_available_room_inventory(self, start_date, days):
        """Fetch room-availability rows for `days` days starting at `start_date`
        (YYYY-MM-DD). Equivalent to the Room Availability page's search.

        Note: this endpoint's per-room-type fields (DLT, PRKG, ...) are
        remaining PHYSICAL availability, not the allotment/online-sale cap -
        use get_allotment_room_inventory() to read back what save_allotment
        actually wrote."""
        return self._api_post(
            "AvailableRoomInventoryType",
            {
                "TrxDate": start_date,
                "Days": days,
                "HotelId": self.hotel_id,
                "UserId": self.user_id,
            },
        )

    def get_allotment_room_inventory(self, company_id, start_date, days):
        """Fetch the current allotment grid ('Allotment Room List - Channel
        Manager' page) for `days` days from `start_date` (YYYY-MM-DD).

        Confirmed via a live probe (2026-09-27): each response row's
        per-room-type fields are keyed by the same short codes used as
        `type_id`/`checkbox_value` in save_allotment (e.g. "DLT", "PRKG"),
        and their values match what save_allotment most recently wrote for
        that room type/date - unlike get_available_room_inventory's fields,
        which are a different number (remaining physical availability).
        There are also `{code}_REQ` and `{code}_ATTR` fields in the response
        whose exact semantics weren't confirmed (REQ sometimes differs from
        the plain field; ATTR was 0 in every sampled row) - not used here."""
        return self._api_post(
            "AllotmentRoomInventory",
            {
                "CompanyId": company_id,
                "TrxDate": start_date,
                "Days": days,
                "HotelId": self.hotel_id,
                "UserId": self.user_id,
            },
        )

    def save_allotment(self, company_id, start_date, end_date, type_id, no_of_rooms, remark, is_closed=False):
        """Push one allotment change for one contiguous date range and one room
        type. `start_date`/`end_date` are YYYY/MM/DD strings, matching what the
        PMS's own "Add Allotment Room" modal sends. Equivalent to one row of
        that modal's batch save."""
        return self._api_post(
            "allotment",
            {
                "CompanyId": company_id,
                "StartDate": start_date,
                "EndDate": end_date,
                "TypeId": type_id,
                "NoOfRoom": no_of_rooms,
                "Remark": remark,
                "IsClosed": is_closed,
                "Closed": "X" if is_closed else "0",
                "HotelId": self.hotel_id,
                "UserId": self.user_id,
            },
        )
