import os
import io
import random
import logging
from typing import Optional

import discord

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from PIL import Image
from huggingface_hub import AsyncInferenceClient
from openai import OpenAI

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Validate environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is required")
if not HF_TOKEN:
    raise ValueError("HF_TOKEN environment variable is required")

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    description="AI-powered Discord bot for text and image generation",
    intents=intents,
    help_command=None
)

# Model configurations
IMAGE_MODELS = {
    "sdxl": {
        "provider": "fal-ai",
        "model": "fofr/sdxl-emoji",
        "description": "Emoji-style images"
    },
    "pony": {
        "provider": "replicate",
        "model": "stabilityai/sdxl-turbo",
        "description": "Fast SDXL turbo images"
    },
    "hidream": {
        "provider": "fal-ai",
        "model": "strangerzonehf/Flux-Super-Realism-LoRA",
        "description": "Super realistic images"
    }
}

TEXT_MODEL = "mistralai/Mistral-7B-Instruct-v0.2:featherless-ai"


def get_hf_text_client() -> OpenAI:
    """Create OpenAI client configured for HuggingFace router."""
    return OpenAI(
        base_url="https://router.huggingface.co/v1",
        api_key=HF_TOKEN,
    )


async def generate_text_response(prompt: str) -> str:
    """
    Generate text response using HuggingFace via OpenAI-compatible API.

    Args:
        prompt: User's text prompt

    Returns:
        Generated text response

    Raises:
        Exception: If API call fails
    """
    try:
        client = get_hf_text_client()
        completion = client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=500,
            temperature=0.7,
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Text generation failed: {e}", exc_info=True)
        raise


def get_hf_image_client(provider: str) -> AsyncInferenceClient:
    """
    Create async HuggingFace inference client for image generation.

    Args:
        provider: Provider name (e.g., 'fal-ai', 'replicate')

    Returns:
        AsyncInferenceClient instance
    """
    return AsyncInferenceClient(
        provider=provider,
        api_key=HF_TOKEN,
    )


async def generate_image_bytes(
    model_key: str,
    prompt: str,
    seed: Optional[int] = None
) -> bytes:
    """
    Generate image bytes asynchronously.

    Args:
        model_key: Key from IMAGE_MODELS dict
        prompt: Text prompt for image generation
        seed: Optional random seed for reproducibility

    Returns:
        Raw PNG image bytes

    Raises:
        ValueError: If model_key is invalid
        Exception: If image generation fails
    """
    if model_key not in IMAGE_MODELS:
        raise ValueError(f"Unknown model: {model_key}. Available: {list(IMAGE_MODELS.keys())}")

    model_info = IMAGE_MODELS[model_key]

    # Use isolated RNG if seed provided
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    try:
        client = get_hf_image_client(model_info["provider"])
        image = await client.text_to_image(
            prompt=prompt,
            model=model_info["model"],
            seed=seed,
        )

        # Convert PIL Image to bytes in memory
        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        return img_bytes.getvalue()

    except Exception as e:
        logger.error(
            f"Image generation failed for model={model_key}, "
            f"prompt={prompt[:50]}, seed={seed}: {e}",
            exc_info=True
        )
        raise


@bot.event
async def on_ready():
    """Bot startup event."""
    logger.info(f"✅ Bot logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash commands")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    """Handle prefix command errors."""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Unknown command. Use `/help` for available commands.")
    else:
        logger.error(f"Command error in {ctx.command}: {error}", exc_info=True)
        await ctx.send(f"❌ Command failed: {str(error)}")


@bot.tree.command(name="generate", description="Generate an AI image")
@app_commands.describe(
    prompt="Description of the image you want to generate",
    model="Image generation model to use"
)
@app_commands.choices(model=[
    app_commands.Choice(name="SDXL Emoji", value="sdxl"),
    app_commands.Choice(name="SDXL Turbo (Pony)", value="pony"),
    app_commands.Choice(name="HiDream Realism", value="hidream"),
])
async def generate_slash(
    interaction: discord.Interaction,
    prompt: str,
    model: str = "sdxl"
):
    """
    Slash command for image generation.

    Args:
        interaction: Discord interaction
        prompt: Image prompt
        model: Model key from IMAGE_MODELS
    """
    await interaction.response.defer(thinking=True)

    try:
        model_info = IMAGE_MODELS.get(model, IMAGE_MODELS["sdxl"])
        image_bytes = await generate_image_bytes(model, prompt)

        # Create Discord file from bytes
        file = discord.File(
            io.BytesIO(image_bytes),
            filename=f"generated_{model}.png"
        )

        embed = discord.Embed(
            title="🎨 Image Generated",
            description=f"**Model:** {model_info['description']}\n**Prompt:** {prompt}",
            color=discord.Color.blue()
        )
        embed.set_image(url=f"attachment://generated_{model}.png")
        embed.set_footer(text=f"Powered by {model_info['provider']} | {model_info['model']}")

        await interaction.followup.send(file=file, embed=embed)

    except Exception as e:
        logger.error(f"Slash command generate failed: {e}", exc_info=True)
        await interaction.followup.send(
            f"❌ Failed to generate image: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="ask", description="Ask AI a question (text generation)")
@app_commands.describe(question="Your question or prompt")
async def ask_slash(interaction: discord.Interaction, question: str):
    """
    Slash command for text generation.

    Args:
        interaction: Discord interaction
        question: User's text prompt
    """
    await interaction.response.defer(thinking=True)

    try:
        response = await generate_text_response(question)

        # Truncate if too long for Discord
        if len(response) > 1900:
            response = response[:1900] + "..."

        embed = discord.Embed(
            title="💬 AI Response",
            description=response,
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Model: {TEXT_MODEL}")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        logger.error(f"Slash command ask failed: {e}", exc_info=True)
        await interaction.followup.send(
            f"❌ Failed to generate response: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="help", description="Show available commands")
async def help_slash(interaction: discord.Interaction):
    """Display help information."""
    embed = discord.Embed(
        title="🤖 AI Bot Commands",
        description="AI-powered text and image generation using HuggingFace",
        color=discord.Color.purple()
    )

    embed.add_field(
        name="🎨 /generate",
        value="Generate an AI image\n"
              "• `prompt`: Image description\n"
              "• `model`: sdxl, pony, hidream",
        inline=False
    )
    embed.add_field(
        name="💬 /ask",
        value="Ask AI a question\n• `question`: Your prompt",
        inline=False
    )
    embed.add_field(
        name="❓ /help",
        value="Show this help message",
        inline=False
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


# Legacy prefix commands (kept for backwards compatibility)
@bot.command(name="SDXL_generate")
async def SDXL_generate_prefix(ctx: commands.Context, *, prompt: str):
    """Legacy prefix command for SDXL image generation."""
    await generate_image(ctx, "sdxl", prompt)


@bot.command(name="pony_generate")
async def pony_generate_prefix(ctx: commands.Context, *, prompt: str):
    """Legacy prefix command for Pony image generation."""
    await generate_image(ctx, "pony", prompt)


@bot.command(name="HiDream_generate")
async def HiDream_generate_prefix(ctx: commands.Context, *, prompt: str):
    """Legacy prefix command for HiDream image generation."""
    await generate_image(ctx, "hidream", prompt)


@bot.command(name="text")
async def text_prefix(ctx: commands.Context, *, prompt: str):
    """Legacy prefix command for text generation."""
    await generate_text(ctx, prompt)


async def generate_image(
    ctx: commands.Context,
    model_key: str,
    prompt: str
):
    """
    Legacy image generation handler for prefix commands.

    Args:
        ctx: Command context
        model_key: Model identifier
        prompt: Image prompt
    """
    try:
        msg = await ctx.send(
            f"🎨 Generating **{model_key}** image...\n"
            f"**Prompt:** {prompt}"
        )

        image_bytes = await generate_image_bytes(model_key, prompt)

        file = discord.File(
            io.BytesIO(image_bytes),
            filename=f"generated_{model_key}.png"
        )

        embed = discord.Embed(
            title="Image Generated",
            description=f"**Model:** {model_key}\n**Prompt:** {prompt}",
            color=discord.Color.blue()
        )
        embed.set_image(url=f"attachment://generated_{model_key}.png")

        await msg.edit(content=None, embed=embed, attachments=[file])

    except Exception as e:
        logger.error(f"Prefix image generation failed: {e}", exc_info=True)
        await ctx.send(f"❌ Error: {str(e)}")


async def generate_text(ctx: commands.Context, prompt: str):
    """
    Legacy text generation handler for prefix commands.

    Args:
        ctx: Command context
        prompt: User's text prompt
    """
    try:
        msg = await ctx.send(f"📝 Generating response for: {prompt}")

        response = await generate_text_response(prompt)

        if len(response) > 1900:
            response = response[:1900] + "..."

        embed = discord.Embed(
            title="AI Response",
            description=response,
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Model: {TEXT_MODEL}")

        await msg.edit(content=None, embed=embed)

    except Exception as e:
        logger.error(f"Prefix text generation failed: {e}", exc_info=True)
        await ctx.send(f"❌ Error: {str(e)}")


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.critical("DISCORD_TOKEN not set in environment")
        exit(1)

    try:
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested")
    except Exception as e:
        logger.critical(f"Bot crashed: {e}", exc_info=True)
        raise
