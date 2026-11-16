"""Linked files: the PDFs, Office files and Google files a scan's pages link to.

The report's "Documents" tab lists them. In code they are *linked files*, not
"documents", on purpose: in the crawler a "document" is an HTML page (the
rendered document, ``orchestrator._is_document_url``), and one word for two
things would make every reader of this code check which one is meant.

The pieces, in the order a crawl uses them:

* :mod:`.formats` decides whether a URL or a server's Content-Type names a
  linked file, and which type.
* :mod:`.discovery` finds every way a page reaches one: links, frames,
  ``object`` and ``embed``.
* :mod:`.tracker` records what each page links to while the crawl runs, and
  checks the PDFs at the end.
* :mod:`.fetch` downloads one file with a size and a time limit.
* :mod:`.pdf_check` runs the machine checks on a PDF's bytes.

Storage is in :mod:`audit.db.linked_files`; the report's list is in
:mod:`audit.web.linked_files_queries`. Nothing here sends a file or a result
anywhere: a file is downloaded, checked in memory, and only the result is
kept.
"""
