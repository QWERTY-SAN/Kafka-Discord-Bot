# Kafka Discord Bot

A modular Discord AI chatbot styled after Kafka from *Honkai: Star Rail*, powered by Google Gemini.

## Features

- `k!kafka <message>` conversation command
- `k!reset` / `k!forget` conversation reset
- `k!gif` / `k!kafkagif` sends a Kafka GIF
- `k!ping` latency check
- `k!kafkahelp` help
- Replies when Kafka is mentioned
- Replies in DMs
- Replies when a user directly replies to Kafka's message
- Per-user/per-channel conversation memory
- Memory TTL and maximum conversation cap
- Per-user/per-channel cooldown
- Concurrent Gemini request limit
- Retry handling for transient Gemini failures
- Discord 2,000-character-safe splitting
- Blocked Discord mentions in generated text
- Configurable Kafka GIF behavior
- Natural emoji guidance built into the persona
- Render-compatible health server on `$PORT`

## Environment

Copy `.env.example` to `.env` locally, then fill in your Discord and Gemini keys.

Important presentation settings:

```env
EMOJIS_ENABLED=true
KAFKA_GIF_ENABLED=true
KAFKA_GIF_MODE=every_mention
KAFKA_GIF_COOLDOWN_SECONDS=300
KAFKA_GIF_URL=https://www.gifcen.com/wp-content/uploads/2023/08/kafka-gif-6.gif
```

### GIF modes

`off` — never send a GIF automatically.

`first_reply` — send one GIF per user/channel every `KAFKA_GIF_COOLDOWN_SECONDS`.

`every_mention` — send a GIF for each qualifying mention, subject to the cooldown.

`every_command` — send a GIF after `k!kafka`, subject to the cooldown.

`every_response` — send a GIF after every AI response, subject to the cooldown.

`k!gif` always forces a GIF attempt, ignoring the automatic mode and cooldown.

The default GIF URL points to a Kafka GIF hosted by GIFcen; replace it with your preferred direct `.gif` URL if needed.

## Render

Use a **Web Service** with:

```text
Build Command: pip install -r requirements.txt
Start Command: python main.py
Health Check Path: /health
```

The health server binds to `0.0.0.0:$PORT` so Render can detect the service.


## Emoji and GIF behavior

Emoji presentation is now deterministic: when enabled, the bot adds a small Kafka-appropriate emoji to normal prose when the model did not already provide one. It deliberately avoids altering fenced code.

GIFs are downloaded from `KAFKA_GIF_URL` and uploaded to Discord as an actual `.gif` attachment. This avoids relying on Discord to render a third-party embedded URL. The bot logs the HTTP status, content type, file validity, and Discord send error when a GIF fails.
