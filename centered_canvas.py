"""Centre existing Designer controls without resizing their authored geometry."""

from PyQt5.QtCore import QEvent, QRect, Qt
from PyQt5.QtWidgets import QMainWindow, QSizeGrip, QSizePolicy, QWidget


class _CenteredViewport(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = None
        # A fixed child must not impose its minimum size on the outer window.
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

    def center_canvas(self):
        if self.canvas is not None:
            area = self.contentsRect()
            self.canvas.move(
                area.x() + (area.width() - self.canvas.width()) // 2,
                area.y() + (area.height() - self.canvas.height()) // 2,
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Negative offsets deliberately clip symmetrically below content size.
        self.center_canvas()

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Resize:
            self.setGeometry(watched.contentsRect())
            self.center_canvas()
        return super().eventFilter(watched, event)


def _controls(parent):
    return [widget for widget in parent.findChildren(QWidget, options=Qt.FindDirectChildrenOnly)
            if not widget.isWindow() and not isinstance(widget, QSizeGrip)]


def _control_bounds(controls):
    bounds = QRect()
    for widget in controls:
        if not widget.geometry().isEmpty():
            bounds = bounds.united(widget.geometry())
    return bounds


def _focus_order(window):
    """Remember nested tab stops before dialog controls change parent."""
    result = []
    visited = set()
    widget = window.nextInFocusChain()
    while widget is not window and widget not in visited:
        visited.add(widget)
        if (widget.focusPolicy() != Qt.NoFocus and not isinstance(widget, QSizeGrip)
                and window.isAncestorOf(widget) and not widget.isWindow()):
            result.append(widget)
        widget = widget.nextInFocusChain()
    return result


def center_window_contents(window):
    """Wrap an absolute-positioned main window or dialog in a centred canvas.

    Designer files remain the source of control dimensions. The wrapper removes
    only the surrounding authored margin, then centres the fixed content in the
    available client area. It can be called again safely on the same window.
    """
    existing = getattr(window, "_centered_viewport", None)
    if existing is not None:
        return existing

    is_main_window = isinstance(window, QMainWindow)
    source = window.centralWidget() if is_main_window else window
    if source is None:
        return None
    controls = _controls(source)
    bounds = _control_bounds(controls)
    if bounds.isEmpty():
        return None

    focus_order = _focus_order(window) if not is_main_window else []
    viewport = _CenteredViewport(window)
    viewport.setObjectName("centeredViewport")

    if is_main_window:
        canvas = window.takeCentralWidget()
        canvas.setParent(viewport)
        for widget in controls:
            widget.move(widget.pos() - bounds.topLeft())
        window.setCentralWidget(viewport)
    else:
        canvas = QWidget(viewport)
        canvas.setObjectName("centeredContent")
        for widget in controls:
            position = widget.pos() - bounds.topLeft()
            # setParent hides widgets; retain explicit hidden states rather
            # than treating a not-yet-shown dialog as entirely hidden.
            hidden = widget.isHidden()
            widget.setParent(canvas)
            widget.move(position)
            widget.setVisible(not hidden)
        for previous, following in zip(focus_order, focus_order[1:]):
            QWidget.setTabOrder(previous, following)
        window.installEventFilter(viewport)
        viewport.setGeometry(window.contentsRect())

    canvas.setFixedSize(bounds.size())
    viewport.canvas = canvas
    window._centered_viewport = viewport
    canvas.show()
    viewport.show()
    for grip in window.findChildren(QSizeGrip, options=Qt.FindDirectChildrenOnly):
        grip.raise_()
    viewport.center_canvas()
    return viewport
