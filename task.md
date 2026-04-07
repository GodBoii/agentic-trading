Here is the detailed implementation plan for Phase 2: The "Connect to Dhan" Flow. This plan breaks down exactly which files you need to create, where they go, and the specific logic required inside each one.

Phase 2: Implementation Plan

Objective: Build the interface and API logic to securely exchange a user's Dhan Client ID for an Access Token and store it in your database.

Step 1: Environment Configuration

We need to configure the secrets that allow your application to talk to Dhan's Auth Servers.

File: .env.local

Action: Add the following variables.

DHAN_APP_ID: Your Application's API Key (from Dhan Dashboard).

DHAN_APP_SECRET: Your Application's Secret Key.

NEXT_PUBLIC_APP_URL: The base URL of your app (e.g., http://localhost:3000 for dev, your Vercel domain for prod).

Step 2: The "Initiate Auth" API Route

This endpoint acts as the bridge. It takes the User's ID and asks Dhan for a permission slip (Consent ID).

File Location: app/api/dhan/auth/route.ts

Method: POST

Logic:

Auth Check: Verify the user is logged into your website (via Supabase Auth). If not, return 401.

Input Validation: Receive the dhanClientId from the request body. Ensure it's not empty.

External Call: Make a POST request to Dhan's /generate-consent endpoint.

Header: Pass your DHAN_APP_ID and DHAN_APP_SECRET.

Response Handling:

If successful, Dhan returns a consentId.

Construct the official login URL: https://auth.dhan.co/login/consentApp-login?consentAppId=...

Return: Send this URL back to the frontend as JSON { url: "..." }.

Step 3: The "Callback" API Route

This is the destination where Dhan sends the user back after they enter their password. This is where the magic happens.

File Location: app/api/dhan/callback/route.ts

Method: GET

Logic:

Param Extraction: Parse the URL to find the tokenId query parameter.

Auth Check: Verify the user is logged in via Supabase.

Token Exchange: Make a POST request to Dhan's /consumeApp-consent endpoint.

Body/Param: Pass the tokenId.

Header: Pass your DHAN_APP_ID and DHAN_APP_SECRET.

DB Operation: Upon success, you receive the accessToken. Use Supabase Admin (or Server Client) to perform an UPSERT operation on the user_trading_keys table.

Match user by user_id.

Save: dhan_client_id, dhan_access_token, token_expiry.

Set: is_trading_enabled to false (Default to safe mode).

Redirect: Redirect the user's browser back to your main dashboard page (/dashboard?success=true).

Step 4: Frontend "Connect" Component

The UI element where the user types their ID.

File Location: components/dhan-connect.tsx

Key Features:

State: Holds the input value (clientId) and loading state (isLoading).

Function: handleConnect()

Calls your own API (/api/dhan/auth).

Receives the URL.

Performs window.location.href = url to navigate the user away to Dhan.

Visuals: An input box and a "Connect" button. Disable the button while loading.

Step 5: Frontend "Status & Toggle" Component

The UI element that shows if they are connected and lets them start/stop the AI.

File Location: components/trading-status.tsx

Key Features:

Data Fetching: On load, query the user_trading_keys table from Supabase to check if a row exists for this user.

Conditional Rendering:

If no row found: Show "Not Connected".

If row found: Show "Connected ✅" and the Toggle Switch.

Toggle Logic:

When the switch is clicked, update the is_trading_enabled column in Supabase directly to true or false.

Note: Since we set up RLS in Phase 1, the frontend is allowed to do this update securely.

Step 6: The Dashboard Page

Putting it all together.

File Location: app/dashboard/page.tsx (or wherever your main view is).

Logic:

Import <DhanConnect />.

Import <TradingStatus />.

Check URL search params for ?success=true to show a toast notification ("Account Connected Successfully!").

Summary of Data Flow

User -> Enters ID -> Click Connect.

Next.js API -> Calls Dhan -> Gets Link.

User -> Goes to Dhan -> Logs in -> Comes back with tokenId.

Next.js API -> Swaps tokenId for accessToken -> Saves to Supabase.

User -> Sees "Connected" badge -> Toggles "Start Trading".

Ready to write the code for Step 1 (Environment) and Step 2 (Auth Route)?