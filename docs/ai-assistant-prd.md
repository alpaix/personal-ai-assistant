# Product Requirements Document (PRD)

## Product: BriefBox (Working Name)

AI-Native Local Email Triage and Management System

---

# 1. Product Overview

BriefBox is an **AI-native personal email management system** designed to reduce inbox overload by automatically triaging incoming email into actionable categories and presenting them through a **summary-based feed interface**.

The system processes all email **locally using a self-hosted LLM**, ensuring privacy and full user control.

Instead of a traditional inbox, users interact with a **messenger-like feed of summarized messages**, allowing rapid scanning, prioritization, and action.

---

# 2. Product Goals

### Primary Goals

1. Reduce time spent triaging email by **>80%**
2. Ensure **high signal-to-noise ratio** in the inbox
3. Enable **automatic categorization and lifecycle management**
4. Maintain **100% local processing for privacy**
5. Provide a **low-friction interaction model**

---

# 3. Target Users

### Primary

Busy professionals receiving **50–300 emails/day**

### Secondary

Privacy-conscious users who:

* distrust cloud AI assistants
* prefer local-first software

---

# 4. Core User Jobs

Users want to:

1. Quickly see **what matters today**
2. Avoid manually reading **every message**
3. Track **deliveries, trips, and events**
4. Avoid inbox clutter from **promotions and noise**
5. Retain important records **without manual filing**

---

# 5. Functional Requirements

Functional requirements are prioritized:

* **P0 — MVP critical**
* **P1 — Important**
* **P2 — Future**

---

# 5.1 Email Ingestion

## FR-1 Email Retrieval

**Priority:** P0

The system shall ingest emails from user accounts.

Capabilities:

1. Support IMAP-based email providers
2. Periodically poll inbox for new messages
3. Retrieve email metadata and body content
4. Store emails locally

---

## FR-2 Local Email Storage

**Priority:** P0

The system shall maintain a local email store.

Capabilities:

1. Persist full message content
2. Store attachments
3. Maintain metadata:

   * sender
   * timestamp
   * subject
   * message-id
4. Maintain message state:

   * unread
   * archived
   * pinned
   * deleted

---

# 5.2 Email Classification

## FR-3 Semantic Categorization

**Priority:** P0

The system shall categorize incoming emails into predefined categories.

Categories include:

1. Archive
2. Action Required
3. Track / Pinned
4. Important Updates
5. Community Updates
6. Deals
7. Newsletters
8. Noise

The classification system shall:

* combine deterministic rules
* AI-based semantic classification

---

## FR-4 Confidence Scoring

**Priority:** P1

The system shall generate a classification confidence score.

If confidence is low:

* message appears in **Action Required** category.

---

## FR-5 Rule-Based Overrides

**Priority:** P0

Users shall be able to define rules overriding AI classification.

Examples:

* always pin airline emails
* delete marketing emails from specific senders

---

# 5.3 Email Summarization

## FR-6 Message Summaries

**Priority:** P0

The system shall generate a short summary for each email.

Summary requirements:

1. Maximum 1–2 sentences
2. Capture key intent
3. Extract relevant entities where possible:

   * dates
   * deliveries
   * events
   * deadlines

---

## FR-7 Batch Summarization

**Priority:** P1

The system shall summarize groups of emails such as:

* newsletters
* community updates
* deals

---

# 5.4 Inbox Feed Interface

## FR-8 Feed-Based Inbox

**Priority:** P0

The UI shall display messages as a **scrollable feed** of summaries.

Each feed item includes:

* sender
* summary
* timestamp
* category
* quick actions

---

## FR-9 Auto-Mark Read

**Priority:** P0

Messages shall be automatically marked as read when:

* the user scrolls past them.

---

## FR-10 Quick Actions

**Priority:** P0

Users shall be able to perform quick actions:

1. archive
2. delete
3. pin
4. unsubscribe
5. mark as important
6. snooze

Actions shall be available via:

* keyboard shortcuts
* swipe gestures

---

# 5.5 Pinned Tracking System

## FR-11 Persistent Tracking

**Priority:** P0

Pinned messages shall remain visible until completion.

Examples:

* shipment delivered
* event concluded
* travel completed

---

## FR-12 Expiration Rules

**Priority:** P1

The system shall support expiration policies.

Examples:

* deals expire after X days
* newsletters auto-delete after Y days

---

# 5.6 Digest Generation

## FR-13 Daily Digest

**Priority:** P1

The system shall generate a daily summary containing:

* important updates
* pending actions
* pinned items

---

## FR-14 Weekly Digest

**Priority:** P1

The system shall generate a weekly digest summarizing:

* newsletters
* community updates
* deals

---

# 5.7 Learning System

## FR-15 Behavior-Based Learning

**Priority:** P1

The system shall learn from user behavior:

Signals include:

* deletes
* pins
* archives
* reading behavior

The model shall adapt classification rules.

---

## FR-16 Pattern Detection

**Priority:** P2

The system shall detect patterns such as:

* frequently ignored senders
* high-priority senders
* recurring event emails

---

# 5.8 Conversational Configuration

## FR-17 Chat-Based Control

**Priority:** P1

Users shall be able to configure the system via chat.

Examples:

"Always highlight hospital emails."

"Delete all marketing from Best Buy."

---

## FR-18 Natural Language Rule Creation

**Priority:** P2

The system shall convert chat commands into rule definitions.

---

# 5.9 Telegram Integration (Optional)

## FR-19 Bot Interface

**Priority:** P2

The system may provide a Telegram bot interface allowing:

* viewing summaries
* quick triage
* notification alerts

---

# 6. Non-Functional Requirements

---

# 6.1 Privacy

## NFR-1 Local Processing

**Priority:** P0

All AI processing shall occur locally.

No email content shall be transmitted to external services.

---

## NFR-2 Data Ownership

**Priority:** P0

All user data must remain under full user control.

---

# 6.2 Performance

## NFR-3 Email Processing Latency

**Priority:** P0

New email classification shall complete within:

**<5 seconds**

---

## NFR-4 Summarization Latency

**Priority:** P0

Summary generation shall complete within:

**<10 seconds**

---

# 6.3 Reliability

## NFR-5 Fault Tolerance

**Priority:** P0

Failures in AI components must not prevent email ingestion.

Fallback:

* deterministic rules.

---

## NFR-6 Idempotent Processing

**Priority:** P0

Email ingestion and classification must be idempotent.

Duplicate processing must be avoided.

---

# 6.4 Extensibility

## NFR-7 Modular Architecture

**Priority:** P0

The system shall support modular components:

* ingestion
* classification
* summarization
* UI

---

## NFR-8 Plugin Support

**Priority:** P2

Future versions may allow plugin integrations.

---

# 6.5 Security

## NFR-9 Secure Storage

**Priority:** P0

Email data must be stored encrypted at rest.

---

# 6.6 Scalability

## NFR-10 Message Capacity

**Priority:** P1

System must support:

* ≥500k stored emails

---

# 7. MVP Scope

Initial release will include:

**Core capabilities**

1. IMAP ingestion
2. Local storage
3. AI categorization
4. Message summaries
5. Feed-based UI
6. Quick triage actions
7. Pin tracking

Excluded from MVP:

* digests
* Telegram integration
* conversational configuration
* advanced learning

---

# 8. Success Metrics

### User Metrics

Inbox triage time reduction: **>80%**

Messages auto-processed: **>70%**

Pinned item completion tracking accuracy: **>90%**

---

# 9. Risks

### AI Misclassification

Mitigation:

* user overrides
* rule system

---

### Trust

Users must feel confident the system **does not lose messages**.

---

### Local Model Performance

Mitigation:

* optimized small models
* fallback rules
