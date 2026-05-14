# 🤖 AIBot Discord — AI Discord Bot for Text and Image Generation  
[![Typing SVG](https://readme-typing-svg.herokuapp.com?font=Fira+Code&pause=1000&color=2CF7EE&width=435&lines=AIBot+Discord)](https://git.io/typing-svg)

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)  
![Discord](https://img.shields.io/badge/Discord-Bot-7289DA.svg)  
![HuggingFace](https://img.shields.io/badge/Hugging%20Face-API-yellow)

> A modern Discord bot powered by HuggingFace models for AI-generated images and text responses. Supports both slash commands and legacy prefix commands.

---

## 📹 Video Demo

Watch the bot in action:

<video width="800" controls poster="video/poster.png">
  <source src="video/Discordbot.mp4" type="video/mp4">
  Your browser does not support the video tag. <a href="video/Discordbot.mp4">Download the video</a>.
</video>

*Video demonstration: generating images and text responses directly in Discord*

---

## ✨ Features

- **🎨 Multiple Image Models** (via HuggingFace Inference API):
  - `SDXL Emoji` — Emoji-style images (`fofr/sdxl-emoji` via fal-ai)
  - `SDXL Turbo` — Fast image generation (`stabilityai/sdxl-turbo` via replicate)
  - `HiDream Realism` — Ultra-realistic images (`Flux-Super-Realism-LoRA` via fal-ai)

- **💬 Text Generation** (via HuggingFace Router + OpenAI-compatible API):
  - Uses `Mistral-7B-Instruct` model for intelligent responses

- **🔒 Secure Configuration**:
  - Environment-based token management (`.env`)
  - No hardcoded secrets

- **⚡ Modern Architecture**:
  - Async/await throughout (non-blocking)
  - Slash commands (`/generate`, `/ask`, `/help`)
  - Legacy prefix commands still supported (`!SDXL_generate`, `!text`, etc.)
  - Structured logging
  - Proper error handling

---

## 🧠 Commands

### Slash Commands (Recommended)

| Command | Description | Parameters |
|---------|-------------|------------|
| `/generate` | Generate an AI image | `prompt` (str), `model` (sdxl/pony/hidream) |
| `/ask` | Ask AI a question | `question` (str) |
| `/help` | Show help message | — |

### Legacy Prefix Commands

| Command | Description |
|---------|-------------|
| `!SDXL_generate <prompt>` | Generate emoji-style image |
| `!pony_generate <prompt>` | Generate SDXL turbo image |
| `!HiDream_generate <prompt>` | Generate hyper-realistic image |
| `!text <prompt>` | Generate text response |

---

## 🛠️ Installation

### Prerequisites

- Python 3.10 or higher
- Discord Bot Token ([Create here](https://discord.com/developers/applications))
- HuggingFace Token with Inference API access ([Get here](https://huggingface.co/settings/tokens))

### Setup Steps

1. **Clone the repository:**

```bash
git clone https://github.com/AlihanSDev/discord-bot-ai.git
cd discord-bot-ai
```

2. **Create virtual environment (recommended):**

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\Activate.ps1
# Linux/macOS
source .venv/bin/activate
```

3. **Install dependencies:**

```bash
pip install -r requirements.txt
```

4. **Configure environment variables:**

```bash
# Copy example and edit
cp .env.example .env
```

Edit `.env` with your tokens:

```env
DISCORD_TOKEN=your_discord_bot_token_here
HF_TOKEN=your_huggingface_token_here
```

5. **Invite bot to your Discord server:**

In Discord Developer Portal:
- Enable **Message Content Intent** (required for prefix commands)
- Enable **Server Members Intent** (optional)
- Generate OAuth2 URL with:
  - Scopes: `bot`
  - Bot Permissions: `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History`

6. **Run the bot:**

```bash
python main.py
```

---

## 📁 Project Structure

```
discord-bot-ai/
├── main.py              # Bot entry point, commands, handlers
├── requirements.txt      # Python dependencies
├── .env                 # Environment variables (not committed)
├── .env.example         # Example env file
├── .gitignore           # Git ignore rules
├── README.md            # Documentation
└── .git/               # Git repository
```

---

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DISCORD_TOKEN` | Discord bot token from Developer Portal | Yes |
| `HF_TOKEN` | HuggingFace API token with inference access | Yes |

### Available Image Models

| Key | Provider | Model ID | Use Case |
|-----|----------|----------|----------|
| `sdxl` | fal-ai | `fofr/sdxl-emoji` | Emoji-style art |
| `pony` | replicate | `stabilityai/sdxl-turbo` | Fast generation |
| `hidream` | fal-ai | `strangerzonehf/Flux-Super-Realism-LoRA` | Realistic photos |

---

## 🚨 Error Handling

The bot includes comprehensive error handling:

- **API Errors**: Logged to console with stack trace; user sees friendly error message
- **Invalid Models**: Clear error indicating available options
- **Missing Arguments**: Bot prompts for required parameters
- **Rate Limits**: HuggingFace provider rate limits apply (free tier has quotas)

---

## 📝 Logging

All operations are logged with Python's `logging` module:

```
2026-05-12 23:30:15 - INFO - ✅ Bot logged in as AIBot#1234 (ID: 123456789)
2026-05-12 23:30:20 - INFO - Synced 3 slash commands
```

Adjust log level in `main.py` (line 23) from `INFO` to `DEBUG` for verbose output.

---

## ⚠️ Known Limitations

1. **Rate Limits**: Free HuggingFace tokens have rate limits (~10k inferences/month). Monitor usage at https://huggingface.co/settings/billing
2. **Image Generation Time**: 3-10 seconds depending on model and load
3. **Memory Usage**: Large models may cause OOM on free tier
4. **No Database**: All requests are stateless; no history or caching
5. **No Cooldowns**: Currently no per-user rate limiting (may be added)

---

## 🛠️ Development

### Adding New Models

Edit `IMAGE_MODELS` dict in `main.py`:

```python
IMAGE_MODELS = {
    "new_model": {
        "provider": "fal-ai",  # or "replicate", "together-ai", etc.
        "model": "organization/model-id",
        "description": "Human readable name"
    }
}
```

The model automatically appears in `/generate` command choices.

### Running Locally with Debug

```bash
# Set debug log level
$env:LOG_LEVEL="DEBUG"; python main.py
```

---

## 📄 License

MIT License — feel free to modify and deploy.

---

## 🙏 Credits

- [discord.py](https://github.com/Rapptz/discord.py) — Discord API wrapper
- [huggingface_hub](https://github.com/huggingface/huggingface_hub) — Inference client
- [OpenAI Python SDK](https://github.com/openai/openai-python) — Used for HF router compatibility

---

## 🔗 Resources

- [Discord.py Documentation](https://discordpy.readthedocs.io/)
- [HuggingFace Inference API](https://huggingface.co/inference-api)
- [HuggingFace Router Docs](https://huggingface.co/docs/huggingface_hub/guides/inference#openai-compatible-endpoint)
- [Discord Bot Developer Portal](https://discord.com/developers/applications)
