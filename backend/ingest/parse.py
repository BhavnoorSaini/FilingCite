"""PDF -> DoclingDocument, cached as JSON so re-runs skip the slow parse. Mac only; never deployed."""

import logging
from pathlib import Path

from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument

log = logging.getLogger(__name__)


def make_converter() -> DocumentConverter:
    options = PdfPipelineOptions()
    options.do_ocr = False  # FinanceBench PDFs have a text layer
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def parse(pdf: Path, cache_dir: Path, converter: DocumentConverter) -> DoclingDocument:
    cached = cache_dir / f"{pdf.stem}.json"
    if cached.exists():
        return DoclingDocument.load_from_json(cached)

    log.info("Parsing %s", pdf.name)
    result = converter.convert(pdf)
    if result.status != ConversionStatus.SUCCESS:
        log.warning("%s: %s, %d page errors", pdf.name, result.status.value, len(result.errors))
    result.input.release()

    cache_dir.mkdir(parents=True, exist_ok=True)
    result.document.save_as_json(cached)
    return result.document
