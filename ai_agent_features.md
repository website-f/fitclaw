# AI Agent for Business — Feature Specification

## Project Overview

A business-focused AI agent that helps SMEs automate workflows, answer queries from internal knowledge, and take real actions across business tools. Built with a Malaysian market focus.

---

## 1. Core Capabilities

### 1.1 Natural Language Understanding
- Multi-intent parsing — handle complex, multi-part requests in a single prompt
- Context retention within a session (short-term memory)
- Optional long-term memory across sessions (user preferences, past tasks)
- Support for Bahasa Malaysia and English (bilingual)
- Industry-specific vocabulary handling per business type

### 1.2 Tool Use / Actions
- Web search and real-time data retrieval
- CRM read/write — contacts, deals, tasks, pipeline stages
- Email actions — send, reply, summarize, draft
- Calendar — create events, check availability, schedule follow-ups
- Document generation — proposals, invoices, reports
- Database querying via natural language (SQL or NoSQL)

### 1.3 Workflow Automation
- Multi-step task chaining (e.g. "find leads → draft email → schedule follow-up")
- Conditional logic (e.g. "if deal value > RM10,000, escalate to manager")
- Trigger-based actions (on form submission, on email received, on schedule)
- Integration with n8n or Make.com via webhook

---

## 2. Business-Specific Features

### 2.1 Knowledge Base (RAG — Retrieval-Augmented Generation)
- Upload company SOPs, FAQs, product catalogues, pricing sheets
- Agent queries internal knowledge first before web search
- Responses include cited source (document name + page/section)
- Supports PDF, DOCX, TXT, and CSV uploads
- Re-indexing on document update

### 2.2 Role-Based Access Control
- Different agent scopes per department (Sales, HR, Finance, Ops)
- User permission tiers — what data each role can read or modify
- Admin panel to configure agent behavior per role
- API key or SSO-based authentication

### 2.3 Human Handoff
- Agent detects low-confidence or sensitive topics → escalates to human
- Full conversation transcript passed along so context is not lost
- Configurable escalation rules (by topic, keyword, or sentiment)
- Notification to assigned staff via WhatsApp or email

---

## 3. Operational & Admin Features

### 3.1 Analytics Dashboard
- Most common queries and topics
- Fallback/failure rate and escalation rate
- Response quality scores (based on user feedback)
- Usage breakdown per user, role, and department
- Token usage and cost tracking

### 3.2 Feedback Loop
- Thumbs up/down on every agent response
- Correction mode — admins can flag wrong answers and provide correct ones
- Flagged responses feed into fine-tuning or prompt improvement pipeline
- Weekly summary report of feedback trends

### 3.3 Audit Logs
- Every agent action is logged (query, action taken, data changed, timestamp, user)
- Immutable log storage for compliance (especially finance and legal use cases)
- Exportable logs in CSV or JSON
- Configurable log retention period

### 3.4 Cost Controls
- Token usage tracking per user and team
- Monthly budget cap with alert at threshold (e.g. 80% of limit)
- Rate limiting per user to prevent abuse
- Model selection per use case (cheaper model for simple tasks, smarter model for complex ones)

---

## 4. UX & Interface

### 4.1 Omnichannel Access
- Web chat widget (embeddable on any site)
- WhatsApp Business API integration
- Telegram bot
- Slack and Microsoft Teams integration
- Email-based interface (reply to a dedicated inbox)

### 4.2 Memory
- Short-term: full context retention within a conversation
- Long-term: remembers user preferences, recurring tasks, past project context
- Memory can be viewed and cleared by the user

### 4.3 Proactive Suggestions
- Agent surfaces insights unprompted based on patterns
- Examples:
  - "You have 5 uncontacted leads this week"
  - "Invoice #1042 is overdue by 7 days"
  - "3 support tickets haven't been replied to in 48 hours"
- Configurable frequency and delivery channel (WhatsApp, email, dashboard)

---

## 5. Malaysian Market Differentiators

| Feature | Rationale |
|---|---|
| Bahasa Malaysia + English bilingual support | Most Malaysian SMEs communicate in both |
| WhatsApp Business API as primary channel | Dominant communication tool for local businesses |
| SSM document awareness | Parse and understand Malaysian business registration documents |
| Invoice and receipt parsing (local formats) | Support for Malaysian invoice formats, GST/SST fields |
| n8n webhook integration | Fast automation setup without custom dev work |
| Offline FAQ caching | Fast, cheap responses for common queries with no API call needed |
| Ringgit-aware financial logic | Currency formatting, budget thresholds in MYR |

---

## 6. MVP Scope (Suggested Starting Point)

Focus on these for v1:

1. **Web chat interface** with session memory
2. **Knowledge base (RAG)** — upload docs, agent answers from them with citations
3. **WhatsApp integration** via Twilio or official WhatsApp Business API
4. **n8n webhook** as the automation trigger/action layer
5. **Basic analytics** — query volume, fallback rate, feedback score
6. **Role-based access** — at minimum admin vs. staff distinction
7. **Audit log** — every query and action recorded

---

## 7. Tech Stack Suggestions

| Layer | Options |
|---|---|
| LLM | Claude API (Sonnet for complex, Haiku for simple) |
| RAG / Vector DB | Supabase pgvector, Pinecone, or Qdrant |
| Backend | Node.js + Express or Python FastAPI |
| Frontend | Next.js or plain React |
| Automation | n8n (self-hosted on VPS) |
| WhatsApp | Twilio WhatsApp API or official Meta Cloud API |
| Auth | Supabase Auth or Clerk |
| Hosting | DigitalOcean App Platform or VPS |
| Logs | Supabase or a dedicated logging service (Logtail, Papertrail) |

---

## 8. Open Questions to Decide Before Building

- Which industry/vertical to target first? (e.g. F&B, retail, property, logistics)
- SaaS model (subscription) or white-label for agencies?
- Self-hosted or fully managed cloud?
- Will you offer onboarding services or fully self-serve?
- Data residency requirements — any clients needing Malaysia-hosted data?

---

*Last updated: June 2026*
