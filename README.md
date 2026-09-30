# Kafka Discord AI Bot

A modular Discord AI chatbot inspired by Kafka from *Honkai: Star Rail*, powered by Groq.

## Features

- `k!kafka <message>` command
- Mention the bot to talk to Kafka
- DM support
- Per-user, per-channel conversation memory
- Automatic memory expiration
- Conversation limit to prevent unbounded RAM use
- Per-conversation locking to prevent history races
- User/channel cooldown
- Input length protection
- Discord 2,000-character response splitting
- Groq retries for transient failures
- Configurable GPT-OSS reasoning effort
- Hidden reasoning output
- Clean shutdown and structured logging

## Recommended model

`openai/gpt-oss-120b`

Recommended reasoning setting for normal Discord conversation:

```env
REASONING_EFFORT=medium
```

## Setup

1. Install Python 3.10+.
2. Run `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`.
4. Add `DISCORD_TOKEN` and `GROQ_API_KEY`.
5. Enable the Discord **Message Content Intent** in the Discord Developer Portal.
6. Run `python main.py`.

Never commit `.env` or API keys to GitHub.
