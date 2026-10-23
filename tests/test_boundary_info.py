"""The editable reference popup explains the boundary loss controls."""

from pumpsolver.gui.boundary_info_dialog import BoundaryLossInfo


def test_boundary_reference_contains_equations_units_and_geometry_guidance(qt_app):
    window = BoundaryLossInfo()
    try:
        browser = window.ui.textBrowserBoundaryInfo
        text = browser.toPlainText()
        for phrase in ("hL", "Δp", "ρ", "m/s", "kg/m", "Pa", "dimensionless",
                       "first segment", "last segment", "0.5", "0.02–0.2",
                       "0.78–0.8", "0.5–0.7", "1.0", "geometry"):
            assert phrase.lower() in text.lower(), phrase
        assert browser.isReadOnly()
        assert browser.openExternalLinks()
        html = browser.toHtml()
        assert "hec.usace.army.mil" in html
        assert "innovationspace.ansys.com" in html
        assert "fluids.readthedocs.io" in html
        assert "h<sub>L</sub>" in html or "vertical-align:sub" in html
    finally:
        window.close()
        window.deleteLater()


def test_boundary_reference_scrolls_centres_without_scaling_and_closes(qt_app):
    window = BoundaryLossInfo()
    try:
        window.show()
        qt_app.processEvents()
        browser = window.ui.textBrowserBoundaryInfo
        size = browser.size()
        assert browser.verticalScrollBar().maximum() > 0
        viewport = window._centered_viewport
        window.resize(window.width() + 220, window.height() + 160)
        qt_app.processEvents()
        assert browser.size() == size
        assert abs(2 * viewport.canvas.x() + viewport.canvas.width() - viewport.width()) <= 1
        assert abs(2 * viewport.canvas.y() + viewport.canvas.height() - viewport.height()) <= 1
        window.ui.pushButtonClose.click()
        qt_app.processEvents()
        assert not window.isVisible()
    finally:
        window.close()
        window.deleteLater()
