Here is the completely updated context.md.

This file now reflects the simplified security model (relying on Supabase RLS instead of custom encryption), the exact database schema we agreed upon, and the complete environment variable list required for the next steps.

Save this file to your project root.

code
Markdown
download
content_copy
expand_less
# Project Context: Agentic Trading System

## 1. Executive Summary
We are building a **fully automated, AI-driven algorithmic trading platform** using a hierarchical Multi-Agent System.
- **User Side:** Users log in, connect their Dhan brokerage account via OAuth (API Key Flow), and toggle "Start Trading".
- **System Side:** A centralized Python backend performs market analysis using a "Master Account" (Data API).
- **Execution:** When the AI decides to trade, it executes orders on behalf of all active users using their individual (Free) Trading API keys stored securely in Supabase.

---

## 2. Tech Stack

### Frontend & Auth
- **Framework:** Next.js 14 (App Router)
- **Database:** Supabase (PostgreSQL)
- **Auth:** Supabase Auth + Custom Dhan OAuth Flow
- **Security:** Supabase Row Level Security (RLS) + Transparent Data Encryption (TDE)

### Backend (The Intelligence)
- **Runtime:** Python 3.11+ (Dockerized)
- **Orchestrator:** Agno (formerly Phidata)
- **Data Analysis:** Pandas, TA-Lib
- **Broker Interface:** `dhanhq-py`
- **LLMs:** OpenAI (GPT-4o), Gemini Flash, or DeepSeek (via OpenRouter/Groq)

---

## 3. Database Schema (Supabase)

### A. User Credentials (The Vault)
**Table:** `user_trading_keys`
*Stores user tokens. Protected by strict RLS policies.*
- `id`: UUID (Primary Key)
- `user_id`: UUID (FK to auth.users)
- `dhan_client_id`: Text (e.g., "100054")
- `dhan_access_token`: Text (Stored plain, protected by RLS)
- `is_trading_enabled`: Boolean (The Master Switch)
- `token_expiry`: Timestamptz
- `created_at`: Timestamptz
- `updated_at`: Timestamptz

### B. Agent Intelligence (The Brain)
**Table:** `daily_scans` (The Scout)
- `id`: UUID
- `date`: Date
- `symbol`: Text
- `scan_result`: Text ("SHORTLISTED", "DISCARDED")
- `initial_signal`: Text ("BULLISH", "BEARISH")

**Table:** `analysis_reports` (The Analysts)
- `id`: UUID
- `scan_id`: FK to daily_scans
- `agent_type`: Text ("TECHNICAL", "SENTIMENT")
- `report_data`: JSONB (Full analysis details)
- `sentiment_score`: Integer

**Table:** `trade_decisions` (The Commander)
- `id`: UUID
- `scan_id`: FK to daily_scans
- `symbol`: Text
- `action`: Text ("BUY", "SELL", "HOLD")
- `reasoning`: Text
- `is_executed`: Boolean

### C. Execution Logs
**Table:** `user_trade_logs`
- `id`: UUID
- `user_id`: FK to auth.users
- `decision_id`: FK to trade_decisions
- `dhan_order_id`: Text
- `status`: Text ("SUCCESS", "FAILED")
- `failure_reason`: Text

---

## 4. Environment Variables Reference

### Frontend (.env.local)
```env
# App Configuration
NEXT_PUBLIC_APP_URL=http://localhost:3000

# Supabase Keys
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...

# Dhan Application Keys (For generating Login Links)
DHAN_APP_ID=your_api_key_here
DHAN_APP_SECRET=your_api_secret_here
Python Backend (.env)
code
Env
download
content_copy
expand_less
# Database Access (Bypasses RLS)
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...

# Master Account for Market Data (PAID API)
ADMIN_DHAN_CLIENT_ID=...
ADMIN_DHAN_ACCESS_TOKEN=...

# AI Models
OPENAI_API_KEY=...
5. Implementation Roadmap
Phase 1: Foundation (Completed)

Database Schema Design

RLS Security Policies

Performance Indexing

Phase 2: User Onboarding (Current)

API Route: POST /api/dhan/auth (Generate Consent)

API Route: GET /api/dhan/callback (Exchange Token & Save to DB)

UI Component: Connect Button & Input Field

UI Component: Trading Status Toggle

Phase 3: Python Agent Core (Next)

Docker Setup

Market Data Connection (Admin Key)

User Session Manager (Fetch tokens from DB)

The "Scout" Agent Implementation

Phase 4: The Loop

Specialist Agents (Technical/Sentiment)

Commander Agent (Decision Making)

Execution Engine (Iterate Users -> Place Orders)

code
Code
download
content_copy
expand_less