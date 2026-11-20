import json, sys
from faster_whisper import WhisperModel

audio, out = sys.argv[1], sys.argv[2]
lang = sys.argv[3] if len(sys.argv) > 3 else "zh"

model = WhisperModel("small", device="cpu", compute_type="int8")

kwargs = dict(beam_size=5, vad_filter=True)
if lang == "zh":
    kwargs["language"] = "zh"
    kwargs["initial_prompt"] = "以下是普通话的转写，请使用简体中文，并正确断句。"
else:
    kwargs["language"] = lang  # 例如 "en"，不传中文提示词

segments, info = model.transcribe(audio, **kwargs)
results = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segments]
json.dump(results, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"{out} done, lang={info.language}, segments={len(results)}", flush=True)
