"""
Zoho Books API integration.

Handles:
- OAuth2 token management (refresh token flow)
- Creating expense entries from extracted bill data
- Graceful error handling for malformed extractions and API failures

Zoho Books API docs: https://www.zoho.com/books/api/v3/
"""

import json
import os
import time
from datetime import datetime
from typing import Any

import httpx

from src.config import settings

# Zoho Books API base URLs — data-center aware.
# Zoho uses a different host per region; the OAuth endpoint must match the
# region the account was created in (e.g. Indian accounts use zoho.in).
ZOHO_HOSTS = {
    "com": ("https://accounts.zoho.com", "https://www.zohoapis.com"),
    "in": ("https://accounts.zoho.in", "https://www.zohoapis.in"),
    "eu": ("https://accounts.zoho.eu", "https://www.zohoapis.eu"),
    "au": ("https://accounts.zoho.com.au", "https://www.zohoapis.com.au"),
    "cn": ("https://accounts.zoho.com.cn", "https://www.zohoapis.com.cn"),
}


def _zoho_hosts(data_center: str) -> tuple[str, str]:
    accounts, api = ZOHO_HOSTS.get(data_center, ZOHO_HOSTS["com"])
    return accounts, api


ZOHO_ACCOUNTS_URL, ZOHO_API_HOST = _zoho_hosts(
    getattr(settings, "zoho_data_center", "com")
)
ZOHO_BASE_URL = f"{ZOHO_API_HOST}/books/v3"


class ZohoBooksClient:
    """
    Zoho Books API client with automatic token refresh.

    Usage:
        client = ZohoBooksClient()
        client.create_expense({
            "vendor_name": "ABC Store",
            "amount": 450.00,
            "date": "2025-03-15",
            ...
        })
    """

    def __init__(self):
        self.client_id = settings.zoho_client_id
        self.client_secret = settings.zoho_client_secret
        self.organization_id = settings.zoho_organization_id
        self.redirect_uri = settings.zoho_redirect_uri

        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self._currency_ids: dict[str, str] = {}
        self._account_ids: dict[str, str] = {}

        # Pre-populated refresh token from .env
        self._refresh_token: str | None = settings.zoho_refresh_token or None

    # ── OAuth2 ──────────────────────────────────────────────────────

    def _refresh_access_token(self) -> str:
        """Use refresh token to get a new access token."""
        if not self._refresh_token:
            raise RuntimeError(
                "No refresh token available. "
                "Set ZOHO_REFRESH_TOKEN in .env or follow docs/zoho_setup.md "
                "to complete OAuth2 setup."
            )

        resp = httpx.post(
            f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token",
            data={
                "refresh_token": self._refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        # Tokens from Zoho typically last 1 hour
        self._token_expires_at = time.time() + 3600
        return self._access_token

    def _get_access_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        if not self._access_token or time.time() >= self._token_expires_at:
            return self._refresh_access_token()
        return self._access_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Zoho-oauthtoken {self._get_access_token()}",
            "Content-Type": "application/json",
        }

    def _resolve_currency_id(self, currency_code: str | None) -> str | None:
        """
        Map an ISO currency code to Zoho's numeric currency_id.

        Zoho's expense API expects a currency_id (numeric), not an ISO code.
        Cache the org's currency table after the first call.
        """
        if not currency_code:
            return None
        if currency_code in self._currency_ids:
            return self._currency_ids[currency_code]
        resp = httpx.get(
            f"{ZOHO_BASE_URL}/settings/currencies",
            params={"organization_id": self.organization_id},
            headers=self._headers(),
        )
        if resp.status_code == 200:
            for cur in resp.json().get("currencies", []):
                self._currency_ids[cur["currency_code"]] = cur["currency_id"]
        return self._currency_ids.get(currency_code)

    def _resolve_account_id(self, account_name: str) -> str | None:
        """
        Map a chart-of-accounts name to its account_id.

        The expense API requires account_id (account_name alone is rejected).
        Cache the org's chart of accounts after the first call.
        """
        if account_name in self._account_ids:
            return self._account_ids[account_name]
        resp = httpx.get(
            f"{ZOHO_BASE_URL}/chartofaccounts",
            params={"organization_id": self.organization_id},
            headers=self._headers(),
        )
        if resp.status_code == 200:
            for acc in resp.json().get("chartofaccounts", []):
                self._account_ids[acc["account_name"]] = acc["account_id"]
        return self._account_ids.get(account_name)

    # ── Expense Creation ────────────────────────────────────────────

    def create_expense(self, bill_data: dict) -> dict[str, Any]:
        """
        Create an expense entry in Zoho Books from extracted bill data.

        bill_data expected fields:
            vendor_name  (str | None)
            invoice_number (str | None)
            date         (str | None)  — YYYY-MM-DD
            amount       (float | None)
            currency     (str | None)
            tax_gst      (dict | None) — {gst_number, gst_amount, taxable_value}

        Returns the API response JSON.
        """
        # Build the Zoho Books expense payload
        # Zoho Books expense API: POST /books/v3/expenses?organization_id={org_id}

        date_str = bill_data.get("date")
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")

        vendor_name = bill_data.get("vendor_name") or "Unknown Vendor"
        amount = bill_data.get("amount")
        if amount is None:
            raise ValueError("amount is required to create an expense in Zoho Books")

        currency = bill_data.get("currency") or "INR"
        currency_id = self._resolve_currency_id(currency)
        account_id = self._resolve_account_id(settings.zoho_expense_account)

        # Zoho Books expense payload
        payload = {
            "account_id": account_id,
            "description": f"Bill from {vendor_name}",
            "amount": float(amount),
            "date": date_str,
            "reference_number": bill_data.get("invoice_number") or "",
            "vendor_name": vendor_name,
        }
        if currency_id:
            payload["currency_id"] = currency_id

        # Add tax details if available
        tax_gst = bill_data.get("tax_gst") or {}
        if tax_gst.get("gst_amount"):
            payload["tax_amount"] = float(tax_gst["gst_amount"])
        if tax_gst.get("taxable_value"):
            payload["taxable_value"] = float(tax_gst["taxable_value"])

        # Make API call
        url = f"{ZOHO_BASE_URL}/expenses"
        params = {"organization_id": self.organization_id}

        resp = httpx.post(url, params=params, json=payload, headers=self._headers())

        if resp.status_code in (401, 403):
            # Token may have expired — force refresh and retry once
            self._access_token = None
            resp = httpx.post(url, params=params, json=payload, headers=self._headers())

        if resp.status_code >= 400:
            error_detail = resp.text
            raise RuntimeError(
                f"Zoho Books API error ({resp.status_code}): {error_detail}"
            )

        return resp.json()

    def create_expenses_from_file(
        self, predictions_file: str, max_bills: int | None = None
    ) -> list[dict]:
        """
        Create Zoho expense entries from a predictions JSON file.

        predictions_file should be a JSON array of BillExtraction dicts
        (as produced by the extraction pipeline).
        """
        with open(predictions_file, encoding="utf-8") as f:
            predictions = json.load(f)

        if max_bills:
            predictions = predictions[:max_bills]

        results = []
        for pred in predictions:
            try:
                result = self.create_expense(pred)
                results.append(
                    {
                        "vendor": pred.get("vendor_name"),
                        "amount": pred.get("amount"),
                        "status": "created",
                        "expense_id": result.get("expense", {}).get("expense_id"),
                    }
                )
                print(f"  Created expense: {pred.get('vendor_name')} — ${pred.get('amount')}")
            except (ValueError, RuntimeError, httpx.HTTPError) as e:
                results.append(
                    {
                        "vendor": pred.get("vendor_name"),
                        "amount": pred.get("amount"),
                        "status": "failed",
                        "error": str(e),
                    }
                )
                print(f"  FAILED: {pred.get('vendor_name')} — {e}")

        return results


# ── CLI entry point ────────────────────────────────────────────────

def main():
    """Push extracted predictions to Zoho Books."""
    import argparse

    parser = argparse.ArgumentParser(description="Push bill extractions to Zoho Books")
    parser.add_argument(
        "predictions_file",
        help="JSON file with extracted bill data (array of BillExtraction dicts)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Max number of bills to push (default: all)",
    )
    args = parser.parse_args()

    client = ZohoBooksClient()
    print("Pushing bills to Zoho Books...")
    results = client.create_expenses_from_file(args.predictions_file, max_bills=args.max)

    created = sum(1 for r in results if r["status"] == "created")
    failed = sum(1 for r in results if r["status"] == "failed")
    print(f"\nDone. {created} created, {failed} failed.")


if __name__ == "__main__":
    main()
