import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAccessible
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox

from study_agent.switch import AppleSwitch
from study_agent.theme import SWITCH_METRICS


@pytest.fixture
def qapp(monkeypatch: pytest.MonkeyPatch) -> QApplication:
    monkeypatch.setenv("QT_QPA_PLATFORM", "minimal")
    return QApplication.instance() or QApplication([])


def test_switch_is_accessible_and_works_by_keyboard_and_label(qapp: QApplication) -> None:
    switch = AppleSwitch("Повышенный контраст", reduce_motion=True)
    switch.resize(switch.sizeHint())
    switch.show()
    qapp.processEvents()

    accessible = QAccessible.queryAccessibleInterface(switch)
    assert isinstance(switch, QCheckBox)
    assert accessible.role() == QAccessible.Role.CheckBox
    assert switch.accessibleName() == "Повышенный контраст"

    QTest.keyClick(switch, Qt.Key.Key_Space)
    assert switch.isChecked() and switch.progress == 1
    assert accessible.state().checked

    label_point = QPoint(switch.width() - 8, switch.height() // 2)
    QTest.mouseClick(switch, Qt.MouseButton.LeftButton, pos=label_point)
    assert not switch.isChecked() and switch.progress == 0
    assert not accessible.state().checked

    switch.setChecked(True)
    assert switch.isChecked() and switch.progress == 1
    switch.close()


def test_switch_animation_respects_reduce_motion_and_disabled_state(
    qapp: QApplication,
) -> None:
    switch = AppleSwitch("Уменьшить движение", reduce_motion=True)
    switch.show()
    switch.setChecked(True)
    assert switch.progress == 1

    switch.set_reduce_motion(False)
    switch.setChecked(False)
    QTest.qWait(220)
    assert switch.progress == 0

    switch.set_reduce_motion(True)
    switch.setChecked(True)
    assert switch.progress == 1
    switch.setEnabled(False)
    switch.click()
    assert switch.isChecked() and switch.progress == 1
    switch.close()


def test_regular_and_compact_switch_sizes() -> None:
    regular = SWITCH_METRICS["regular"]
    compact = SWITCH_METRICS["compact"]
    assert 48 <= regular.width <= 54
    assert 28 <= regular.height <= 32
    assert compact.width < regular.width
    assert compact.height < regular.height
