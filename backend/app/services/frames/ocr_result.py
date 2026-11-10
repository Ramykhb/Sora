class OCRResult(tuple):
    """Keep the existing (text, confidence) interface with explicit result warnings."""
    def __new__(cls, text, confidence, warnings=()):
        result = super().__new__(cls, (text, confidence))
        result.warnings = tuple(warnings)
        return result
