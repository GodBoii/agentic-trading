# Phase 2 Implementation: Connect to Dhan Flow

## ✅ Completed Features

### 1. **API Routes**
- ✅ **POST /api/dhan/auth** - Generates Dhan consent URL
- ✅ **GET /api/dhan/callback** - Handles OAuth callback and stores tokens

### 2. **Frontend Components**
- ✅ **DhanConnect** (`components/dhan-connect.tsx`) - UI to input Client ID and initiate connection
- ✅ **TradingStatus** (`components/trading-status.tsx`) - Shows connection status and trading toggle
- ✅ **Dashboard** (`app/dashboard/page.tsx`) - Main dashboard with all components integrated

### 3. **User Experience**
- ✅ Success/Error toast notifications
- ✅ Token expiry detection
- ✅ Loading states and error handling
- ✅ Responsive design with Tailwind CSS
- ✅ Dark mode support

## 🚀 Setup Instructions

### Step 1: Configure Environment Variables

Copy the example environment file:
```bash
cp .env.example .env.local
```

Update `.env.local` with your actual values:

```env
# App URL (use your Vercel domain in production)
NEXT_PUBLIC_APP_URL=http://localhost:3000

# Supabase Configuration
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key_here

# Dhan API Credentials (from Dhan Developer Portal)
DHAN_APP_ID=your_dhan_api_key
DHAN_APP_SECRET=your_dhan_api_secret
```

### Step 2: Install Dependencies

```bash
npm install
```

### Step 3: Run the Development Server

```bash
npm run dev
```

Visit `http://localhost:3000` and you'll be redirected to login.

## 📋 User Flow

### First-Time Setup
1. **Sign Up/Login** - User creates account or logs in
2. **Redirected to Dashboard** - Lands on `/dashboard`
3. **Connect Dhan Account**:
   - Enter Dhan Client ID in the "Connect to Dhan" card
   - Click "Connect Account"
   - Redirected to Dhan's login page
   - Enter Dhan password
   - Redirected back to dashboard with success message
4. **Enable Trading**:
   - Toggle the "AI Trading" switch in the "Trading Status" card
   - System is now ready to execute trades

### Returning Users
1. Login → Dashboard
2. See connection status and current trading state
3. Can toggle trading on/off anytime

## 🔒 Security Features

### Database Security (RLS)
- Row Level Security ensures users can only access their own data
- Tokens stored as plain text but protected by RLS policies
- Service role key bypassed only by Python backend (not implemented yet)

### API Security
- All API routes verify user authentication
- Dhan credentials validated server-side
- Error messages don't expose sensitive information

## 📁 File Structure

```
app/
├── api/
│   └── dhan/
│       ├── auth/
│       │   └── route.ts          # Initiates OAuth flow
│       └── callback/
│           └── route.ts          # Handles OAuth callback
├── dashboard/
│   └── page.tsx                  # Main dashboard
├── login/
│   └── page.tsx                  # Login page
├── signup/
│   └── page.tsx                  # Signup page
├── page.tsx                      # Root redirect
├── layout.tsx                    # Root layout
└── globals.css                   # Global styles + animations

components/
├── dhan-connect.tsx              # Connect to Dhan component
└── trading-status.tsx            # Trading status & toggle
```

## 🔧 API Endpoints

### POST /api/dhan/auth
**Request:**
```json
{
  "dhanClientId": "1000054321"
}
```

**Response:**
```json
{
  "url": "https://auth.dhan.co/login/consentApp-login?consentAppId=..."
}
```

**Errors:**
- `401` - User not authenticated
- `400` - Missing or invalid Client ID
- `500` - Server configuration error or Dhan API failure

### GET /api/dhan/callback?tokenId=xxx
**Flow:**
1. Dhan redirects here after user authentication
2. Exchanges `tokenId` for `accessToken`
3. Stores credentials in `user_trading_keys` table
4. Redirects to `/dashboard?success=true`

**Error Redirects:**
- `/dashboard?error=missing_token`
- `/dashboard?error=unauthorized`
- `/dashboard?error=token_exchange_failed`
- `/dashboard?error=db_save_failed`

## 🗄️ Database Schema

The `user_trading_keys` table structure:

```sql
CREATE TABLE user_trading_keys (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id),
  dhan_client_id TEXT NOT NULL,
  dhan_access_token TEXT NOT NULL,
  is_trading_enabled BOOLEAN DEFAULT false,
  token_expiry TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id)
);
```

## 🎨 UI Components

### DhanConnect
- Input for Dhan Client ID
- Validates input before submission
- Shows loading state during API call
- Displays security information

### TradingStatus
- Shows "Not Connected" if no keys found
- Displays Client ID when connected
- Toggle switch for `is_trading_enabled`
- Detects and warns about expired tokens
- Real-time updates via Supabase

## 🧪 Testing Checklist

- [ ] User can sign up and login
- [ ] Login redirects to dashboard
- [ ] Can enter Client ID and initiate connection
- [ ] Dhan login page opens correctly
- [ ] After Dhan authentication, redirected back with success toast
- [ ] Trading status shows "Connected ✅"
- [ ] Toggle switch updates database
- [ ] Sign out works properly
- [ ] Error handling works for invalid Client ID
- [ ] Token expiry warning shows when applicable

## 🔄 Next Steps (Phase 3)

After Phase 2 is complete and tested:

1. **Python Backend Setup**
   - Docker configuration
   - Supabase connection with service key
   - Dhan API integration for market data

2. **Multi-Agent System**
   - Scout Agent (market scanning)
   - Technical Analysis Agent
   - Sentiment Analysis Agent
   - Commander Agent (trade decisions)

3. **Execution Engine**
   - Fetch all active users from `user_trading_keys`
   - Execute trades using individual access tokens
   - Log results in `user_trade_logs`

## 🐛 Troubleshooting

### "Server configuration error"
- Check that `DHAN_APP_ID` and `DHAN_APP_SECRET` are set in `.env.local`
- Restart the dev server after adding env variables

### "Failed to initiate Dhan authentication"
- Verify your Dhan API credentials are correct
- Check Dhan API status
- Ensure redirect URL is whitelisted in Dhan dashboard

### "Database save failed"
- Verify Supabase RLS policies are set up correctly
- Check Supabase logs for detailed error messages
- Ensure user is authenticated

### Toggle not working
- Check browser console for errors
- Verify RLS policy allows UPDATE operations
- Ensure user is connected first

## 📚 Resources

- [Dhan API Documentation](https://dhanhq.co/docs/)
- [Supabase Row Level Security](https://supabase.com/docs/guides/auth/row-level-security)
- [Next.js App Router](https://nextjs.org/docs/app)
- [Tailwind CSS](https://tailwindcss.com/)

---

**Status:** Phase 2 Implementation Complete ✅
