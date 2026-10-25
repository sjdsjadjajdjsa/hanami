# Pictures and videos

The scripts here make the README pictures and Hanami's short videos. You
only need them to redraw those.

- **Screenshots:** `hanami --snapshot panel.png`, then
  `python3 docs/screenshot.py panel.png`. This writes the two README
  pictures and the website's social image.
- **Short video:** `python3 docs/video/video.py hanami.mp4`, music included.
  `--tall` makes the 1080 x 1920 one for Shorts, TikTok and Reels.
- **Longer ones:** `craft.py`, `evening.py`, `play.py` and `seasons.py` work
  the same way. Each says at the top what it needs (Rust, ffmpeg, Pillow,
  NumPy and SciPy, and a KDE Plasma desktop).
- **Music:** the `*_music.py` files write the original pieces. `*_ai.py` and
  `craft_footage.py` set up the real programs that appear on screen.
