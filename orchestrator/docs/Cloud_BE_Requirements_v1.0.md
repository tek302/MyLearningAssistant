# 📘 Cloud Backend Requirements v1.0

**Project:** Learning Assistant MVP\
**Status:** Week6 complete (Local E2E done)\
**Next Phase:** Local Android → FastAPI (Real Firebase Token) E2E
validation → Cloud Run (tick-driven)

------------------------------------------------------------------------

# 1️⃣ Current Architecture (After Week6)

## Overall Flow

Android App\
↓ (Firebase ID Token)\
FastAPI Backend (Local / Cloud Run)\
↓\
Supabase Postgres (+ pgvector)\
↓\
OpenAI (Embeddings + RAG + Summary)

------------------------------------------------------------------------

# 2️⃣ Authentication Model (Finalized)

## Android

-   Firebase Auth (Google Sign-In)
-   Every API request attaches: Authorization: Bearer
    `<Firebase_ID_Token>`{=html}
-   Token cached in-memory (\~50 min)

## Backend (FastAPI)

-   get_user_id():
    -   Verifies Firebase ID token via Firebase Admin SDK
    -   Returns uid (firebase_uid)
-   DB layer:
    -   resolve_user_id(firebase_uid) → maps to users.id (uuid)
-   No arbitrary user strings accepted in production
-   AUTH_BYPASS_USER_ID allowed only if:
    -   APP_ENV=local
    -   OR DEBUG=true

## Security Guarantees

-   No token logging
-   401 for invalid/missing token
-   Ownership enforced:
    -   /ingest/status
    -   /documents
    -   /rag/answer

------------------------------------------------------------------------

# 3️⃣ Database Model (Auth-related)

## users table

  column         type          note
  -------------- ------------- -------------
  id             uuid          internal PK
  firebase_uid   text          UNIQUE
  created_at     timestamptz   

## resolve_user_id behavior (final)

-   Treat input strictly as firebase_uid
-   Insert if missing
-   Return users.id
-   No UUID branch

------------------------------------------------------------------------

# 4️⃣ Ingest Architecture Decision (Cost Constraint Applied)

## ❌ Rejected

-   Always-on background worker (Cloud Run instance-based)
-   Estimated cost: \~\$40--50/month

## ✅ Selected: Tick-Driven Architecture

### Design

POST /ingest\
→ insert jobs(state=queued)

Cloud Scheduler (1--2 min interval)\
→ POST /worker/tick

worker/tick:\
→ claim 1 queued job\
→ process ingest\
→ mark done/failed

### Benefits

-   Scale-to-zero
-   0.25 vCPU possible
-   Expected cost: single-digit \~\$5--10/month
-   Acceptable latency (≤ tick interval)

------------------------------------------------------------------------

# 5️⃣ Cloud Run Requirements (Final Target)

## Region

-   us-east1
-   Reason: Supabase primary DB = East US (Ohio)

## Compute (tick-driven)

-   Billing: request-based
-   CPU: 0.25 vCPU
-   Memory: 512Mi
-   Concurrency: 1
-   Execution: 1st gen
-   min-instances: 0

## Secrets

-   Firebase Admin Service Account
    -   Mounted as file
    -   GOOGLE_APPLICATION_CREDENTIALS=/secrets/firebase.json
-   OpenAI API Key
-   Supabase credentials

------------------------------------------------------------------------

# 6️⃣ Remaining Work (Next Session)

## Phase 1 --- Local E2E (Real Token)

Checklist: - Firebase project properly configured - SHA-1 registered -
Android idToken non-null - FastAPI verifies token - /documents returns
200 - users table contains single firebase_uid

## Phase 2 --- Implement tick-driven worker

-   Remove run_forever background loop
-   Add /worker/tick
-   Add claim_one_job() (FOR UPDATE SKIP LOCKED)
-   Add Cloud Scheduler config

## Phase 3 --- Deploy to Cloud Run

-   Dockerfile finalized
-   gcloud build
-   Cloud Run deploy
-   Secret Manager setup
-   Scheduler job created
-   Remote E2E test

------------------------------------------------------------------------

# 7️⃣ New Chat Kickoff Prompt

Learning Assistant MVP --- Continuing from Cloud_BE_Requirements_v1.0.

Current state: - Android Firebase Auth implemented - FastAPI verifies
real Firebase ID tokens - resolve_user_id simplified (firebase_uid
only) - Local backend running - Next goal: Local Android → FastAPI
real-token E2E validation before Cloud Run deployment.

Let's start with verifying the local E2E authentication flow
step-by-step.
