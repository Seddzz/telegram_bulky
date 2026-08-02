import os
import asyncio
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# Replace this with your token from @BotFather
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TEMP_DIR = "temp_downloads"

os.makedirs(TEMP_DIR, exist_ok=True)

async def start(update: Update, context):
    await update.message.reply_text(
        "⚡ Send me a TikTok or Instagram profile link! I will download and send the latest videos one by one."
    )

def download_video_sync(video_url: str, output_path: str):
    """Synchronous download function using direct pre-merged MP4 streams."""
    ydl_opts = {
        'outtmpl': output_path,
        # Force single stream mp4 so yt-dlp doesn't freeze looking for ffmpeg
        'format': 'b[ext=mp4]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

async def handle_url(update: Update, context):
    url = update.message.text.strip()

    if not ("instagram.com" in url or "tiktok.com" in url):
        await update.message.reply_text("Please send a valid Instagram or TikTok profile URL.")
        return

    status = await update.message.reply_text("🔎 Extracting profile media list...")

    extract_opts = {
        'extract_flat': True,
        'quiet': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }

    loop = asyncio.get_running_loop()

    def _extract():
        with yt_dlp.YoutubeDL(extract_opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        # Extract video entries
        info = await loop.run_in_executor(None, _extract)
        if not info:
            await status.edit_text("❌ Could not read profile.")
            return

        entries = info.get('entries', [info])
        if not entries:
            await status.edit_text("❌ No videos found.")
            return

        # Cap queue to the 15 most recent videos for speed and stability
        MAX_VIDEOS = 15
        entries = [e for e in entries if e][:MAX_VIDEOS]
        total = len(entries)

        await status.edit_text(f"🚀 Found videos! Downloading and sending the latest {total} one by one...")

        sent_count = 0
        for idx, entry in enumerate(entries, start=1):
            video_url = entry.get('url') or entry.get('webpage_url')
            if not video_url:
                continue

            file_path = f"{TEMP_DIR}/{update.effective_user.id}_{idx}.mp4"

            try:
                # 30-second strict download timeout per video
                await asyncio.wait_for(
                    loop.run_in_executor(None, download_video_sync, video_url, file_path),
                    timeout=30.0
                )

                if os.path.exists(file_path):
                    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

                    # Standard Telegram bot 50MB limit validation
                    if 0 < file_size_mb <= 50:
                        with open(file_path, 'rb') as video_file:
                            await update.message.reply_video(
                                video=video_file,
                                caption=f"📹 Video {idx}/{total}",
                                supports_streaming=True
                            )
                        sent_count += 1
                    else:
                        await update.message.reply_text(f"⚠️ Video {idx} skipped (Exceeds 50MB limit).")

                    # Delete temporary video file immediately after upload
                    os.remove(file_path)

            except asyncio.TimeoutError:
                print(f"Video {idx} timed out.")
                await update.message.reply_text(f"⚠️ Video {idx} timed out. Skipping to next...")
            except Exception as e:
                print(f"Error processing video {idx}: {e}")

            # 1.5-second pacing delay between sends to comply with Telegram rate limits
            await asyncio.sleep(1.5)

        await update.message.reply_text(f"🎉 Done! Successfully delivered {sent_count} video(s).")

    except Exception as e:
        await status.edit_text(f"❌ Error extracting profile: {str(e)}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    print("Bot is live...")
    app.run_polling()
