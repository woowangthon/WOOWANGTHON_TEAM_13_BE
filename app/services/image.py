MAX_IMAGE_BYTES = 10 * 1024 * 1024
JPEG_SIGNATURE = bytes.fromhex("ffd8ff")
PNG_SIGNATURE = bytes.fromhex("89504e470d0a1a0a")


class ImageTooLargeError(Exception):
    """사진이 비어 있거나 10MB를 넘을 때 발생합니다."""


class ImageTypeError(Exception):
    """JPEG, PNG, WebP가 아닌 사진일 때 발생합니다."""


class ImageStorageError(Exception):
    """사진 저장소를 사용할 수 없을 때 발생합니다."""


def detect_image_type(data: bytes) -> tuple[str, str]:
    """파일 앞부분으로 실제 사진 형식과 확장자를 판별합니다."""
    if data.startswith(JPEG_SIGNATURE):
        return "image/jpeg", "jpg"
    if data.startswith(PNG_SIGNATURE):
        return "image/png", "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise ImageTypeError


def check_image(data: bytes) -> tuple[str, str]:
    """사진 크기와 실제 형식을 검사하고 형식과 확장자를 돌려줍니다."""
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ImageTooLargeError
    return detect_image_type(data)
