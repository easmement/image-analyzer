from importlib.metadata import version

__version__ = version("image-analyzer")


def main() -> None:
    import uvicorn

    from image_analyzer.core.config import settings

    uvicorn.run("image_analyzer.main:app", host=settings.host, port=settings.port, reload=True)
