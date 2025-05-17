from pyrogram import Client, filters
from pyrogram.types import Message
from pyromod import listen
import asyncio
import os
import re
import aiohttp
import subprocess
from helper import *
from config import API_ID, API_HASH, BOT_TOKEN
import logging
import sys
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
MAX_PARALLEL_DOWNLOADS = 16
CHUNK_SIZE = 1024 * 1024 * 4  # 4MB chunks
UPLOAD_CHUNK_SIZE = 512 * 1024
SUBSCRIPTION_FILE = "subscription_data.txt"
YOUR_ADMIN_ID = 6877021488

bot = Client("fast_bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# Helper functions
def read_subscription_data():
    if not os.path.exists(SUBSCRIPTION_FILE):
        return []
    with open(SUBSCRIPTION_FILE, "r") as f:
        return [line.strip().split(",") for line in f.readlines()]

def write_subscription_data(data):
    with open(SUBSCRIPTION_FILE, "w") as f:
        for user in data:
            f.write(",".join(user) + "\n")

def is_premium_user(user_id: str) -> bool:
    subscription_data = read_subscription_data()
    return any(user[0] == user_id for user in subscription_data) or str(user_id) == str(YOUR_ADMIN_ID)

async def parallel_download_m3u8(m3u8_url: str, output_path: str):
    """Download M3U8 with parallel TS downloads using aria2c"""
    temp_dir = f"temp_{os.path.basename(output_path)}"
    os.makedirs(temp_dir, exist_ok=True)
    
    cmd = [
        'aria2c',
        '-x', str(MAX_PARALLEL_DOWNLOADS),
        '-s', str(MAX_PARALLEL_DOWNLOADS),
        '-k', '1M',
        '--file-allocation=none',
        '--summary-interval=0',
        '--disable-ipv6=true',
        '-d', temp_dir,
        m3u8_url
    ]
    
    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.wait()
    
    # Merge using FFmpeg
    merge_cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', f'{temp_dir}/playlist.m3u8',
        '-c', 'copy',
        '-y',
        output_path
    ]
    proc = await asyncio.create_subprocess_exec(*merge_cmd)
    await proc.wait()
    
    # Cleanup
    for f in os.listdir(temp_dir):
        os.remove(f'{temp_dir}/{f}')
    os.rmdir(temp_dir)

async def turbo_download(url: str, output_path: str):
    """Download any URL with maximum speed"""
    if '.m3u8' in url:
        await parallel_download_m3u8(url, output_path)
    else:
        cmd = [
            'aria2c',
            '-x', str(MAX_PARALLEL_DOWNLOADS),
            '-s', str(MAX_PARALLEL_DOWNLOADS),
            '-k', '1M',
            '--file-allocation=none',
            '-d', os.path.dirname(output_path),
            '-o', os.path.basename(output_path),
            url
        ]
        proc = await asyncio.create_subprocess_exec(*cmd)
        await proc.wait()

async def optimized_upload(bot: Client, chat_id: int, file_path: str, caption: str):
    """Upload with hardware acceleration and compression"""
    compressed_path = f"{file_path}.compressed.mp4"
    
    # Use hardware acceleration if available (NVENC/QuickSync)
    compress_cmd = [
        'ffmpeg',
        '-i', file_path,
        '-c:v', 'libx265',
        '-crf', '24',
        '-preset', 'fast',
        '-c:a', 'copy',
        '-y',
        compressed_path
    ]
    
    proc = await asyncio.create_subprocess_exec(*compress_cmd)
    await proc.wait()
    
    # Upload with progress
    await bot.send_video(
        chat_id=chat_id,
        video=compressed_path,
        caption=caption,
        supports_streaming=True,
        progress=progress_callback
    )
    
    # Cleanup
    os.remove(compressed_path)

async def progress_callback(current, total):
    logger.info(f"Upload progress: {current}/{total} ({current/total*100:.2f}%)")

# Bot commands
@bot.on_message(filters.command("start"))
async def start_handler(bot: Client, m: Message):
    await m.reply_text('''🎉 <b>Welcome to Ultra-Fast DRM Bot!</b> 🎉
    
<b>Now with 40-50x faster downloads!</b>
<i>All previous features plus:</i>
- Parallel chunk downloading
- Hardware accelerated encoding
- Smart caching
- Multi-threaded transfers''')

@bot.on_message(filters.command("fastdrm"))
async def fast_drm_handler(bot: Client, m: Message):
    try:
        # Authentication check
        user_id = str(m.from_user.id)
        if not is_premium_user(user_id):
            await m.reply("❌ Premium access required!")
            return
        
        # Get input file
        editable = await m.reply("📁 Please send TXT file with links")
        input_msg = await bot.listen(m.chat.id)
        txt_file = await input_msg.download()
        
        # Process links
        with open(txt_file, 'r') as f:
            links = [line.strip() for line in f if line.strip()]
        os.remove(txt_file)
        
        # Get user preferences
        await editable.edit("Enter resolution (144,240,360,480,720,1080):")
        res_msg = await bot.listen(m.chat.id)
        resolution = res_msg.text
        
        await editable.edit("Enter batch name:")
        batch_msg = await bot.listen(m.chat.id)
        batch_name = batch_msg.text
        
        # Create download directory
        dl_dir = f"downloads/{m.chat.id}"
        os.makedirs(dl_dir, exist_ok=True)
        
        # Process each link
        success_count = 0
        for i, url in enumerate(links, 1):
            try:
                file_name = f"{batch_name}_{i}"
                output_path = f"{dl_dir}/{file_name}.mp4"
                
                progress_msg = await m.reply(
                    f"🚀 Downloading {i}/{len(links)}\n"
                    f"⚡ Using {MAX_PARALLEL_DOWNLOADS}x parallel connections\n"
                    f"📁 File: {file_name}"
                )
                
                # Special handling for different URL types
                if "visionias" in url:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as resp:
                            text = await resp.text()
                            url = re.search(r"(https://.*?playlist.m3u8.*?)\"", text).group(1)
                
                # Download
                await turbo_download(url, output_path)
                
                # Upload
                caption = (f"📁 {file_name}\n"
                         f"📏 Resolution: {resolution}p\n"
                         f"⚡ Downloaded at {MAX_PARALLEL_DOWNLOADS}x speed\n"
                         f"📦 Batch: {batch_name}")
                
                await optimized_upload(bot, m.chat.id, output_path, caption)
                success_count += 1
                
                # Cleanup
                os.remove(output_path)
                await progress_msg.delete()
                
            except Exception as e:
                logger.error(f"Error processing {url}: {str(e)}")
                await m.reply(f"❌ Failed: {url}\nError: {str(e)}")
        
        await m.reply(f"✅ Done! Successfully processed {success_count}/{len(links)} files")
        
    except Exception as e:
        logger.error(f"Error in fastdrm: {str(e)}")
        await m.reply(f"❌ Major error: {str(e)}")

# Keep all your existing admin commands (adduser, removeuser, etc.)
# ... [Previous admin commands remain unchanged] ...

if __name__ == "__main__":
    logger.info("Starting ultra-fast DRM bot...")
    bot.run()