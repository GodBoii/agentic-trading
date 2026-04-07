# 🔧 Troubleshooting Guide - Dhan Connection Issues

## Issues Identified

1. ❌ **404 on callback** - The callback route isn't being reached
2. ❌ **Empty database table** - Data not saved to user_trading_keys
3. ❌ **Login not persisting** - Session doesn't stay between page refreshes
4. ✅ **Favicon added** - Icon now in place

---

## Root Cause Analysis

### Issue 1: Callback 404 Error

The 404 error on `/api/dhan/callback?tokenId=...` means:
- The route exists (we created it)
- But Next.js isn't recognizing it properly

**Possible Causes:**
1. App not restarted after creating routes
2. Route file not properly exported
3. Middleware blocking the route

### Issue 2: Empty Database

The `user_trading_keys` table is empty because:
- The callback route fails with 404
- So the upsert operation never runs
- No data gets saved

### Issue 3: Session Not Persisting

This could be due to:
- Supabase session cookies not being properly set
- Middleware not refreshing sessions correctly
- Browser clearing cookies

---

## Fixes Applied

### ✅ 1. Favicon Added
- Created `/public` folder
- Copied `icon.png` from `assets/` to `public/`
- Updated `app/layout.tsx` with favicon metadata

### ✅ 2. Updated Root Layout
```typescript
export const metadata: Metadata = {
  title: "Agentic Trading - AI-Powered Trading Platform",
  description: "Automated trading powered by AI agents",
  icons: {
    icon: '/icon.png',
    apple: '/icon.png',
  },
};
```

---

## Steps to Fix Callback Issue

### Step 1: Verify Environment Variables

Make sure your `.env.local` has:
```env
NEXT_PUBLIC_APP_URL=http://localhost:3000
DHAN_APP_ID=your_app_id
DHAN_APP_SECRET=your_app_secret
```

### Step 2: Check Dhan Developer Portal

In your Dhan API settings at https://web.dhan.co:
1. Go to **DhanHQ Trading APIs**
2. Click on your application
3. **Redirect URL should be EXACTLY:**
   ```
   http://localhost:3000/api/dhan/callback
   ```
4. Save the changes

### Step 3: Restart Dev Server

```bash
# Stop the current server (Ctrl+C)
# Then restart:
npm run dev
```

### Step 4: Clear Browser Cache

1. Open DevTools (F12)
2. Right-click the refresh button
3. Select "Empty Cache and Hard Reload"

### Step 5: Test Connection Again

1. Go to http://localhost:3000
2. Login
3. Enter Dhan Client ID
4. Click "Connect Account"
5. Complete the Dhan OAuth flow

---

## Understanding Dhan API Keys

### There are 3 different credentials:

1. **Dhan Client ID** (Your trading account ID)
   - Example: `1000000001`
   - This is YOUR account number
   - Users enter this in the UI

2. **Trading API Key & Secret** (For your app)
   - `DHAN_APP_ID` in `.env.local`
   - `DHAN_APP_SECRET` in `.env.local`
   - This is for your APPLICATION
   - **FREE** - No cost

3. **Access Token** (Generated after OAuth)
   - Returned from Dhan after user connects
   - Stored in `user_trading_keys` table
   - Valid for 30 days
   - Used to make trading API calls

### ❌ You do NOT need Data API for Phase 2

The Data API (₹499/month) is different:
- Used for getting live market feed
- Not needed for Phase 2 (user onboarding)
- You use **Trading API** which is FREE


---

## Session Persistence Issue

### Why Sessions Might Not Persist:

1. **Cookies not being saved**
   - Check browser's cookie settings
   - Allow cookies for localhost

2. **Supabase session expired**
   - Default: 1 hour
   - Can be extended in Supabase dashboard

3. **Browser in incognito mode**
   - Incognito doesn't persist cookies

### To Fix Session Persistence:

**Extend Session Duration in Supabase:**
1. Go to Supabase Dashboard
2. Navigate to **Authentication** → **Settings**
3. Scroll to **Auth Settings**
4. Set **JWT Expiry** to  `604800` (7 days)
5. Save

---

## Database Schema Validation

Your `user_trading_keys` table should have:

```sql
 Columns:
- id (uuid, primary key)
- user_id (uuid, references auth.users, unique)
- dhan_client_id (text)
- dhan_access_token (text)
- is_trading_enabled (boolean, default false)
- token_expiry (timestamptz)
- created_at (timestamptz)
- updated_at (timestamptz)

✅ RLS Enabled
✅ Policies for SELECT and ALL operations
```

### Verify Table Exists:

1. Open Supabase Dashboard
2. Go to **Table Editor**
3. Check if `user_trading_keys` exists
4. If not, run the SQL from `supabase-structure.txt`

---

## Testing Checklist

### Before Testing:
- [ ] `.env.local` has all required variables
- [ ] Dhan redirect URL matches exactly
- [ ] Dev server restarted completely
- [ ] Browser cache cleared
- [ ] `user_trading_keys` table exists in Supabase
- [ ] RLS policies are enabled

### During Connection Flow:
1. [ ] Login works
2. [ ] Redirected to `/dashboard`
3. [ ] Can enter Dhan Client ID
4. [ ] Click "Connect Account"
5. [ ] Redirected to Dhan login page (not 404)
6. [ ] Enter Dhan password successfully
7. [ ] Redirected back to dashboard
8. [ ] See success toast: "Account Connected Successfully! 🎉"
9. [ ] Trading Status shows "Connected ✅"
10. [ ] Check Supabase: `user_trading_keys` has 1 row

### Verify Data Saved:
```sql
-- Run this in Supabase SQL Editor:
SELECT * FROM user_trading_keys;

-- You should see:
-- user_id, dhan_client_id, dhan_access_token, is_trading_enabled, token_expiry
```

---

## Common Errors & Solutions

### Error: "404 on callback"
**Solution:** 
- Check redirect URL in Dhan matches exactly
- Restart dev server
- Clear browser cache

### Error: "Unauthorized"
**Solution:**
- Login again
- Check Supabase session is valid
- Ensure cookies are enabled

### Error: "Dhan account not connected"
**Solution:**
- Complete the connection flow first
- Check `user_trading_keys` table has data
- Verify token hasn't expired

### Error: "Failed to fetch holdings/positions/funds"
**Solution:**
- Ensure you completed connection successfully
- Check access token is valid in database
- Verify Dhan API is responding

---

## Debug Commands

### Check if routes are compiled:
```
Look in terminal for:
✓ Compiled /api/dhan/callback in XXXms
```

### Check Supabase connection:
```typescript
// In browser console on /dashboard:
const supabase = createClient()
const { data, error } = await supabase.auth.getUser()
console.log(data, error)
```

### Check environment variables are loaded:
```
Look in terminal startup for:
- Environments: .env.local
```

---

## Next Steps After Successful Connection

Once connected successfully:
1. ✅ Dashboard shows "Connected ✅"
2. ✅ Portfolio data loads (funds, holdings, positions)
3. ✅ AI Trading toggle becomes functional
4. ✅ Ready for Phase 3 (Python backend)

---

**Status:** Troubleshooting documentation ready
**Action Required:** Follow steps above to test connection again
