import hmac
import os
import re
import time
import uuid
from datetime import datetime
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from file_processor import (
    is_tiktok_url,
    parse_upload,
    results_to_link_table,
    table_to_xlsx,
    urls_from_table,
)
from tiktok_stats import DEFAULT_BROWSER, fetch_many_video_data


app = FastAPI(title="TikTok Stats Internal Tool")
security = HTTPBasic(auto_error=False)
PREVIEW_CACHE: dict[str, tuple[float, bytes, str, str]] = {}
PREVIEW_TTL_SECONDS = 15 * 60
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def require_auth(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    password = os.getenv("INTERNAL_TOOL_PASSWORD")
    if not password:
        return

    username = os.getenv("INTERNAL_TOOL_USER", "admin")
    if credentials is None:
        raise_auth_error()

    valid_user = hmac.compare_digest(credentials.username, username)
    valid_password = hmac.compare_digest(credentials.password, password)
    if not (valid_user and valid_password):
        raise_auth_error()


def raise_auth_error() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Basic"},
    )


def split_links(raw_links: str) -> list[str]:
    links = [part.strip() for part in re.split(r"[\n,]+", raw_links) if part.strip()]
    return links


def file_download(content: bytes, filename: str, media_type: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )


def export_filename(extension: str = "xlsx") -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"tiktok-video-stats-{timestamp}.{extension}"


def remember_preview(content: bytes, filename: str, media_type: str) -> str:
    now = time.time()
    expired_keys = [
        key
        for key, (created_at, _, _, _) in PREVIEW_CACHE.items()
        if now - created_at > PREVIEW_TTL_SECONDS
    ]
    for key in expired_keys:
        PREVIEW_CACHE.pop(key, None)

    preview_id = uuid.uuid4().hex
    PREVIEW_CACHE[preview_id] = (now, content, filename, media_type)
    return preview_id


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def index() -> str:
    return """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TikTok Stats</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #5d6673;
      --line: #d8dde5;
      --accent: #0f766e;
      --accent-strong: #115e59;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main {
      width: min(920px, calc(100vw - 32px));
      margin: 40px auto;
    }
    h1 {
      margin: 0 0 8px;
      font-size: 28px;
      font-weight: 700;
      letter-spacing: 0;
    }
    p { margin: 0; color: var(--muted); }
    .mode-switch {
      display: inline-flex;
      gap: 4px;
      margin-top: 24px;
      padding: 4px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #eef2f6;
    }
    .mode {
      min-height: 36px;
      border: 0;
      border-radius: 5px;
      padding: 0 14px;
      background: transparent;
      color: var(--muted);
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    .mode:hover,
    .mode.active {
      background: #fff;
      color: var(--text);
      box-shadow: 0 1px 2px rgb(16 24 40 / 0.06);
    }
    form {
      display: none;
      margin-top: 28px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 1px 2px rgb(16 24 40 / 0.04);
    }
    form.active { display: block; }
    label {
      display: block;
      margin-bottom: 8px;
      font-weight: 600;
    }
    textarea,
    input[type="file"] {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      padding: 10px 12px;
      font: inherit;
    }
    textarea {
      min-height: 180px;
      resize: vertical;
    }
    input[type="file"].file-input {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      opacity: 0;
      pointer-events: none;
    }
    .dropzone {
      display: block;
      border: 1px dashed #a8b3c2;
      border-radius: 8px;
      background: #fbfcfe;
      padding: 28px 18px;
      text-align: center;
      cursor: pointer;
      transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
    }
    .dropzone:hover,
    .dropzone.dragover {
      border-color: var(--accent);
      background: #f0fdfa;
      box-shadow: 0 0 0 3px rgb(15 118 110 / 0.12);
    }
    .dropzone strong {
      display: block;
      margin-bottom: 6px;
      font-size: 16px;
    }
    .dropzone span {
      color: var(--muted);
      font-size: 13px;
    }
    .file-name {
      margin-top: 10px;
      color: var(--text);
      font-weight: 700;
      overflow-wrap: anywhere;
    }
    .hint {
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
    }
    .actions {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 22px;
    }
    .primary {
      min-height: 44px;
      border: 0;
      border-radius: 6px;
      padding: 0 18px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    .primary:hover { background: var(--accent-strong); }
    .primary:disabled { cursor: wait; opacity: 0.7; }
    .status { color: var(--muted); min-height: 22px; }
    .modal {
      position: fixed;
      inset: 0;
      display: none;
      z-index: 20;
    }
    .modal.open { display: block; }
    .modal-backdrop {
      position: absolute;
      inset: 0;
      background: rgb(15 23 42 / 0.42);
    }
    .modal-card {
      position: relative;
      width: min(1100px, calc(100vw - 32px));
      max-height: calc(100vh - 48px);
      margin: 24px auto;
      overflow: hidden;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 20px 60px rgb(15 23 42 / 0.24);
      display: flex;
      flex-direction: column;
    }
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      padding: 20px 22px 14px;
      border-bottom: 1px solid var(--line);
    }
    .modal-header h2 {
      margin: 0 0 4px;
      font-size: 20px;
      letter-spacing: 0;
    }
    .icon-button {
      width: 36px;
      min-height: 36px;
      border: 0;
      border-radius: 6px;
      background: #eef2f6;
      color: var(--text);
      font-size: 24px;
      line-height: 1;
      cursor: pointer;
    }
    .preview-wrap {
      overflow: auto;
      padding: 0 22px;
    }
    table {
      width: 100%;
      min-width: 1200px;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      max-width: 320px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }
    th {
      position: sticky;
      top: 0;
      background: #f8fafc;
      font-weight: 700;
      white-space: nowrap;
      z-index: 1;
    }
    .modal-actions {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      padding: 16px 22px 20px;
      border-top: 1px solid var(--line);
    }
    .secondary {
      min-height: 44px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 18px;
      background: #fff;
      color: var(--text);
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    .processing-card {
      width: min(420px, calc(100vw - 32px));
      margin: 18vh auto 0;
      padding: 28px;
      align-items: center;
      text-align: center;
    }
    .spinner {
      width: 48px;
      height: 48px;
      border-radius: 50%;
      border: 4px solid #d8dde5;
      border-top-color: var(--accent);
      animation: spin 0.8s linear infinite;
      margin-bottom: 18px;
    }
    .processing-card h2 {
      margin: 0 0 8px;
      font-size: 20px;
      letter-spacing: 0;
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    @media (max-width: 720px) {
      main { margin: 24px auto; }
      form { padding: 18px; }
      .modal-card { margin: 16px auto; max-height: calc(100vh - 32px); }
    }
  </style>
</head>
<body>
  <main>
    <h1>TikTok Stats</h1>
    <p>Dán link TikTok hoặc tải file để xuất file thống kê.</p>

    <div class="mode-switch" role="tablist" aria-label="Chọn cách nhập">
      <button class="mode active" type="button" data-panel="paste-form">Dán link</button>
      <button class="mode" type="button" data-panel="upload-form">Tải file</button>
    </div>

    <form id="paste-form" class="active" action="/preview-links" method="post">
      <label for="links">Danh sách link TikTok</label>
      <textarea id="links" name="links" placeholder="Mỗi dòng một link, hoặc ngăn cách bằng dấu phẩy" required></textarea>
      <div class="hint">File xuất ra gồm các cột: Url, Caption, View, Like, Comment, Share, Save.</div>
      <div class="actions">
        <button id="paste-submit" class="primary" type="submit">Lấy số liệu</button>
        <span id="paste-status" class="status"></span>
      </div>
    </form>

    <form id="upload-form" action="/preview-file" method="post" enctype="multipart/form-data">
      <label for="file">File dữ liệu</label>
      <label id="dropzone" class="dropzone" for="file">
        <strong>Chọn file hoặc kéo thả vào đây</strong>
        <span>Hỗ trợ file danh sách link TikTok</span>
        <div id="file-name" class="file-name">Chưa chọn file</div>
      </label>
      <input id="file" class="file-input" name="file" type="file" accept=".csv,.xlsx,.xlsm" required>
      <div class="hint">Hệ thống tự nhận cột link theo tên như url, link, tiktok_url hoặc video_url.</div>
      <div class="actions">
        <button id="upload-submit" class="primary" type="submit">Lấy số liệu</button>
        <span id="upload-status" class="status"></span>
      </div>
    </form>

    <div id="preview-modal" class="modal" aria-hidden="true">
      <div class="modal-backdrop"></div>
      <section class="modal-card" role="dialog" aria-modal="true" aria-labelledby="preview-title">
        <div class="modal-header">
          <div>
            <h2 id="preview-title">Preview file xuất</h2>
            <p id="preview-subtitle"></p>
          </div>
          <button id="close-preview" class="icon-button" type="button" aria-label="Đóng">×</button>
        </div>
        <div class="preview-wrap">
          <table>
            <thead id="preview-head"></thead>
            <tbody id="preview-body"></tbody>
          </table>
        </div>
        <div class="modal-actions">
          <button id="cancel-export" class="secondary" type="button">Đóng</button>
          <button id="export-csv" class="primary" type="button">Xuất file</button>
        </div>
      </section>
    </div>

    <div id="processing-modal" class="modal" aria-hidden="true">
      <div class="modal-backdrop"></div>
      <section class="modal-card processing-card" role="dialog" aria-modal="true" aria-labelledby="processing-title">
        <div class="spinner" aria-hidden="true"></div>
        <h2 id="processing-title">Đang xử lý dữ liệu</h2>
        <p>Vui lòng giữ nguyên tab này trong khi hệ thống lấy số liệu TikTok.</p>
      </section>
    </div>
  </main>

  <script>
    const modes = document.querySelectorAll(".mode");
    const forms = document.querySelectorAll("form");
    modes.forEach((mode) => {
      mode.addEventListener("click", () => {
        modes.forEach((item) => item.classList.remove("active"));
        forms.forEach((form) => form.classList.remove("active"));
        mode.classList.add("active");
        document.getElementById(mode.dataset.panel).classList.add("active");
      });
    });

    const pasteForm = document.getElementById("paste-form");
    const pasteButton = document.getElementById("paste-submit");
    const pasteStatus = document.getElementById("paste-status");
    const linksInput = document.getElementById("links");
    const uploadForm = document.getElementById("upload-form");
    const uploadButton = document.getElementById("upload-submit");
    const uploadStatus = document.getElementById("upload-status");
    const fileInput = document.getElementById("file");
    const dropzone = document.getElementById("dropzone");
    const fileName = document.getElementById("file-name");
    const previewModal = document.getElementById("preview-modal");
    const previewSubtitle = document.getElementById("preview-subtitle");
    const previewHead = document.getElementById("preview-head");
    const previewBody = document.getElementById("preview-body");
    const processingModal = document.getElementById("processing-modal");
    const exportButton = document.getElementById("export-csv");
    const closePreview = document.getElementById("close-preview");
    const cancelExport = document.getElementById("cancel-export");
    let previewId = "";
    let previewFilename = "";

    function setPasteBusy(isBusy) {
      pasteButton.disabled = isBusy;
      linksInput.disabled = isBusy;
      modes.forEach((mode) => {
        mode.disabled = isBusy;
      });
      processingModal.classList.toggle("open", isBusy);
      processingModal.setAttribute("aria-hidden", isBusy ? "false" : "true");
      if (isBusy) {
        pasteStatus.textContent = "Đang xử lý, vui lòng chờ.";
      }
    }

    function setUploadBusy(isBusy) {
      uploadButton.disabled = isBusy;
      fileInput.disabled = isBusy;
      modes.forEach((mode) => {
        mode.disabled = isBusy;
      });
      processingModal.classList.toggle("open", isBusy);
      processingModal.setAttribute("aria-hidden", isBusy ? "false" : "true");
      if (isBusy) {
        uploadStatus.textContent = "Đang xử lý, vui lòng chờ.";
      }
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function showPreview(payload) {
      const headers = payload.headers || [];
      const rows = payload.rows || [];
      previewId = payload.preview_id || "";
      previewFilename = payload.filename || "";
      exportButton.textContent = "Xuất file";
      previewSubtitle.textContent = rows.length + " dòng đã xử lý. Kiểm tra nhanh rồi bấm Export để tải file.";
      previewHead.innerHTML = "<tr>" + headers.map((header) => "<th>" + escapeHtml(header) + "</th>").join("") + "</tr>";
      previewBody.innerHTML = rows.slice(0, 50).map((row) =>
        "<tr>" + headers.map((_, index) => "<td>" + escapeHtml(row[index]) + "</td>").join("") + "</tr>"
      ).join("");
      previewModal.classList.add("open");
      previewModal.setAttribute("aria-hidden", "false");
    }

    function hidePreview() {
      previewModal.classList.remove("open");
      previewModal.setAttribute("aria-hidden", "true");
    }

    function downloadCsv() {
      if (!previewId) return;
      window.location.href = "/download-preview/" + encodeURIComponent(previewId);
    }

    async function fetchJsonOrThrow(url, options, fallbackMessage) {
      const response = await fetch(url, options);
      const contentType = response.headers.get("content-type") || "";
      let payload = null;
      let rawText = "";

      if (contentType.includes("application/json")) {
        payload = await response.json();
      } else {
        rawText = await response.text();
      }

      if (!response.ok) {
        const detail = payload && typeof payload.detail === "string"
          ? payload.detail
          : rawText || fallbackMessage;
        throw new Error(detail);
      }

      if (!payload) {
        throw new Error(fallbackMessage);
      }
      return payload;
    }

    function updateFileName() {
      const file = fileInput.files && fileInput.files[0];
      fileName.textContent = file ? file.name : "Chưa chọn file";
    }

    fileInput.addEventListener("change", updateFileName);
    ["dragenter", "dragover"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        dropzone.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        dropzone.classList.remove("dragover");
      });
    });
    dropzone.addEventListener("drop", (event) => {
      const files = event.dataTransfer && event.dataTransfer.files;
      if (!files || files.length === 0) return;
      const transfer = new DataTransfer();
      transfer.items.add(files[0]);
      fileInput.files = transfer.files;
      updateFileName();
    });

    pasteForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(pasteForm);
      setPasteBusy(true);
      try {
        const payload = await fetchJsonOrThrow(
          "/preview-links",
          { method: "POST", body: formData },
          "Không xử lý được danh sách link."
        );
        showPreview(payload);
        pasteStatus.textContent = "";
      } catch (error) {
        pasteStatus.textContent = error.message;
      } finally {
        setPasteBusy(false);
      }
    });

    uploadForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(uploadForm);
      setUploadBusy(true);
      try {
        const payload = await fetchJsonOrThrow(
          "/preview-file",
          { method: "POST", body: formData },
          "Không xử lý được file."
        );
        showPreview(payload);
        uploadStatus.textContent = "";
      } catch (error) {
        uploadStatus.textContent = error.message;
      } finally {
        setUploadBusy(false);
      }
    });

    closePreview.addEventListener("click", hidePreview);
    cancelExport.addEventListener("click", hidePreview);
    exportButton.addEventListener("click", downloadCsv);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") hidePreview();
    });
  </script>
</body>
</html>"""


@app.post("/process-links", dependencies=[Depends(require_auth)])
async def process_links(links: str = Form(...)) -> Response:
    table = await build_link_table(links)
    return file_download(table_to_xlsx(table), export_filename("xlsx"), XLSX_MEDIA_TYPE)


@app.post("/preview-links", dependencies=[Depends(require_auth)])
async def preview_links(links: str = Form(...)) -> dict[str, object]:
    table = await build_link_table(links)
    xlsx_content = table_to_xlsx(table)
    filename = export_filename("xlsx")
    return {
        "headers": table.headers,
        "rows": table.rows,
        "preview_id": remember_preview(xlsx_content, filename, XLSX_MEDIA_TYPE),
        "filename": filename,
    }


@app.get("/download-preview/{preview_id}", dependencies=[Depends(require_auth)])
async def download_preview(preview_id: str) -> Response:
    cached = PREVIEW_CACHE.get(preview_id)
    if cached is None:
        raise HTTPException(status_code=404, detail="Preview đã hết hạn. Vui lòng xử lý lại.")
    _, content, filename, media_type = cached
    return file_download(content, filename, media_type)


@app.post("/preview-file", dependencies=[Depends(require_auth)])
async def preview_file(file: UploadFile = File(...)) -> dict[str, object]:
    enriched, output, output_name, media_type = await build_file_output(file)
    return {
        "headers": enriched.headers,
        "rows": enriched.rows,
        "preview_id": remember_preview(output, output_name, media_type),
        "filename": output_name,
    }


async def build_link_table(links: str):
    urls = split_links(links)
    max_rows = int(os.getenv("MAX_BATCH_ROWS", "100"))
    if not urls:
        raise HTTPException(status_code=400, detail="Vui lòng nhập ít nhất một link TikTok.")
    if len(urls) > max_rows:
        raise HTTPException(status_code=400, detail=f"Tối đa {max_rows} link mỗi lần.")

    invalid_urls = [url for url in urls if not is_tiktok_url(url)]
    if invalid_urls:
        raise HTTPException(status_code=400, detail=f"Link không hợp lệ: {invalid_urls[0]}")

    results = await fetch_many_video_data(urls, browser=DEFAULT_BROWSER, headless=True)
    return results_to_link_table(urls, results)


async def build_file_output(file: UploadFile):
    filename = file.filename or "input.csv"
    content = await file.read()
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "10"))
    if len(content) > max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File tối đa {max_upload_mb} MB.")

    try:
        table = parse_upload(filename, content)
        urls = urls_from_table(table)
        max_rows = int(os.getenv("MAX_BATCH_ROWS", "100"))
        if len(table.rows) > max_rows:
            raise ValueError(f"Batch limit is {max_rows} rows. Split the file and try again.")
        if not urls:
            raise ValueError("Không tìm thấy link TikTok hợp lệ trong file.")
        results = await fetch_many_video_data(urls, browser=DEFAULT_BROWSER, headless=True)
        output_table = results_to_link_table(urls, results)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Không đọc được file. Vui lòng kiểm tra file dữ liệu và thử lại. Chi tiết: {type(exc).__name__}",
        ) from exc

    output = table_to_xlsx(output_table)
    media_type = XLSX_MEDIA_TYPE
    output_name = export_filename("xlsx")
    return output_table, output, output_name, media_type


@app.post("/process", dependencies=[Depends(require_auth)])
async def process_file(file: UploadFile = File(...)) -> Response:
    _, output, output_name, media_type = await build_file_output(file)
    return file_download(output, output_name, media_type)
