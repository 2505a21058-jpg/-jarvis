# Jarvis Remote Bridge

Control Jarvis from your phone or any network client.

## Telegram Setup
1. Create bot at https://t.me/BotFather -> get token
2. Set env vars:
   export TELEGRAM_BOT_TOKEN=your_bot_token
   export JARVIS_BRIDGE_TOKEN=your_secret_pin
   export JARVIS_REMOTE_BRIDGE=true
3. Run Jarvis: python jarvis.py
4. Message your bot: /auth your_secret_pin

## WebSocket Setup
Connect to ws://localhost:8765
Send: {"chat_id": 1, "message": "/auth your_pin"}
Then: {"chat_id": 1, "message": "open chrome"}
Receive: {"status": "ok", "response": "Opened chrome"}

## Security
- NEVER expose port 8765 to the public internet
- Use Tailscale for secure remote access
- JARVIS_BRIDGE_TOKEN must be set - without it all connections are rejected
- High-risk skills require /approve confirmation
