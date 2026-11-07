import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
path, words = sys.argv[1], [w.lower() for w in sys.argv[2:]]
for i, line in enumerate(open(path, encoding="utf-8").read().splitlines(), 1):
    low = line.lower()
    if any(w in low for w in words):
        print(f"{i}: {line}")
