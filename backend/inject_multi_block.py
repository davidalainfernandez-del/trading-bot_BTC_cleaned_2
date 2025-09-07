#!/usr/bin/env python3
import sys, re, io, os

if len(sys.argv) < 3:
    print("Usage: python3 inject_multi_block.py <app.py> <append_block.py>")
    sys.exit(1)

app_path = sys.argv[1]
blk_path = sys.argv[2]

src = open(app_path, "r", encoding="utf-8").read()
blk = open(blk_path, "r", encoding="utf-8").read()

m = re.search(r"^\s*if\s+__name__\s*==\s*['\"]__main__['\"]\s*:\s*$", src, re.M)
if not m:
    print("ERROR: could not find `if __name__ == \"__main__\":` in", app_path)
    sys.exit(2)

insert_at = m.start()
new_src = src[:insert_at] + "\n\n# >>> BEGIN Multi-Actifs Append Block >>>\n" + blk + "\n# <<< END Multi-Actifs Append Block <<<\n\n" + src[insert_at:]

bak = app_path + ".bak"
open(bak, "w", encoding="utf-8").write(src)
open(app_path, "w", encoding="utf-8").write(new_src)
print("Injected block into", app_path, "Backup written to", bak)
