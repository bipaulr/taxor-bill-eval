# Zoho Books API Setup Guide

## 1. Create a Zoho Books Free Account

1. Go to https://www.zoho.com/books/signup/ and sign up for the Free Plan.
2. Note your **Organization ID**:
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

1. Build the authorization URL (open in browser):
   ```
   https://accounts.zoho.com/oauth/v2/auth?
   scope=ZohoBooks.fullaccess.all&
   client_id=YOUR_CLIENT_ID&
   response_type=code&
   redirect_uri=https://www.zoho.com/books/&
   access_type=offline
   ```
   (Replace `YOUR_CLIENT_ID` with your actual Client ID.)

2. After authorizing, the browser redirects to `https://www.zoho.com/books/?code=...`
   — **copy the full URL** from the address bar.

3. Extract the `code` parameter value from the URL.

4. Exchange the code for tokens using this command (replace `CODE`, `CLIENT_ID`, `CLIENT_SECRET`):
   ```cmd
   curl -X POST "https://accounts.zoho.com/oauth/v2/token" ^
     -d "code=YOUR_CODE" ^
     -d "client_id=YOUR_CLIENT_ID" ^
     -d "client_secret=YOUR_CLIENT_SECRET" ^
     -d "redirect_uri=https://www.zoho.com/books/" ^
     -d "grant_type=authorization_code"
   ```

5. You'll get a JSON response like:
   ```json
   {
     "access_token": "...",
     "refresh_token": "...",
     "expires_in": 3600
   }
   ```

6. Copy the **refresh_token** value and add it to `.env`:
   ```
   ZOHO_REFRESH_TOKEN=your_refresh_token_here
   ```

## 4. Verify the Connection

Run:
```cmd
py -c "from src.zoho_integration import ZohoBooksClient; c = ZohoBooksClient(); print('Token works!')"
```

If it succeeds without errors, your Zoho Books integration is ready.

## 5. Push Expenses

```cmd
py src\zoho_integration.py eval\results\extractions.json --max 5
```

This pushes the first 5 bill extractions as expense entries in Zoho Books.

## Notes

- Access tokens expire after 1 hour. The client auto-refreshes using the refresh token.
- The Free Plan supports up to 1000 contacts, 50 invoices/year, etc. — sufficient for this project.
- Zoho Books API rate limit: 100 requests per minute for the Free Plan.
