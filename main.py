from discord import Intents, File
from discord.ext import commands
from dotenv import load_dotenv
import os
import io
import random
from PIL import Image
from huggingface_hub import InferenceClient

load_dotenv()

intents = Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    description="Just Run!",
    intents=intents,
)

HUGGINGFACE_TOKEN = os.environ["HUGGINGFACE_TOKEN"]

MODELS = {
    "SDXL": {
        "provider": "fal-ai",
        "model": "fofr/sdxl-emoji"
    },
    "pony": {
        "provider": "replicate",
        "model": "stabilityai/sdxl-turbo"
    },
    "HiDream": {
        "provider": "fal-ai",
        "model": "strangerzonehf/Flux-Super-Realism-LoRA"
    }
}

TEXT_MODEL = {
    "model": "meta-llama/Llama-3.1-8B-Instruct",
    "token": HUGGINGFACE_TOKEN
}

# Function for generating text
async def generate_text(ctx, prompt):
    try:
        msg = await ctx.send(f"“{prompt}” 𝐏𝐫𝐨𝐜𝐞𝐬𝐬𝐢𝐧𝐠 𝐲𝐨𝐮𝐫 𝐫𝐞𝐪𝐮𝐞𝐬𝐭... 📝")
        client = InferenceClient(TEXT_MODEL["token"])
        response = client.text(
            model=TEXT_MODEL["model"],
            inputs=prompt,
            max_length=500,
            temperature=0.7
        )
        await msg.edit(content=f"“{prompt}”\n\n**Response:**\n{response}")
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")

@bot.command()
async def SDXL_generate(ctx, *, prompt):
    await generate_image(ctx, "SDXL", prompt)

@bot.command()
async def pony_generate(ctx, *, prompt):
    await generate_image(ctx, "pony", prompt)

@bot.command()
async def HiDream_generate(ctx, *, prompt):
    await generate_image(ctx, "HiDream", prompt)

@bot.command()
async def text(ctx, *, prompt):
    await generate_text(ctx, prompt)

def generate_image_bytes(model_key, prompt, seed):
    model_info = MODELS[model_key]

    client = InferenceClient(
        provider=model_info["provider"],
        api_key=HUGGINGFACE_TOKEN
    )

    # Image generation
    image = client.text_to_image(
        prompt,
        model=model_info["model"],
        seed=seed
    )

    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()

def generate_random_with_seed(seed, model_key, prompt):
    if seed is None:
        seed = random.randint(0, 100)
    random.seed(seed)
    image_bytes = generate_image_bytes(model_key, prompt, seed)
    return image_bytes

async def generate_image(ctx, model_key, prompt):
    try:
        msg = await ctx.send(f"“{prompt}” 𝐖𝐨𝐰 𝐜𝐨𝐨𝐥 𝐝𝐮𝐝𝐞! 😻 \n> 🤖 𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐢𝐧𝐠...")
        image_bytes = generate_random_with_seed(seed=None, model_key=model_key, prompt=prompt)
        image = Image.open(io.BytesIO(image_bytes))
        image.save("generated_image.png")
        with open("generated_image.png", "rb") as f:
            await ctx.send(file=File(f))
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")

bot.run(os.environ["DISCORD_TOKEN"])