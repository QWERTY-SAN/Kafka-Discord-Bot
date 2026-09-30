# Kafka Discord Bot

A modular Discord AI chatbot that roleplays as **Kafka from Honkai: Star Rail** using **Groq**.

## Features

- `k!kafka <message>` — chat with Kafka
- `k!reset` / `k!forget` — clear your conversation for the current channel
- `k!ping` — Discord latency
- `k!kafkahelp` — help
- Reply by mentioning Kafka
- DM support
- Per-user, per-channel conversation memory
- Expiring memory and a maximum conversation cache
- Per-conversation locking so simultaneous requests cannot reorder history
- Input length limiting
- Discord 2,000-character response splitting
- Groq timeout, retry, rate-limit, and API error handling
- Clean startup validation and graceful Groq client shutdown

## Setup

1. Install Python 3.10+.
2. Create a Discord bot and enable **Message Content Intent**.
3. Create a Groq API key.
4. Copy `.env.example` to `.env` and fill in the two secrets.
5. Install dependencies:

```bash
pip install -r requirements.txt
```

6. Start the bot:

```bash
python main.py
```

## Configuration

The defaults are designed for a small personal bot. The important values are:

- `GROQ_MODEL` — defaults to `openai/gpt-oss-120b`.
- `MAX_HISTORY` — number of individual chat messages retained per conversation.
- `MAX_OUTPUT_TOKENS` — output budget.
- `MAX_INPUT_CHARS` — maximum user prompt size before truncation.
- `MEMORY_TTL_SECONDS` — how long an inactive conversation stays cached.
- `MAX_CONVERSATIONS` — maximum number of cached user/channel conversations.
- `REQUEST_TIMEOUT` — Groq request timeout in seconds.
- `GROQ_MAX_RETRIES` — Groq SDK retry count.
- `REASONING_EFFORT` — `low`, `medium`, or `high` for GPT-OSS.

## Environment variables on Render

Use the same variables in Render's Environment settings. Keep `DISCORD_TOKEN` and `GROQ_API_KEY` as secrets and never commit `.env`.

A Background Worker is the natural fit for a Discord Gateway bot because the bot itself does not need an HTTP health endpoint.
