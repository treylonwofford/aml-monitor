"""Inline web/data.json into web/template.html -> web/index.html (one self-contained file)."""
import os
here = os.path.dirname(os.path.abspath(__file__))
t = open(os.path.join(here, "web/template.html")).read()
d = open(os.path.join(here, "web/data.json")).read().replace("</", "<\\/")
open(os.path.join(here, "web/index.html"), "w").write(t.replace("__DATA__", d))
print("web/index.html", os.path.getsize(os.path.join(here, "web/index.html")) // 1024, "KB")
