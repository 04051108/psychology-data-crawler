"""测试 faster-whisper - 使用有音频的视频"""
from faster_whisper import WhisperModel
import time, os, glob

MODEL_PATH = "models/faster-whisper-small"

print("加载本地模型...")
t0 = time.time()
model = WhisperModel(MODEL_PATH, device="cpu", compute_type="int8")
print(f"模型加载完成: {time.time()-t0:.1f}s")

# 找一个有音频的视频
video_dir = r"E:\ai_test\video_get\video_data"
files = sorted(glob.glob(os.path.join(video_dir, "*.mp4")))

# 找一个黄仕明视频
test_video = None
for f in files:
    if "黄仕明" in os.path.basename(f):
        test_video = f
        break
if not test_video:
    test_video = files[0]

print(f"\n转写: {os.path.basename(test_video)}")
t0 = time.time()

segments, info = model.transcribe(test_video, language="zh", beam_size=5)

print(f"语言: {info.language}, 时长: {info.duration:.1f}s")
text_parts = []
for seg in segments:
    text_parts.append(seg.text.strip())

print(f"\n完整文案:\n{' '.join(text_parts)}")
print(f"\n转写耗时: {time.time()-t0:.1f}s")
