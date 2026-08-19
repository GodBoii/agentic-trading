-- 1. Create the table to store User Credentials
create table public.user_trading_keys (
  id uuid not null default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  
  -- Dhan Specific Credentials
  dhan_client_id text not null,
  dhan_access_token text not null, -- Storing as plain text per your request (Relying on RLS)
  
  -- Logic Control
  is_trading_enabled boolean default false, -- The "Start/Stop" switch
  token_expiry timestamptz,
  
  -- Audit Timestamps
  created_at timestamptz default timezone('utc', now()),
  updated_at timestamptz default timezone('utc', now()),
  
  primary key (id),
  unique (user_id) -- Ensures one set of keys per user
);

-- 2. Enable Row Level Security (RLS) - The Security Layer
alter table public.user_trading_keys enable row level security;

-- 3. Create Security Policies
-- Policy: Users can only SEE their own keys
create policy "Users can view own keys" 
on public.user_trading_keys for select 
using (auth.uid() = user_id);

-- Policy: Users can INSERT/UPDATE their own keys
create policy "Users can manage own keys" 
on public.user_trading_keys for all 
using (auth.uid() = user_id);

-- 4. Create Performance Index
-- This helps the Python Backend instantly find all users who have turned "ON" trading
create index idx_active_traders on public.user_trading_keys(is_trading_enabled) 
where is_trading_enabled = true;