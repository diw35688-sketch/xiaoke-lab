import urllib.request

t = urllib.request.urlopen(
    "http://127.0.0.1:8000/static/vad_mode.js", timeout=10
).read().decode("utf-8")
print("has mic-emoji:", "🎤" in t)
print("has button id:", "vad-mode-btn" in t)
print("has form target:", 'getElementById("form")' in t)
print("has state id:", "vad-state" in t)
print("length:", len(t))
