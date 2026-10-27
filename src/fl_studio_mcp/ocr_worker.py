"""Isolated native Windows OCR worker; no GUI input or network use."""
import faulthandler
faulthandler.dump_traceback_later(8)
import asyncio
import json
import sys


async def recognize(path):
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage import StorageFile, FileAccessMode
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.globalization import Language
    file = await StorageFile.get_file_from_path_async(path)
    stream = await file.open_async(FileAccessMode.READ)
    try:
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        results = []
        for language in ('zh-Hans', 'en-US'):
            engine = OcrEngine.try_create_from_language(Language(language))
            if engine is None:
                continue
            result = await engine.recognize_async(bitmap)
            results.append({'language': language, 'words': [
                {'text': word.text, 'line': line_index, 'x': word.bounding_rect.x, 'y': word.bounding_rect.y,
                 'width': word.bounding_rect.width, 'height': word.bounding_rect.height}
                for line_index,line in enumerate(result.lines) for word in line.words]})
        if not results:
            raise RuntimeError('No supported OCR language installed')
        return results
    finally:
        stream.close()


if __name__ == '__main__':
    print(json.dumps(asyncio.run(recognize(sys.argv[1])), ensure_ascii=True))
