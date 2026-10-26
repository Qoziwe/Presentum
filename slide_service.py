import os
import uuid
import shutil
import subprocess
import glob
from pathlib import Path
from werkzeug.utils import secure_filename
from models import db, Slide, PresentationState

UPLOAD_DIR = Path("static/uploads/slides")
ALLOWED_IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_PDF = {".pdf"}


def init_storage():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def convert_pdf_to_images(pdf_path: Path, output_dir: Path) -> list[Path]:
    """Конвертирует PDF в список PNG-изображений через pdftoppm."""
    if not shutil.which("pdftoppm"):
        raise RuntimeError(
            "Утилита pdftoppm (из пакета poppler) не найдена. "
            "Убедитесь, что установлен poppler."
        )

    prefix = output_dir / f"pdf_page_{uuid.uuid4().hex[:8]}"
    cmd = ["pdftoppm", "-png", "-r", "150", str(pdf_path), str(prefix)]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"Ошибка pdftoppm: {result.stderr.decode(utf-8, errors=ignore)}")

    generated = sorted(glob.glob(f"{prefix}-*.png"))
    return [Path(p) for p in generated]


def add_slides_from_files(files, target_position=None) -> list[Slide]:
    """
    Принимает список FileStorage (изображения или PDF).
    Сохраняет слайды на диск и вставляет в базу данных на указанную позицию (1-based).
    Если target_position None — добавляет в конец.
    """
    init_storage()
    new_slides_data = []

    for file in files:
        if not file or not file.filename:
            continue

        orig_name = secure_filename(file.filename) or "slide"
        ext = Path(orig_name).suffix.lower()

        if ext in ALLOWED_IMAGES:
            unique_name = f"{uuid.uuid4().hex}{ext}"
            dest = UPLOAD_DIR / unique_name
            file.save(dest)
            new_slides_data.append((unique_name, orig_name))

        elif ext in ALLOWED_PDF:
            temp_pdf = UPLOAD_DIR / f"temp_{uuid.uuid4().hex}.pdf"
            file.save(temp_pdf)
            try:
                pages = convert_pdf_to_images(temp_pdf, UPLOAD_DIR)
                for idx, page_path in enumerate(pages, 1):
                    unique_name = f"{uuid.uuid4().hex}.png"
                    final_path = UPLOAD_DIR / unique_name
                    page_path.rename(final_path)
                    new_slides_data.append((unique_name, f"{orig_name} (стр. {idx})"))
            finally:
                if temp_pdf.exists():
                    temp_pdf.unlink()
        else:
            continue

    if not new_slides_data:
        return []

    total_existing = Slide.query.count()

    if target_position is None or target_position < 1 or target_position > total_existing + 1:
        insert_index = total_existing + 1
    else:
        insert_index = int(target_position)

    shift_count = len(new_slides_data)
    if insert_index <= total_existing:
        Slide.query.filter(Slide.order_index >= insert_index).update(
            {Slide.order_index: Slide.order_index + shift_count},
            synchronize_session="fetch"
        )

    created_slides = []
    for i, (fname, orig) in enumerate(new_slides_data):
        slide = Slide(
            filename=fname,
            original_filename=orig,
            order_index=insert_index + i
        )
        db.session.add(slide)
        created_slides.append(slide)

    db.session.commit()
    return created_slides


def delete_slide(slide_id: int) -> bool:
    """Удаляет слайд, удаляет файл с диска и сдвигает индексы."""
    slide = db.session.get(Slide, slide_id)
    if not slide:
        return False

    deleted_index = slide.order_index
    file_path = UPLOAD_DIR / slide.filename
    if file_path.exists():
        file_path.unlink()

    db.session.delete(slide)

    Slide.query.filter(Slide.order_index > deleted_index).update(
        {Slide.order_index: Slide.order_index - 1},
        synchronize_session="fetch"
    )

    state = PresentationState.get_current()
    total_remaining = Slide.query.count()
    if total_remaining == 0:
        state.current_slide_index = 1
    elif state.current_slide_index > total_remaining:
        state.current_slide_index = total_remaining

    db.session.commit()
    return True


def clear_all_slides():
    """Удаляет абсолютно все слайды и очищает директорию."""
    init_storage()
    for item in UPLOAD_DIR.iterdir():
        if item.is_file():
            try:
                item.unlink()
            except OSError:
                pass

    Slide.query.delete()
    state = PresentationState.get_current()
    state.current_slide_index = 1
    db.session.commit()
