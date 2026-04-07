# 🔧 API Endpoint Fix - Dhan v2.0

## Issue Fixed ✅

The initial implementation was using incorrect Dhan API endpoints. I've updated both routes to use the **correct Dhan API v2.0** endpoints.

---

## Changes Made

### 1. **Auth Route** (`app/api/dhan/auth/route.ts`)

**Before:**
```typescript
const dhanAuthUrl = 'https://api.dhan.co/v2/oauth/generate-consent'
headers: {
  'client-id': DHAN_APP_ID,
  'client-secret': DHAN_APP_SECRET,
}
body: JSON.stringify({ clientId, redirectUrl })
```

**After:**
```typescript
const dhanAuthUrl = `https://auth.dhan.co/app/generate-consent?client_id=${dhanClientId}`
headers: {
  'app_id': DHAN_APP_ID,
  'app_secret': DHAN_APP_SECRET,
}
// No body needed
```

**Changes:**
- ✅ Fixed endpoint URL
- ✅ Changed headers from `client-id`/`client-secret` to `app_id`/`app_secret`
- ✅ Moved client_id to query parameter
- ✅ Removed body from request
- ✅ Changed response field from `consentId` to `consentAppId`

---

### 2. **Callback Route** (`app/api/dhan/callback/route.ts`)

**Before:**
```typescript
const dhanTokenUrl = 'https://api.dhan.co/v2/oauth/consumeApp-consent'
method: 'POST'
headers: {
  'client-id': DHAN_APP_ID,
  'client-secret': DHAN_APP_SECRET,
}
body: JSON.stringify({ tokenId })
```

**After:**
```typescript
const dhanTokenUrl = `https://auth.dhan.co/app/consumeApp-consent?tokenId=${tokenId}`
// Default GET method
headers: {
  'app_id': DHAN_APP_ID,
  'app_secret': DHAN_APP_SECRET,
}
// No body needed
```

**Changes:**
- ✅ Fixed endpoint URL
- ✅ Changed from POST to GET
- ✅ Changed headers from `client-id`/`client-secret` to `app_id`/`app_secret`
- ✅ Moved tokenId to query parameter
- ✅ Removed body from request
- ✅ Response now expects `dhanClientId` (already correct)

---

## Correct Dhan OAuth Flow (v2.0)

### Step 1: Generate Consent
```bash
POST https://auth.dhan.co/app/generate-consent?client_id={dhanClientId}
Headers:
  app_id: {your_api_key}
  app_secret: {your_api_secret}

Response:
{
  "consentAppId": "940b0ca1-3ff4-4476-b46e-03a3ce7dc55d",
  "consentAppStatus": "GENERATED",
  "status": "success"
}
```

### Step 2: Browser Login
```
https://auth.dhan.co/login/consentApp-login?consentAppId={consentAppId}

User enters credentials → Redirects to:
{your_redirect_url}/?tokenId={tokenId}
```

### Step 3: Consume Consent
```bash
GET https://auth.dhan.co/app/consumeApp-consent?tokenId={tokenId}
Headers:
  app_id: {your_api_key}
  app_secret: {your_api_secret}

Response:
{
  "dhanClientId": "1000000001",
  "dhanClientName": "JOHN DOE",
  "dhanClientUcc": "CEFE4265",
  "givenPowerOfAttorney": true,
  "accessToken": "{access_token}",
  "expiryTime": "2025-09-23T12:37:23"
}
```

---

## Testing

Now the API should work correctly. Try:

1. Go to `/dashboard`
2. Enter your Dhan Client ID
3. Click "Connect Account"
4. You should be redirected to Dhan's login page (not get a 500 error)
5. Login with your Dhan credentials
6. Get redirected back with success message

---

## Documentation Reference

- [Dhan API v2.0 Authentication](https://dhanhq.co/docs/v2/authentication/)
- Individual Trader flow is what we're using
- Partners flow is different (uses different endpoints)

---

**Status**: ✅ API Endpoints Fixed  
**Ready**: For testing with actual Dhan credentials
