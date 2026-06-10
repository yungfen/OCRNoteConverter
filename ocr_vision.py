"""macOS Vision-framework OCR backend (the engine behind Live Text).

Far better at handwriting than Tesseract. Only available on macOS with the
pyobjc Vision bindings installed; callers should catch ImportError and fall
back to Tesseract.
"""

import Quartz
import Vision
from Foundation import NSData


def extract_text(image_bytes: bytes) -> tuple[str, float]:
    """Return (text, confidence 0-100) using Apple Vision OCR."""
    ns_data = NSData.dataWithBytes_length_(image_bytes, len(image_bytes))
    image_source = Quartz.CGImageSourceCreateWithData(ns_data, None)
    if image_source is None:
        raise ValueError("could not decode image")
    cg_image = Quartz.CGImageSourceCreateImageAtIndex(image_source, 0, None)
    if cg_image is None:
        raise ValueError("could not decode image")

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    request.setRecognitionLanguages_(["en-US", "zh-Hant", "zh-Hans"])

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        cg_image, None
    )
    success, error = handler.performRequests_error_([request], None)
    if not success:
        raise RuntimeError(f"Vision OCR failed: {error}")

    lines = []
    confs = []
    for observation in request.results() or []:
        candidate = observation.topCandidates_(1)
        if candidate and len(candidate) > 0:
            lines.append(str(candidate[0].string()))
            confs.append(float(candidate[0].confidence()))

    text = "\n".join(lines)
    # Vision confidence is 0-1; scale to 0-100 to match the Tesseract backend.
    avg_conf = (sum(confs) / len(confs) * 100.0) if confs else 0.0
    return text, avg_conf
