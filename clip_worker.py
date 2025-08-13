import os
import subprocess
from dataclasses import dataclass
from typing import List

from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class ClipTask:
    startTimeSeconds: float
    durationSeconds: float
    outputPath: str


class ClipExtractionWorker(QObject):
    # Signals to communicate with the GUI thread
    progressUpdated = pyqtSignal(str)
    clipGenerated = pyqtSignal(str, float)
    errorOccurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        vodPath: str,
        matchStartOffsetSeconds: int,
        fakeEventTimestamps: List[int],
        outputDir: str,
        preSeconds: int = 5,
        postSeconds: int = 5,
    ) -> None:
        super().__init__()
        self.vodPath = vodPath
        self.matchStartOffsetSeconds = matchStartOffsetSeconds
        self.fakeEventTimestamps = fakeEventTimestamps
        self.outputDir = outputDir
        self.preSeconds = preSeconds
        self.postSeconds = postSeconds

    def buildTasks(self) -> List[ClipTask]:
        tasks: List[ClipTask] = []
        # How video-relative timestamps are computed:
        # Add the match start offset to each event timestamp to get absolute times
        for idx, relativeEventSecond in enumerate(self.fakeEventTimestamps, start=1):
            absoluteSecond = float(self.matchStartOffsetSeconds + relativeEventSecond)
            # Where to adjust clip duration window
            startTime = max(absoluteSecond - self.preSeconds, 0.0)
            duration = float(self.preSeconds + self.postSeconds)
            outputFilename = f"clip_{idx:02d}_{int(absoluteSecond)}s.mp4"
            outputPath = os.path.join(self.outputDir, outputFilename)
            tasks.append(ClipTask(startTimeSeconds=startTime, durationSeconds=duration, outputPath=outputPath))
        return tasks

    def run(self) -> None:
        try:
            tasks = self.buildTasks()
            total = len(tasks)
            if total == 0:
                self.progressUpdated.emit("No events to process.")
                self.finished.emit()
                return

            for i, task in enumerate(tasks, start=1):
                self.progressUpdated.emit(f"Processing {i}/{total} ...")
                self.executeFfmpeg(task)
                # Emit filename and clip start time (video-relative seconds)
                self.clipGenerated.emit(os.path.basename(task.outputPath), float(task.startTimeSeconds))

            self.progressUpdated.emit("All clips generated.")
        except Exception as exc:  # noqa: BLE001 - surface any unexpected errors
            self.errorOccurred.emit(str(exc))
        finally:
            self.finished.emit()

    def executeFfmpeg(self, task: ClipTask) -> None:
        # How FFmpeg is called to extract clips:
        # ffmpeg -ss <start> -i <input> -t <duration> -c copy <output>
        # Using re-encode fallback to avoid keyframe cut issues and ensure compatibility
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(task.startTimeSeconds),
            "-i",
            self.vodPath,
            "-t",
            str(task.durationSeconds),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            task.outputPath,
        ]

        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError as fnf_err:
            raise RuntimeError(
                "FFmpeg not found. Please install FFmpeg and ensure it is in your PATH."
            ) from fnf_err
        except subprocess.CalledProcessError as cpe:
            raise RuntimeError(f"FFmpeg failed for {os.path.basename(task.outputPath)}") from cpe



