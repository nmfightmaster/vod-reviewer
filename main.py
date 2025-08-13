import os
import sys
from typing import List

from PyQt6.QtCore import QThread, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QGroupBox,
    QGridLayout,
    QLayout,
    QSizePolicy,
    QMenu,
    QSpacerItem,
    QSlider,
    QSplitter,
)

from clip_worker import ClipExtractionWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        # Where to adjust the hard-coded events. Replace with Riot API or detection later.
        self.eventsConfig = [
            {"time": 10, "eventType": "kill"},
            {"time": 35, "eventType": "death"},
            {"time": 75, "eventType": "kill"},
            {"time": 120, "eventType": "death"},
        ]
        self.vodFilePath: str = ""
        self.workerThread: QThread | None = None
        self.worker: ClipExtractionWorker | None = None
        self.currentOutputDir: str = ""
        self.currentClipIndex: int = -1
        self.player: QMediaPlayer | None = None
        self.audioOutput: QAudioOutput | None = None
        self.videoWidget: QVideoWidget | None = None

        self.setWindowTitle("Valorant VOD Clip Extractor")
        self.resize(980, 680)

        self.buildUi()
        self.setupStyles()
        self.ensureClipsFolderExists()

    def buildUi(self) -> None:
        centralWidget = QWidget(self)
        self.setCentralWidget(centralWidget)

        rootLayout = QVBoxLayout()
        rootLayout.setContentsMargins(16, 16, 16, 16)
        rootLayout.setSpacing(14)
        centralWidget.setLayout(rootLayout)

        # Splitter for YouTube/IDE-like layout: large viewer left, controls right
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        rootLayout.addWidget(splitter, 1)

        # Right panel container
        rightPanel = QWidget()
        rightLayout = QVBoxLayout()
        rightLayout.setSpacing(10)
        rightPanel.setLayout(rightLayout)

        # Group 1: Video selection (button + path display)
        videoGroup = QGroupBox("Video Selection")
        videoGroupLayout = QGridLayout()
        videoGroupLayout.setHorizontalSpacing(10)
        videoGroupLayout.setVerticalSpacing(8)
        videoGroup.setLayout(videoGroupLayout)
        # Prevent this box from stretching vertically beyond its contents
        videoGroup.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        videoGroupLayout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        # Layout choice: grid aligns label, button, and path display neatly and resizes well
        self.selectVodButton = QPushButton("Select VOD File…")
        self.selectVodButton.setObjectName("primaryButton")
        self.selectVodButton.clicked.connect(self.selectVodFile)
        self.vodPathDisplay = QLineEdit()
        self.vodPathDisplay.setPlaceholderText("No file selected")
        self.vodPathDisplay.setReadOnly(True)
        self.vodPathDisplay.setMinimumWidth(400)
        videoGroupLayout.addWidget(QLabel("File:"), 0, 0)
        videoGroupLayout.addWidget(self.vodPathDisplay, 0, 1)
        videoGroupLayout.addWidget(self.selectVodButton, 0, 2)
        rightLayout.addWidget(videoGroup)

        # Group 2: Match start input
        matchGroup = QGroupBox("Match Start")
        matchLayout = QGridLayout()
        matchLayout.setHorizontalSpacing(10)
        matchLayout.setVerticalSpacing(8)
        matchGroup.setLayout(matchLayout)
        # Keep height proportional to content
        matchGroup.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        matchLayout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        matchLayout.addWidget(QLabel("Start time (seconds):"), 0, 0)
        self.matchStartOffsetInput = QLineEdit()
        self.matchStartOffsetInput.setPlaceholderText("e.g., 123")
        self.matchStartOffsetInput.setText("0")
        self.matchStartOffsetInput.setFixedWidth(160)
        matchLayout.addWidget(self.matchStartOffsetInput, 0, 1)
        rightLayout.addWidget(matchGroup)

        # Group 3 removed: Fake event timestamps input is no longer in the GUI.
        # Events are now hard-coded in self.eventsConfig above.

        # Group 4: Clip generation controls
        controlsGroup = QGroupBox("Clip Generation")
        controlsLayout = QHBoxLayout()
        controlsLayout.setSpacing(10)
        controlsGroup.setLayout(controlsLayout)
        # Keep height proportional to content
        controlsGroup.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.generateClipsButton = QPushButton("Generate Clips")
        self.generateClipsButton.clicked.connect(self.generateClips)
        self.statusLabel = QLabel("")
        self.statusLabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        controlsLayout.addWidget(self.generateClipsButton)
        controlsLayout.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))
        controlsLayout.addWidget(self.statusLabel)
        rightLayout.addWidget(controlsGroup)

        # Group 5: Generated clips list (interactive)
        clipsGroup = QGroupBox("Generated Clips")
        clipsGroup.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        clipsGroup.setMaximumHeight(150)
        clipsLayout = QVBoxLayout()
        clipsLayout.setSpacing(8)
        clipsGroup.setLayout(clipsLayout)
        self.clipsListWidget = QListWidget()
        self.clipsListWidget.setAlternatingRowColors(True)
        self.clipsListWidget.setUniformItemSizes(True)
        # Keep this section compact; user can scroll
        self.clipsListWidget.setMinimumHeight(70)
        self.clipsListWidget.setMaximumHeight(110)
        self.clipsListWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.clipsListWidget.customContextMenuRequested.connect(self.onClipsContextMenu)
        # Double-click to play inside the in-app viewer
        self.clipsListWidget.itemDoubleClicked.connect(self.onPlaySelectedClip)
        self.clipsListWidget.currentRowChanged.connect(self.onListRowChanged)
        clipsLayout.addWidget(self.clipsListWidget)
        rightLayout.addWidget(clipsGroup)
        # Consume remaining vertical space with a stretch so groups don't expand
        rightLayout.addStretch(1)

        # Group 6: In-app clip viewer (plays one clip at a time)
        viewerGroup = QGroupBox("Clip Viewer")
        viewerGroup.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        viewerLayout = QVBoxLayout()
        viewerLayout.setSpacing(8)
        viewerGroup.setLayout(viewerLayout)

        # Where to adjust player UI sizing/aspect: size policies and minimum sizes
        self.videoWidget = QVideoWidget()
        self.videoWidget.setMinimumHeight(520)
        self.videoWidget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        viewerLayout.addWidget(self.videoWidget)

        # Player transport controls row (Play/Pause, Stop, Previous/Next, Seek)
        controlsRow = QHBoxLayout()
        controlsRow.setSpacing(8)
        self.playPauseButton = QPushButton("Play")
        self.playPauseButton.clicked.connect(self.onTogglePlayPause)
        self.stopButton = QPushButton("Stop")
        self.stopButton.clicked.connect(self.onStop)
        self.prevButton = QPushButton("Previous")
        self.prevButton.clicked.connect(self.onPrevClip)
        self.nextButton = QPushButton("Next")
        self.nextButton.clicked.connect(self.onNextClip)
        # Initially disabled until we have clips
        self.prevButton.setEnabled(False)
        self.nextButton.setEnabled(False)
        self.positionSlider = QSlider(Qt.Orientation.Horizontal)
        self.positionSlider.setRange(0, 0)
        # Where to adjust seek behavior: slider moves the playback position in ms
        self.positionSlider.sliderMoved.connect(self.onSeek)
        self.timeLabel = QLabel("00:00 / 00:00")
        controlsRow.addWidget(self.playPauseButton)
        controlsRow.addWidget(self.stopButton)
        controlsRow.addWidget(self.prevButton)
        controlsRow.addWidget(self.nextButton)
        controlsRow.addWidget(self.positionSlider, 1)
        controlsRow.addWidget(self.timeLabel)
        viewerLayout.addLayout(controlsRow)

        # Metadata label under the player
        self.metadataLabel = QLabel("")
        self.metadataLabel.setObjectName("metadata")
        viewerLayout.addWidget(self.metadataLabel)

        splitter.addWidget(viewerGroup)
        splitter.addWidget(rightPanel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        # Initialize the media player with audio output
        self.audioOutput = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audioOutput)
        self.player.setVideoOutput(self.videoWidget)
        # Where to adjust player settings: volume and playback rate
        self.audioOutput.setVolume(0.8)  # 0.0 - 1.0
        self.player.setPlaybackRate(1.0)  # normal speed
        # Player event wiring for controls and end-of-media behavior
        self.player.positionChanged.connect(self.onPlayerPositionChanged)
        self.player.durationChanged.connect(self.onPlayerDurationChanged)
        self.player.mediaStatusChanged.connect(self.onPlayerMediaStatusChanged)
        self.player.playbackStateChanged.connect(self.onPlayerStateChanged)
        try:
            self.player.errorOccurred.connect(self.onPlayerError)  # PyQt6 >= 6.5
        except Exception:
            pass

    def ensureClipsFolderExists(self) -> None:
        clipsDir = os.path.join(self.projectRoot(), "clips")
        os.makedirs(clipsDir, exist_ok=True)

    def projectRoot(self) -> str:
        return os.path.dirname(os.path.abspath(sys.argv[0]))

    def selectVodFile(self) -> None:
        filePath, _ = QFileDialog.getOpenFileName(
            self,
            "Select VOD File",
            os.path.expanduser("~"),
            "Video Files (*.mp4 *.mkv *.mov *.flv *.ts);;All Files (*.*)",
        )
        if filePath:
            self.vodFilePath = filePath
            self.vodPathDisplay.setText(filePath)

    # Fake timestamps parser removed; events are configured in self.eventsConfig

    def generateClips(self) -> None:
        if not self.vodFilePath or not os.path.isfile(self.vodFilePath):
            QMessageBox.warning(self, "Missing VOD", "Please select a valid VOD file.")
            return

        offsetText = self.matchStartOffsetInput.text().strip()
        try:
            matchStartOffsetSeconds = int(float(offsetText)) if offsetText else 0
        except ValueError:
            QMessageBox.warning(self, "Invalid Offset", "Enter a numeric offset in seconds.")
            return

        # Build events list for the worker from the hard-coded config.
        # How video-relative timestamps are computed: the worker will add matchStartOffsetSeconds
        # to each event's 'time' to create absolute timestamps for FFmpeg cuts.
        events = list(self.eventsConfig)

        outputDir = os.path.join(self.projectRoot(), "clips")
        os.makedirs(outputDir, exist_ok=True)
        self.currentOutputDir = outputDir

        self.clipsListWidget.clear()
        self.setUiBusy(True)
        self.statusLabel.setText("Generating clips...")

        # Worker setup to keep GUI responsive
        self.workerThread = QThread(self)
        # Where to adjust clip duration window around each event
        preSeconds = 5
        postSeconds = 5

        self.worker = ClipExtractionWorker(
            vodPath=self.vodFilePath,
            matchStartOffsetSeconds=matchStartOffsetSeconds,
            events=events,
            outputDir=outputDir,
            preSeconds=preSeconds,
            postSeconds=postSeconds,
        )

        self.worker.moveToThread(self.workerThread)
        self.workerThread.started.connect(self.worker.run)
        self.worker.clipGenerated.connect(self.onClipGenerated)
        self.worker.progressUpdated.connect(self.onProgress)
        self.worker.errorOccurred.connect(self.onError)
        self.worker.finished.connect(self.onFinished)
        self.worker.finished.connect(self.workerThread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.workerThread.finished.connect(self.workerThread.deleteLater)

        self.workerThread.start()

    def setUiBusy(self, isBusy: bool) -> None:
        self.generateClipsButton.setEnabled(not isBusy)
        self.selectVodButton.setEnabled(not isBusy)
        self.matchStartOffsetInput.setEnabled(not isBusy)
        # No longer applicable: fake timestamps input removed

    def onClipGenerated(self, clipFilename: str, clipStartSeconds: float) -> None:
        # Interactive list item: store metadata for viewer and actions
        fullPath = os.path.join(self.currentOutputDir, clipFilename) if self.currentOutputDir else clipFilename
        item = QListWidgetItem(clipFilename)
        # Store full path and start time for actions and metadata display
        item.setData(Qt.ItemDataRole.UserRole, {"path": fullPath, "start": float(clipStartSeconds)})
        self.clipsListWidget.addItem(item)
        # Auto-select and play the first generated clip
        if self.currentClipIndex == -1:
            self.loadClipAtIndex(0)
        else:
            # Ensure navigation buttons reflect the growing list
            self.updateNavButtons()

    def onProgress(self, message: str) -> None:
        self.statusLabel.setText(message)

    def onError(self, message: str) -> None:
        QMessageBox.critical(self, "Error", message)

    def onFinished(self) -> None:
        self.statusLabel.setText("Done.")
        self.setUiBusy(False)
        # Refresh nav buttons in case more clips were added
        self.updateNavButtons()

    # --- Viewer and list interactions ---
    def onPlaySelectedClip(self) -> None:
        index = self.clipsListWidget.currentRow()
        if index < 0:
            return
        self.loadClipAtIndex(index)

    def onPrevClip(self) -> None:
        if self.clipsListWidget.count() == 0:
            return
        newIndex = max(0, (self.currentClipIndex if self.currentClipIndex >= 0 else 0) - 1)
        self.loadClipAtIndex(newIndex)

    def onNextClip(self) -> None:
        if self.clipsListWidget.count() == 0:
            return
        newIndex = min(self.clipsListWidget.count() - 1, (self.currentClipIndex if self.currentClipIndex >= 0 else 0) + 1)
        self.loadClipAtIndex(newIndex)

    def loadClipAtIndex(self, index: int) -> None:
        if index < 0 or index >= self.clipsListWidget.count():
            return
        item = self.clipsListWidget.item(index)
        data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return
        fullPath = data.get("path", "")
        start = float(data.get("start", 0.0))
        if not fullPath:
            return
        # Set media source and play. GUI remains responsive while playback occurs.
        if self.player:
            self.player.setSource(QUrl.fromLocalFile(fullPath))
            self.player.play()
        # Highlight current clip in list
        self.clipsListWidget.setCurrentRow(index)
        self.currentClipIndex = index
        self.updateNavButtons()
        self.updateMetadata(os.path.basename(fullPath), start)
        # Ensure focus on viewer so keyboard space toggles play/pause
        if self.videoWidget:
            self.videoWidget.setFocus()

    def updateNavButtons(self) -> None:
        count = self.clipsListWidget.count()
        if count <= 0:
            self.prevButton.setEnabled(False)
            self.nextButton.setEnabled(False)
            return
        # If nothing selected yet, enable next if there is at least one clip
        if self.currentClipIndex < 0:
            self.prevButton.setEnabled(False)
            self.nextButton.setEnabled(count > 1)
            return
        atStart = self.currentClipIndex <= 0
        atEnd = self.currentClipIndex >= (count - 1)
        self.prevButton.setEnabled(not atStart)
        self.nextButton.setEnabled(not atEnd)

    def updateMetadata(self, filename: str, startSeconds: float) -> None:
        # Where to adjust metadata formatting
        self.metadataLabel.setText(f"{filename}  •  start: {int(startSeconds)}s")

    def setupStyles(self) -> None:
        # Layout choice: styles improve readability and spacing while keeping native feel
        baseFont = QFont()
        baseFont.setPointSize(10)
        self.setFont(baseFont)
        self.setStyleSheet(
            """
            QGroupBox {
                font-weight: 600;
                border: 1px solid palette(mid);
                border-radius: 6px;
                margin-top: 12px;
                padding: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLabel { color: palette(WindowText); }
            QLineEdit, QPlainTextEdit {
                padding: 6px 8px;
                color: palette(Text);
                background: palette(Base);
                border: 1px solid palette(mid);
                border-radius: 4px;
            }
            QPushButton#primaryButton {
                font-weight: 600;
            }
            QPushButton { padding: 6px 12px; }
            QListWidget {
                border: 1px solid palette(mid);
                background: palette(Base);
                color: palette(Text);
            }
            """
        )

    def onClipsContextMenu(self, pos) -> None:
        item = self.clipsListWidget.itemAt(pos)
        if item is None:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        fullPath = data.get("path") if isinstance(data, dict) else data
        menu = QMenu(self)
        openAction = menu.addAction("Open Clip")
        revealAction = menu.addAction("Open Containing Folder")
        copyPathAction = menu.addAction("Copy Path")
        chosen = menu.exec(self.clipsListWidget.mapToGlobal(pos))
        if chosen is openAction:
            self.openPath(fullPath)
        elif chosen is revealAction:
            self.revealInFolder(fullPath)
        elif chosen is copyPathAction:
            self.copyToClipboard(fullPath)

    def onOpenSelectedClip(self) -> None:
        item = self.clipsListWidget.currentItem()
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        fullPath = data.get("path") if isinstance(data, dict) else data
        self.openPath(fullPath)

    def onListRowChanged(self, row: int) -> None:
        # Synchronize current index when user navigates via keyboard or mouse
        if row < 0:
            return
        self.currentClipIndex = row
        self.updateNavButtons()

    def openPath(self, path: str) -> None:
        if not path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def revealInFolder(self, path: str) -> None:
        if not path:
            return
        folder = os.path.dirname(path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def copyToClipboard(self, text: str) -> None:
        if not text:
            return
        QApplication.clipboard().setText(text)

    # --- Player controls ---
    def onTogglePlayPause(self) -> None:
        if not self.player:
            return
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            # If we are at the end, ensure we restart from beginning
            dur = self.player.duration()
            pos = self.player.position()
            if dur > 0 and pos >= dur:
                self.player.setPosition(0)
            self.player.play()

    def onStop(self) -> None:
        if not self.player:
            return
        self.player.stop()
        self.positionSlider.setValue(0)
        self.updateTimeLabel(0, self.player.duration())

    def onSeek(self, positionMs: int) -> None:
        if self.player:
            self.player.setPosition(int(positionMs))

    def onPlayerPositionChanged(self, positionMs: int) -> None:
        # Keep slider in sync with playback
        self.positionSlider.blockSignals(True)
        self.positionSlider.setValue(int(positionMs))
        self.positionSlider.blockSignals(False)
        self.updateTimeLabel(positionMs, self.player.duration() if self.player else 0)

    def onPlayerDurationChanged(self, durationMs: int) -> None:
        self.positionSlider.setRange(0, int(durationMs))
        self.updateTimeLabel(self.player.position() if self.player else 0, durationMs)

    def onPlayerMediaStatusChanged(self, status) -> None:
        # End-of-media: stop auto-looping; keep ready to replay
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.player:
                self.player.pause()
                self.player.setPosition(0)
        # Update play button text for consistency
        self.onPlayerStateChanged(self.player.playbackState() if self.player else QMediaPlayer.PlaybackState.StoppedState)

    def onPlayerStateChanged(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.playPauseButton.setText("Pause")
        else:
            self.playPauseButton.setText("Play")

    def onPlayerError(self, error, errorString: str) -> None:
        if error:
            self.statusLabel.setText(f"Player error: {errorString}")

    def updateTimeLabel(self, positionMs: int, durationMs: int) -> None:
        def fmt(ms: int) -> str:
            totalSeconds = max(0, int(ms // 1000))
            minutes = totalSeconds // 60
            seconds = totalSeconds % 60
            return f"{minutes:02d}:{seconds:02d}"
        self.timeLabel.setText(f"{fmt(positionMs)} / {fmt(durationMs)}")

    # --- End player controls ---


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()



