"""检查视频是否有音频流"""
import av, os, glob

video_dir = r"E:\ai_test\video_get\video_data"
files = glob.glob(os.path.join(video_dir, "*.mp4"))

print(f"共 {len(files)} 个视频\n")
has_audio = 0
no_audio = 0
samples = []

for i, f in enumerate(files[:50]):
    try:
        c = av.open(f)
        video_streams = [s for s in c.streams if s.type == 'video']
        audio_streams = [s for s in c.streams if s.type == 'audio']
        dur = c.duration / 1000000 if c.duration else 0
        name = os.path.basename(f)[:40]
        if audio_streams:
            has_audio += 1
            if len(samples) < 5:
                samples.append(f"✅ [有音频] {name} | {len(audio_streams)}音轨, {dur:.0f}s")
        else:
            no_audio += 1
            if len(samples) < 5:
                samples.append(f"❌ [无音频] {name} | 仅视频 {dur:.0f}s")
        c.close()
    except Exception as e:
        no_audio += 1
        if len(samples) < 5:
            samples.append(f"❌ [异常] {os.path.basename(f)[:40]} | {type(e).__name__}")

for s in samples:
    print(s)
print(f"\n前50个: 有音频 {has_audio}, 无音频/异常 {no_audio}")
