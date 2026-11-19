"""The Word and PowerPoint check's labelled real files (AGENTS.md, "real pages first").

``office_files.json`` holds one entry per distinct file (by SHA-256): the
link a University of Michigan page has to it, that page, the bytes' hash,
the verdict each criterion should get, and why we believe it. A Google Doc
or Slides deck is labelled as the .docx or .pptx file Google exports
(``docs.google.com/document/d/ID/export?format=docx``), because that is what
the check reads.

Sources (approved by the developer, 2026-11-17): files linked from
hr.umich.edu, rossweb.bus.umich.edu/ross-it/, its.umich.edu,
finance.umich.edu and lsa.umich.edu, found by reading those sites' pages
one at a time (robots.txt obeyed, at most one request a second) and
downloaded once each. Files over 10 MB (the app's download limit), private
Google files (HTTP 401) and Google Drive files (Google's robots.txt asks
scanners not to download them) are not in the set: the app would not
check them either.

Labels were written BEFORE any rule of the check existed, by labelling
agents separate from the check's author, following the protocol in
``test_office_real_files.py``. Criteria: ``alt_text``, ``table_header``,
``slide_title``, ``language``, ``headings``, ``heading_order``,
``link_text``, ``title``, each "fail", "pass" or "n/a", and ``barrier``:
whether a screen reader user meets a barrier the first five can prove. The
basis is the file's structure (its XML), with embedded pictures viewed
where the verdict needed it; no file was opened in Word, PowerPoint or a
screen reader, and no outside source labelled these files. This is
evidence, not validation by accessibility experts.

``split`` was fixed before labelling and does not depend on the labels: a
file is in the holdout part when its SHA-256 starts with 0-7, else in the
tuning part. The check was written and tuned on the tuning part only; the
holdout part is scored once and reported separately.

Files with ``"source": "gov-org-2026-11-18"`` (77: 44 PowerPoint, 33
Word) were added on 2026-11-18 and 19, after every rule existed, to test
the check on files it was not tuned on. Sources (approved by the developer
in general, 2026-11-18): files linked from www.section508.gov,
grants.nih.gov (two hosted on osp.od.nih.gov), www.cdc.gov,
stacks.cdc.gov, www.aaal.org (hosted on assets.noviams.com),
isaac-online.org and accessible.org, read one at a time with robots.txt
obeyed. Labelling agents labelled them under the same protocol, without
access to the check's code and before the check was run on them. All are
in the holdout part whatever their SHA-256, and no rule was changed after
scoring them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SET = Path(__file__).with_name("office_files.json")

#: Each criterion and the check key that should fail when it is "fail".
CRITERIA: dict[str, str] = {
    "alt_text": "no_alt_text",
    "table_header": "table_no_header",
    "slide_title": "slide_no_title",
    "language": "no_language",
    "headings": "no_headings",
    "heading_order": "skipped_heading_level",
    "link_text": "unclear_link_text",
    "title": "no_title",
}


def load() -> list[dict[str, Any]]:
    return list(json.loads(SET.read_text(encoding="utf-8"))["files"])
