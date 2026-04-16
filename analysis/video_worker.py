"""QThread wrapper around the lecture-video analysis pipeline."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from analysis.video_pipeline import run_video_analysis


class VideoAnalysisWorker(QThread):
    log_line = Signal(str)
    failed = Signal(str)
    completed = Signal(object)

    def __init__(
        self,
        video_path: str,
        output_dir: str,
        server_url: str,
        language: str | None = "Chinese",
    ):
        super().__init__()
        self._video_path = video_path
        self._output_dir = output_dir
        self._server_url = server_url
        self._language = language
        self._running = True

    def run(self):
        try:
            result = run_video_analysis(
                self._video_path,
                self._output_dir,
                server_url=self._server_url,
                language=self._language,
                log_callback=self.log_line.emit,
                should_stop=lambda: not self._running,
            )
            if self._running:
                self.completed.emit(result)
        except InterruptedError:
            self.log_line.emit("视频分析已停止。")
        except Exception as exc:
            self.failed.emit(str(exc))

    def stop(self):
        self._running = False
