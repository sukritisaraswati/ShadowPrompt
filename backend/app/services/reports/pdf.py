"""PDF export for both report types.

The PDF is rendered from the same autoescaped HTML as the HTML report, so
there is one template to keep safe. Two renderers are supported:

* WeasyPrint, the blueprint's choice, which gives the best output. It needs
  native Pango/GTK libraries, which the Docker image installs.
* xhtml2pdf, pure Python, as a fallback for machines without those libraries
  (for example a Windows development setup). Its CSS support is simpler, so
  the layout is plainer, but the content is identical.

Neither renderer is allowed to fetch anything. Reports never reference
external resources, but if hostile content ever slipped through escaping, a
renderer that followed URLs would become a server-side request forgery
channel, so every fetch is refused outright.
"""

from __future__ import annotations

import io
import logging
from functools import lru_cache

from app.core.errors import AppError
from app.schemas.common import ErrorCode

logger = logging.getLogger(__name__)


class _NoFetch(ValueError):
    pass


def _refuse_weasyprint_fetch(url: str, *args: object, **kwargs: object) -> dict:
    raise _NoFetch(f"external resources are disabled in reports: {url[:60]}")


def _refuse_xhtml2pdf_fetch(uri: str, rel: str) -> str:
    # An empty path tells xhtml2pdf there is no resource to load.
    return ""


@lru_cache
def available_renderer() -> str | None:
    """The best working renderer on this machine, or ``None``."""
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        # OSError: the package is installed but its native libraries are not.
        pass
    else:
        return "weasyprint"
    try:
        import xhtml2pdf  # noqa: F401
    except ImportError:
        return None
    return "xhtml2pdf"


def render_pdf(html: str) -> bytes:
    renderer = available_renderer()
    if renderer == "weasyprint":
        import weasyprint

        return weasyprint.HTML(string=html, url_fetcher=_refuse_weasyprint_fetch).write_pdf()

    if renderer == "xhtml2pdf":
        from xhtml2pdf import pisa

        buffer = io.BytesIO()
        result = pisa.CreatePDF(
            html, dest=buffer, encoding="utf-8", link_callback=_refuse_xhtml2pdf_fetch
        )
        if result.err:
            logger.warning("xhtml2pdf reported %d rendering error(s)", result.err)
            raise AppError(
                ErrorCode.INTERNAL_ERROR, "The PDF could not be generated.", status_code=500
            )
        return buffer.getvalue()

    raise AppError(
        ErrorCode.NOT_IMPLEMENTED,
        "PDF export is not available on this server.",
        status_code=501,
        detail="Install the 'pdf' extra (WeasyPrint or xhtml2pdf). HTML export works.",
    )
