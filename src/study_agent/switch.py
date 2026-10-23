"""A compact, accessible two-state switch rendered with Qt primitives."""

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QCheckBox, QWidget

from study_agent.theme import SWITCH_METRICS


class AppleSwitch(QCheckBox):
    """A checkbox with a switch appearance and the native Qt checkbox semantics."""

    def __init__(
        self,
        text: str,
        parent: QWidget | None = None,
        *,
        compact: bool = False,
        reduce_motion: bool = False,
    ) -> None:
        super().__init__(text, parent)
        self.setTristate(False)
        self.setAccessibleName(text)
        self._metrics = SWITCH_METRICS["compact" if compact else "regular"]
        self._reduce_motion = reduce_motion
        self._progress = 0.0
        self._on_color = QColor("#34C759")
        self._off_color = QColor("#8E8E93")
        self._thumb_color = QColor("#FFFFFF")
        self._border_color = QColor("#60758F")
        self._border_width = 1
        self._focus_color = QColor("#0B65F2")
        self._animation = QPropertyAnimation(self, b"progress", self)
        self._animation.setDuration(170)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_to_state)

    @Property(float)
    def progress(self) -> float:
        return self._progress

    @progress.setter
    def progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, value))
        self.update()

    def set_colors(
        self,
        *,
        on: str,
        off: str,
        thumb: str,
        border: str,
        border_width: int,
        focus: str,
    ) -> None:
        self._on_color = QColor(on)
        self._off_color = QColor(off)
        self._thumb_color = QColor(thumb)
        self._border_color = QColor(border)
        self._border_width = border_width
        self._focus_color = QColor(focus)
        self.update()

    def set_reduce_motion(self, reduce_motion: bool) -> None:
        self._reduce_motion = reduce_motion
        if reduce_motion:
            self._animation.stop()
            self.progress = float(self.isChecked())

    def sizeHint(self) -> QSize:
        metrics = self._metrics
        width = (
            metrics.focus_inset * 2
            + metrics.width
            + metrics.gap
            + self.fontMetrics().horizontalAdvance(self.text())
        )
        height = max(metrics.height, self.fontMetrics().height()) + metrics.focus_inset * 2
        return QSize(width, height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def hitButton(self, position: QPoint) -> bool:
        return self.rect().contains(position)

    def paintEvent(self, _event) -> None:
        metrics = self._metrics
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        track_x = metrics.focus_inset
        if rtl:
            track_x = self.width() - metrics.focus_inset - metrics.width
        track_y = (self.height() - metrics.height) / 2
        track = QRectF(track_x, track_y, metrics.width, metrics.height)
        diameter = metrics.height - metrics.thumb_inset * 2
        travel = metrics.width - metrics.height
        position = 1.0 - self._progress if rtl else self._progress
        thumb_x = track_x + metrics.thumb_inset + travel * position
        thumb = QRectF(
            thumb_x,
            track_y + metrics.thumb_inset,
            diameter,
            diameter,
        )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.45)
        if self.hasFocus():
            painter.setPen(QPen(self._focus_color, metrics.focus_width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            focus = track.adjusted(
                -metrics.focus_inset,
                -metrics.focus_inset,
                metrics.focus_inset,
                metrics.focus_inset,
            )
            painter.drawRoundedRect(
                focus, metrics.height / 2 + metrics.focus_inset,
                metrics.height / 2 + metrics.focus_inset,
            )

        track_color = self._interpolate(self._off_color, self._on_color, self._progress)
        painter.setPen(QPen(self._border_color, self._border_width))
        painter.setBrush(track_color)
        track_rect = track.adjusted(
            self._border_width / 2,
            self._border_width / 2,
            -self._border_width / 2,
            -self._border_width / 2,
        )
        radius = (metrics.height - self._border_width) / 2
        painter.drawRoundedRect(track_rect, radius, radius)
        painter.setBrush(self._thumb_color)
        painter.drawEllipse(thumb)

        text_x = metrics.focus_inset + metrics.width + metrics.gap
        alignment = Qt.AlignmentFlag.AlignLeft
        if rtl:
            text_x = metrics.focus_inset
            alignment = Qt.AlignmentFlag.AlignRight
        text_rect = QRectF(
            text_x,
            0,
            max(0, self.width() - metrics.width - metrics.gap - metrics.focus_inset * 2),
            self.height(),
        )
        painter.setFont(self.font())
        color_group = (
            QPalette.ColorGroup.Normal if self.isEnabled() else QPalette.ColorGroup.Disabled
        )
        painter.setPen(self.palette().color(color_group, QPalette.ColorRole.WindowText))
        painter.drawText(text_rect, alignment | Qt.AlignmentFlag.AlignVCenter, self.text())

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if hasattr(self, "_metrics") and event.type() in (
            QEvent.Type.FontChange,
            QEvent.Type.LayoutDirectionChange,
        ):
            self.updateGeometry()

    def _animate_to_state(self, checked: bool) -> None:
        self._animation.stop()
        target = float(checked)
        if self._reduce_motion:
            self.progress = target
            return
        self._animation.setStartValue(self._progress)
        self._animation.setEndValue(target)
        self._animation.start()

    @staticmethod
    def _interpolate(start: QColor, end: QColor, progress: float) -> QColor:
        channels = (
            round(a + (b - a) * progress)
            for a, b in zip(start.getRgb(), end.getRgb(), strict=True)
        )
        return QColor(*channels)
