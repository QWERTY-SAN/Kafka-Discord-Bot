# Kafka Discord Bot

A modular Discord AI chatbot based on Kafka from *Honkai: Star Rail*, using Gemini and `gemini-3.5-flash-lite`.

## Features

- `k!kafka <message>` conversation command
- `k!reset` / `k!forget` conversation reset
- `k!ping` latency check
- `k!kafkahelp` help command
- Responds to mentions
- Responds in DMs/group DMs
- Responds when a user replies directly to a Kafka message
- Per-user, per-channel conversation memory
- Memory TTL and conversation cap
- Per-user/per-channel cooldown
- Concurrent-request limit
- Input-length protection
- Discord-safe output splitting
- Generated mentions disabled to prevent accidental pings
- Gemini reasoning set to `medium` by default
- Gemini retry/timeout configuration
- Structured logging

## Setup

1. Install Python 3.10+.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN` and `GEMINI_API_KEY`.
4. Enable **Message Content Intent** for the Discord bot in the Developer Portal.
5. Start:

```bash
python main.py
```

## Environment variables

See `.env.example`. The important defaults are:

```env
GEMINI_MODEL=gemini-3.5-flash-lite
MAX_OUTPUT_TOKENS=1536
THINKING_LEVEL=medium
```

Never commit `.env` or API keys to GitHub.
