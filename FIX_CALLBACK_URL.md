# ⚠️ IMPORTANT: Fix Dhan Callback URL

## 🔴 Critical Issue

Your callback is failing with **404 error** because the redirect URL in Dhan doesn't match.

---

## ✅ Required Fix

### Go to Dhan Developer Portal:

1. **Open:** https://web.dhan.co/
2. **Navigate to:** My Profile → **Access DhanHQ APIs**
3. **Click on:** Your application name
4. **Find:** "Redirect URL" field

### Set the EXACT URL:

```
http://localhost:3000/api/dhan/callback
```

⚠️ **IMPORTANT**: Must be EXACTLY this. No trailing slash, no extra characters.

### Save and Test Again

After saving in Dhan portal:
1. Restart your dev server (`npm run dev`)
2. Clear browser cache
3. Try connecting again

---

## Why This Matters

After you authenticate on Dhan's website, Dhan redirects you back to your app with this URL:

```
http://localhost:3000/api/dhan/callback?tokenId=XXXX
```

If the redirect URL in Dhan's settings doesn't match **exactly**, you'll get a 404 error.

---

## How to Verify It's Working

### Before the fix:
```
❌ Redirects to: http://localhost:3000/api/dhan/callback?tokenId=XXX
❌ Shows: "404 - This page could not be found"
❌ Database: Empty user_trading_keys table
```

### After the fix:
```
✅ Redirects to: http://localhost:3000/dashboard?success=true
✅ Shows: "Account Connected Successfully! 🎉" toast
✅ Database: Row added to user_trading_keys table with your access token
```

---

## Screenshot of Where to Set It

In Dhan's interface, you'll see something like:

```
┌─────────────────────────────────────────┐
│  Application Name: [Your App Name]     │
├─────────────────────────────────────────┤
│  API Key: [Your API Key]                │
│  API Secret: [Hidden]                   │
│                                         │
│  Redirect URL:                          │
│  ┌─────────────────────────────────┐  │
│  │ http://localhost:3000/api/dhan/ │  │
│  │ callback                         │  │
│  └─────────────────────────────────┘  │
│                                         │
│  Postback URL (Optional):              │
│  ┌─────────────────────────────────┐  │
│  │                                  │  │
│  └─────────────────────────────────┘  │
│                                         │
│  [Save] [Cancel]                       │
└─────────────────────────────────────────┘
```

---

## For Production (Later)

When you deploy to production (e.g., Vercel), you'll need to:

1. Add a new redirect URL in Dhan:
   ```
   https://your-domain.vercel.app/api/dhan/callback
   ```

2. Update `.env.local` → `.env.production`:
   ```env
   NEXT_PUBLIC_APP_URL=https://your-domain.vercel.app
   ```

Dhan allows multiple redirect URLs, so you can have both localhost and production.

---

**Fix this FIRST** before trying to connect again! 🚀
