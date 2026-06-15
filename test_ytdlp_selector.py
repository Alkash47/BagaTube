import yt_dlp
import traceback

dummy_formats2 = [
    {"format_id": "1", "vcodec": "none", "acodec": "mp4a", "height": None, "ext": "m4a", "filesize": 100},
    {"format_id": "2", "vcodec": "avc1", "acodec": "none", "height": 1080, "ext": "mp4", "filesize": 500},
]
ydl_opts = {
    "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    try:
        selector = ydl.build_format_selector(ydl_opts["format"])
        formats_to_download = list(selector({"formats": dummy_formats2}))
        print("Selected 2:", formats_to_download)
    except Exception as e:
        print("Error 2 traceback:")
        traceback.print_exc()

# Test 4: bestvideo exists, but bestaudio does NOT exist
dummy_formats4 = [
    {"format_id": "2", "vcodec": "avc1", "acodec": "none", "height": 720, "ext": "mp4", "filesize": 500},
]
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    try:
        selector = ydl.build_format_selector(ydl_opts["format"])
        formats_to_download = list(selector({"formats": dummy_formats4}))
        print("Selected 4:", formats_to_download)
    except Exception as e:
        print("Error 4 traceback:")
        traceback.print_exc()
