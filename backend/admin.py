import csv
import hmac
import io
import os
import tempfile
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from backend.program_titles import ProgramTitles
from backend.reporting import (
    ReportConfigurationError,
    ReportSettingsStore,
    get_report_template_path,
    install_template,
    template_export_enabled,
)


admin_blueprint = Blueprint("admin", __name__)

PROGRAM_TITLES_PATH = Path(__file__).resolve().parent / "data" / "program_titles.csv"
MAX_TEMPLATE_BYTES = 30 * 1024 * 1024
MAX_CSV_BYTES = 5 * 1024 * 1024


def _authentication_response(message: str, status: int) -> Response:
    response = Response(message, status=status, mimetype="text/plain")
    if status == 401:
        response.headers["WWW-Authenticate"] = 'Basic realm="Panel GrafikPlus", charset="UTF-8"'
    return response


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        expected_username = os.environ.get("ADMIN_USERNAME", "")
        expected_password = os.environ.get("ADMIN_PASSWORD", "")
        if not expected_username or not expected_password:
            current_app.logger.error("Admin credentials are not configured")
            return _authentication_response(
                "Panel administratora nie jest skonfigurowany.", 503
            )

        credentials = request.authorization
        if not credentials or not (
            hmac.compare_digest(credentials.username or "", expected_username)
            and hmac.compare_digest(credentials.password or "", expected_password)
        ):
            return _authentication_response("Wymagane uwierzytelnienie.", 401)
        return view(*args, **kwargs)

    return wrapped


def _read_upload(field_name: str, max_bytes: int) -> tuple[bytes, str]:
    uploaded_file = request.files.get(field_name)
    if uploaded_file is None or not uploaded_file.filename:
        raise ReportConfigurationError("Nie wybrano pliku do przesłania.")
    data = uploaded_file.stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ReportConfigurationError("Przesłany plik jest zbyt duży.")
    if not data:
        raise ReportConfigurationError("Przesłany plik jest pusty.")
    return data, uploaded_file.filename


def _validate_program_titles(data: bytes, filename: str) -> None:
    if not filename.lower().endswith(".csv"):
        raise ReportConfigurationError("Słownik musi być plikiem CSV.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ReportConfigurationError("Plik CSV musi używać kodowania UTF-8.") from exc

    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=";", strict=True))
    except csv.Error as exc:
        raise ReportConfigurationError("Plik CSV ma nieprawidłową strukturę.") from exc
    if not rows:
        raise ReportConfigurationError("Plik CSV nie zawiera żadnych wpisów.")
    if any(len(row) != 2 or not row[0].strip() for row in rows):
        raise ReportConfigurationError(
            "Każdy wiersz CSV musi zawierać opis i tytuł rozdzielone średnikiem."
        )


def _install_program_titles(data: bytes, filename: str) -> None:
    _validate_program_titles(data, filename)
    PROGRAM_TITLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=PROGRAM_TITLES_PATH.parent,
            suffix=".csv.tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(data)
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, PROGRAM_TITLES_PATH)
        temporary_path = None
        ProgramTitles.reload_titles(str(PROGRAM_TITLES_PATH))
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _file_details(path: Path | None) -> dict[str, str | bool]:
    if path is None or not path.is_file():
        return {"exists": False, "name": "Brak pliku", "modified": "—"}
    modified = path.stat().st_mtime
    return {
        "exists": True,
        "name": path.name,
        "modified": datetime.fromtimestamp(modified).strftime("%d.%m.%Y %H:%M"),
    }


@admin_blueprint.route("/")
@admin_required
def index():
    settings = ReportSettingsStore().load()
    return render_template(
        "admin.html",
        settings=settings,
        template_details=_file_details(get_report_template_path(required=False)),
        csv_details=_file_details(PROGRAM_TITLES_PATH),
        template_export_enabled=template_export_enabled(),
    )


@admin_blueprint.post("/settings")
@admin_required
def save_settings():
    try:
        ReportSettingsStore().save(request.form.to_dict())
        flash("Ustawienia raportu zostały zapisane.", "success")
    except ReportConfigurationError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin.index"))


@admin_blueprint.post("/template")
@admin_required
def upload_template():
    try:
        data, filename = _read_upload("template", MAX_TEMPLATE_BYTES)
        install_template(data, filename)
        flash("Szablon raportu został podmieniony.", "success")
    except (OSError, ReportConfigurationError) as exc:
        current_app.logger.warning("Template upload failed: %s", exc)
        flash(str(exc), "error")
    return redirect(url_for("admin.index"))


@admin_blueprint.post("/program-titles")
@admin_required
def upload_program_titles():
    try:
        data, filename = _read_upload("program_titles", MAX_CSV_BYTES)
        _install_program_titles(data, filename)
        flash("Słownik tytułów został podmieniony i przeładowany.", "success")
    except (OSError, ReportConfigurationError) as exc:
        current_app.logger.warning("Program-title upload failed: %s", exc)
        flash(str(exc), "error")
    return redirect(url_for("admin.index"))
