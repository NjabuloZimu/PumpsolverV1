"""Fixed-size controls stay centred while windows grow or clip symmetrically."""

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QApplication, QDialog, QMainWindow, QMessageBox, QWidget

from test_csv_io import project_state


WINDOW_KINDS = ("main", "properties", "motor", "designer", "solve", "about", "help", "info1", "info2", "info3")


@pytest.fixture
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_window(kind, state):
    if kind == "main":
        from callmain import MyForm
        return MyForm()
    if kind == "properties":
        from callproperties import Properties
        return Properties("Inlet Properties", False)
    if kind == "motor":
        from callmotorProp import MotorProp
        return MotorProp()
    if kind == "designer":
        from callLossesCal import LossesCal
        return LossesCal("Inlet Pipe Fittings Losses Designer")
    if kind == "solve":
        from callsolvePage import SolvePage
        return SolvePage(copy.deepcopy(state["parameters"]))
    if kind == "about":
        from callabout import About
        return About()
    if kind == "help":
        from callhelp import Help
        return Help()
    if kind == "info1":
        from callInfo1 import Info1
        return Info1()
    if kind == "info2":
        from callInfo2 import Info2
        return Info2()
    from callInfo3 import Info3
    return Info3()


def _close_window(window):
    window.close()
    if hasattr(type(window), "windows") and window in type(window).windows:
        type(window).windows.remove(window)


def _flush(app):
    app.processEvents()
    app.processEvents()


def _control_snapshot(window, canvas):
    """Record authored widgets, excluding Qt internals and main-window chrome."""
    snapshot = {}
    for name, widget in vars(window.ui).items():
        if not isinstance(widget, QWidget) or widget is canvas or not canvas.isAncestorOf(widget):
            continue
        point = widget.mapTo(canvas, QPoint(0, 0))
        record = [point.x(), point.y(), widget.width(), widget.height(), widget.font().toString()]
        if hasattr(widget, "iconSize"):
            record.append((widget.iconSize().width(), widget.iconSize().height()))
        if hasattr(widget, "pixmap"):
            pixmap = widget.pixmap()
            if pixmap is not None:
                record.append((pixmap.width(), pixmap.height()))
        snapshot[name] = record
    assert snapshot, "The original controls must remain inside the centred canvas"
    return snapshot


def _resize_viewport(window, viewport, width, height, app):
    chrome_width = window.width() - viewport.width()
    chrome_height = window.height() - viewport.height()
    window.resize(width + chrome_width, height + chrome_height)
    _flush(app)
    assert abs(viewport.width() - width) <= 1
    assert abs(viewport.height() - height) <= 1


def _assert_centred(viewport, canvas):
    assert abs(2 * canvas.x() + canvas.width() - viewport.width()) <= 1
    assert abs(2 * canvas.y() + canvas.height() - viewport.height()) <= 1


def _tab_order(window, ui):
    names = {widget: name for name, widget in vars(ui).items()
             if isinstance(widget, QWidget) and widget.focusPolicy() & Qt.TabFocus
             and not widget.isWindow()}
    order, visited = [], set()
    current = window.nextInFocusChain()
    while current is not window and current not in visited:
        visited.add(current)
        if current in names:
            order.append(names[current])
        current = current.nextInFocusChain()
    return order


def _same_cyclic_order(first, second):
    if not first:
        return not second
    if len(first) != len(second) or first[0] not in second:
        return False
    start = second.index(first[0])
    return first == second[start:] + second[:start]


@pytest.mark.parametrize("kind", WINDOW_KINDS)
def test_all_windows_keep_control_sizes_and_centre_at_each_window_size(kind, qt_app, monkeypatch, project_state):
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: errors.append(args[2]))
    monkeypatch.setattr(QMessageBox, "exec_", lambda self: errors.append(self.text()))
    window = _make_window(kind, project_state)
    try:
        window.show()
        _flush(qt_app)
        viewport = window._centered_viewport
        canvas = viewport.canvas
        original_size = canvas.size()
        original_controls = _control_snapshot(window, canvas)
        raw_window = QMainWindow() if isinstance(window, QMainWindow) else QDialog()
        try:
            raw_ui = type(window.ui)()
            raw_ui.setupUi(raw_window)
            assert _same_cyclic_order(_tab_order(raw_window, raw_ui), _tab_order(window, window.ui))
            authored_visibility = {name: not widget.isHidden() for name, widget in vars(raw_ui).items()
                                   if name in original_controls}
        finally:
            raw_window.close()
        width, height = original_size.width(), original_size.height()
        # Returning through earlier sizes also detects cumulative position drift.
        sizes = [(width + 420, height + 240), (width + 64, height + 48),
                 (width - 120, height - 96), (width + 64, height + 48),
                 (width - 120, height - 96), (width + 420, height + 240)]
        for requested_width, requested_height in sizes:
            _resize_viewport(window, viewport, requested_width, requested_height, qt_app)
            assert canvas.size() == original_size
            assert _control_snapshot(window, canvas) == original_controls
            _assert_centred(viewport, canvas)
            if requested_width >= width and requested_height >= height:
                assert viewport.rect().contains(canvas.geometry()), "Content clipped before it stopped fitting"
                for name, visible in authored_visibility.items():
                    assert getattr(window.ui, name).isVisible() is visible
            else:
                assert canvas.x() < 0 and canvas.y() < 0
                assert canvas.geometry().right() >= viewport.rect().right()
                assert canvas.geometry().bottom() >= viewport.rect().bottom()
        assert not errors
        if isinstance(window, QMainWindow):
            assert window.centralWidget() is viewport
            assert not canvas.isAncestorOf(window.menuBar())
            assert not canvas.isAncestorOf(window.statusBar())
            assert window.menuBar().isVisible()
            assert window.menuBar().width() >= viewport.width() - 2
    finally:
        _close_window(window)


def test_reparented_property_controls_still_edit_and_emit_after_resizing(qt_app, project_state):
    from PyQt5.QtTest import QTest
    window = _make_window("properties", project_state)
    submitted = []
    window.submitClicked.connect(lambda *values: submitted.append(values))
    try:
        window.show()
        _flush(qt_app)
        viewport = window._centered_viewport
        canvas = viewport.canvas
        original = _control_snapshot(window, canvas)
        width, height = canvas.width(), canvas.height()
        _resize_viewport(window, viewport, width + 240, height + 160, qt_app)
        _resize_viewport(window, viewport, width - 100, height - 80, qt_app)
        _resize_viewport(window, viewport, width + 100, height + 80, qt_app)
        window.ui.lineEditHead.setFocus()
        QTest.keyClicks(window.ui.lineEditHead, "12.5")
        assert window.ui.pushButtonApply.isEnabled()
        window.ui.pushButtonApply.click()
        assert submitted and submitted[0][0]["head"] == "12.5"
        assert window.ui.lineEditHead.text() == "12.5"
        assert _control_snapshot(window, canvas) == original
        _assert_centred(viewport, canvas)
    finally:
        _close_window(window)
