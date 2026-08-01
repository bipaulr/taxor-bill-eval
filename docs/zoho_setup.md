# Zoho Books API Setup Guide

## 0. Data center first!

Zoho runs separate regions (`com` = US/Global, `in` = India, `eu` = Europe,
`au` = Australia, `cn` = China). **Use the region your account was created in** —
Indian accounts use `*.zoho.in`, and OAuth/API calls to `.com` will fail with
`invalid_client` / 404. Set it in `.env`:

```
ZOHO_DATA_CENTER=in
```

## 1. Create a Zoho Books Free Account

1. Go to https://www.zoho.com/books/signup/ and sign up for the Free Plan
   (use the region domain that matches your account, e.g. `zoho.in` in India).
2. Create a **New Organization** (any name; country/currency should match your bills).
3. Note your **Organization ID**:
   - Go to Settings → Organization → General
   - Copy the Organization ID from the URL or the settings page.

## 2. Register a Self-Client in Zoho API Console

1. Go to https://api-console.zoho.com/
2. Click **Add Client** → **Self-Client**.
3. Fill in:
   - **Client Name**: `Taxor BillEval` (or anything)
   - **Homepage URL**: `https://github.com/bipaulr/taxor-bill-eval`
   - **Authorized Redirect URI**: `https://www.zoho.com/books/`
4. Click **Create**.
5. Copy the **Client ID** and **Client Secret** — add them to `.env`:
   ```
   ZOHO_CLIENT_ID=your_client_id_here
   ZOHO_CLIENT_SECRET=your_client_secret_here
   ZOHO_REDIRECT_URI=https://www.zoho.com/books/
   ZOHO_ORGANIZATION_ID=your_org_id_here
   ```

## 3. Generate a Refresh Token

### Option A — via the API Console "Generate Token" (simplest)

1. In the API Console on your client page, scroll to **Generate Token**.
2. Scope: `ZohoBooks.fullaccess.all`, pick a time duration, add a description.
3. Click **Create**. Zoho downloads a `self_client.json` containing a **grant
   `code`** (NOT a refresh token) plus the client credentials.
4. Exchange that `code` for a long-lived refresh token:
   ```cmd
   py -X utf8 -c "import httpx,json; d=json.load(open('Downloads/self_client.json')); r=httpx.post('https://accounts.zoho.in/oauth/v2/token', data={'code':d['code'],'client_id':d['client_id'],'client_secret':d['client_secret'],'redirect_uri':'https://www.zoho.com/books/','grant_type':'authorization_code'}); print(r.text)"
   ```
   (Use `accounts.zoho.in` for Indian accounts — match your `ZOHO_DATA_CENTER`.)
5. Copy the **refresh_token** from the response into `.env`.

### Option B — via the OAuth redirect

1. Open (URL-encoded `redirect_uri`; use your region's accounts host):
   ```
   https://accounts.zoho.in/oauth/v2/auth?scope=ZohoBooks.fullaccess.all&client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=https%3A%2F%2Fwww.zoho.com%2Fbooks%2F&access_type=offline
   ```
2. Accept → copy the full redirected URL → extract the `code` param.
3. Exchange it with `grant_type=authorization_code` against your region's
   `/oauth/v2/token` endpoint as above.

## 4. Verify the Connection

Run:
```cmd
py -c "from src.zoho_integration import ZohoBooksClient; c = ZohoBooksClient(); t = c._refresh_access_token(); print('Token works!')"
```

If it succeeds, the integration is ready. (Tip: don't run this repeatedly in a
hurry — Zoho throttles the token endpoint with "too many requests continuously".)

## 5. Push Expenses

```cmd
py run.py zoho-push eval/results/predictions/handwritten_gemini-3-flash-preview.json --max 5
```

This pushes bill extractions as expense entries in Zoho Books.

## Gotchas (all hit during this project)

- **Data center mismatch** → `invalid_client` on OAuth, 404 on API. Fix `ZOHO_DATA_CENTER`.
- **Expense account**: the expense API rejects `account_name` — it needs an
  `account_id` from `/chartofaccounts`. The client resolves it from
  `ZOHO_EXPENSE_ACCOUNT` (default `Uncategorized`, present in new orgs).
- **Currency**: the expense API needs a numeric `currency_id` (from
  `/settings/currencies`), not an ISO code. The client resolves it automatically.
- **Console "Generate Token" gives a grant `code`**, not a refresh token — you
  must exchange it (see above).
- **Unicode**: Malayalam vendor names crash cp1252 consoles — run via
  `py run.py ...` (reconfigured to UTF-8) or `py -X utf8`.

## Notes

- Access tokens expire after 1 hour; the client auto-refreshes via the refresh token.
- The Free Plan is sufficient for this project (expenses, contacts, etc.).
