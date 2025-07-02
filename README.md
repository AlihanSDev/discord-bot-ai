# 🤖 AIBot Discord — AI Discord Bot for Text and Image Generation  
[![Typing SVG](https://readme-typing-svg.herokuapp.com?font=Fira+Code&pause=1000&color=27F7D9&center=true&vCenter=true&width=435&lines=AIBot+Discord)](https://git.io/typing-svg)

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)  
![Discord](https://img.shields.io/badge/Discord-Bot-7289DA.svg)  
![HuggingFace](https://img.shields.io/badge/Hugging%20Face-Model%20API-yellow)

> A Discord bot powered by **Hugging Face models** for AI-generated **images** and **text** responses. Just prompt and run!

---

## 🚀 Features

- 🎨 Generate images using different model styles:
  - `!SDXL_generate` — Emoji-style images (via [fofr/sdxl-emoji](https://huggingface.co/fofr/sdxl-emoji))

- ✨ Text generation:
  - `!text` — Generates intelligent responses using [Llama 3.1 8B Instruct](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct)

- 🔒 Environment token-based security using `.env`

---

## 🧠 Commands Overview

| Command                     | Description                          |
|-----------------------------|--------------------------------------|
| `!SDXL_generate <prompt>`   | Generate an emoji-style image        |
| `!pony_generate <prompt>`   | Generate a turbo SDXL image          |
| `!HiDream_generate <prompt>`| Generate a super realistic image     |
| `!text <prompt>`            | Generate intelligent AI text         |

---

## 🛠️ Installation

1. **Clone the repo**:

```bash
git clone https://github.com/AlihanSDev/discord-bot-ai.git  
cd discord-bot-ai
