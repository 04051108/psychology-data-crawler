"""测试 faster-whisper 转写"""
from faster_whisper import WhisperModel
import time

print("加载模型 (small)...")
t0 = time.time()
model = WhisperModel("small", device="cpu", compute_type="int8")
print(f"模型加载完成: {time.time()-t0:.1f}s")

# 测试一个最小视频
video = r"E:\ai_test\video_get\video_data\我一直迷雾中走着然后_20260731140554.mp4"
print(f"\n转写: {video}")
t0 = time.time()

segments, info = model.transcribe(video, language="zh", beam_size=5)

print(f"检测语言: {info.language}, 时长: {info.duration:.1f}s")
text_parts = []
for seg in segments:
    text_parts.append(seg.text.strip())
    print(f"  [{seg.start:.1f}-{seg.end:.1f}] {seg.text.strip()}")

print(f"\n完整文案:\n{' '.join(text_parts)}")
print(f"转写耗时: {time.time()-t0:.1f}s")
