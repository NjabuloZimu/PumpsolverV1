"""Designer recovery and generation must preserve the authored interface."""

import importlib
import importlib.util
import copy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from PyQt5.QtCore import QFile, QIODevice, QSize
from PyQt5.QtGui import QCursor, QIcon
from PyQt5.QtWidgets import QDialog, QLayout, QMainWindow, QWidget


ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "src" / "pumpsolver" / "gui"
SNAPSHOTS = json.loads((GUI / "forms" / "legacy_layout_snapshot.json").read_text(encoding="utf-8"))


def _snapshot(ui, window, properties):
    result = {}
    for name, obj in [("$root", window), *vars(ui).items()]:
        if not isinstance(obj, (QWidget, QLayout)):
            continue
        data = {"class": type(obj).__name__, "name": obj.objectName(),
                "parent": obj.parent().objectName() if obj.parent() else ""}
        selected = properties.get(name, [])
        if isinstance(obj, QWidget):
            state = {}
            for prop in selected:
                if prop in ("font", "geometry") or obj.metaObject().indexOfProperty(prop) < 0:
                    continue
                value = obj.property(prop)
                if isinstance(value, QSize):
                    state[prop] = [value.width(), value.height()]
                elif isinstance(value, QCursor):
                    state[prop] = int(value.shape())
                elif isinstance(value, QIcon):
                    state[prop] = not value.isNull()
                elif isinstance(value, (str, bool, int, float)):
                    state[prop] = value
                elif value is not None and type(value).__module__.startswith("PyQt5"):
                    try:
                        state[prop] = int(value)
                    except TypeError:
                        pass
            data["state"] = state
            if "geometry" in selected:
                data["geometry"] = [obj.x(), obj.y(), obj.width(), obj.height()]
            if "font" in selected:
                font = obj.font()
                values = {"pointSize": font.pointSizeF(), "bold": font.bold(),
                          "italic": font.italic(), "underline": font.underline(),
                          "weight": font.weight(), "styleStrategy": int(font.styleStrategy())}
                data["font"] = {key: value for key, value in values.items() if "font:" + key in selected}
            if "iconSize" in selected:
                data["iconSize"] = [obj.iconSize().width(), obj.iconSize().height()]
            for prop in ("enabled", "flat", "autoDefault", "default", "clearButtonEnabled",
                         "checkable", "autoExclusive", "scaledContents", "wordWrap",
                         "selectionBehavior", "editable", "modelColumn"):
                if prop in selected and hasattr(obj, prop):
                    value = getattr(obj, prop)()
                    data[prop] = int(value) if type(value).__module__.startswith("PyQt5") else value
            if hasattr(obj, "text"):
                data["text"] = obj.text()
            if hasattr(obj, "title"):
                data["title"] = obj.title()
            if hasattr(obj, "count") and hasattr(obj, "itemText"):
                data["items"] = [obj.itemText(i) for i in range(obj.count())]
            if hasattr(obj, "rowCount"):
                data["table"] = {
                    "rows": obj.rowCount(), "columns": obj.columnCount(),
                    "headers": [obj.horizontalHeaderItem(i).text() if obj.horizontalHeaderItem(i) else ""
                                for i in range(obj.columnCount())],
                    "headerDefault": obj.horizontalHeader().defaultSectionSize(),
                    "headerMinimum": obj.horizontalHeader().minimumSectionSize(),
                    # Parent visibility is false during setupUi; isHidden()
                    # records whether a header was explicitly hidden instead.
                    "horizontalHeaderHidden": obj.horizontalHeader().isHidden(),
                    "verticalHeaderHidden": obj.verticalHeader().isHidden(),
                }
            if hasattr(obj, "pixmap"):
                pixmap = obj.pixmap()
                data["pixmapSize"] = None if pixmap is None or pixmap.isNull() else [pixmap.width(), pixmap.height()]
        result[name] = data
    return result


@pytest.mark.parametrize("module_name", sorted(SNAPSHOTS))
def test_recovered_forms_preserve_authored_controls(qt_app, module_name):
    expected = SNAPSHOTS[module_name]
    module = importlib.import_module("pumpsolver.gui.generated." + module_name)
    ui = getattr(module, expected["class"])()
    window = QMainWindow() if module_name == "ui_main_window" else QDialog()
    try:
        ui.setupUi(window)
        assert _snapshot(ui, window, expected["properties"]) == expected["widgets"]
    finally:
        window.close()
        window.deleteLater()


def test_all_forms_and_resource_sources_are_in_repository():
    forms = list((GUI / "forms").glob("*.ui"))
    assert len(forms) == 10
    for form in forms:
        source = ET.parse(form)
        for include in source.findall(".//resources/include"):
            resource = (form.parent / include.attrib["location"]).resolve()
            assert resource.is_relative_to(GUI.resolve())
            assert resource.is_file()
        for image in [*source.findall(".//pixmap"), *source.findall(".//iconset/normaloff")]:
            assert image.text.startswith(":/"), (form, image.text)


def test_compiled_resources_match_source_bytes(qt_app):
    from pumpsolver.gui.generated import resources_rc  # noqa: F401
    source = GUI / "assets" / "assets.qrc"
    for collection in ET.parse(source).findall("qresource"):
        for entry in collection.findall("file"):
            resource = QFile(":" + collection.attrib["prefix"] + entry.attrib["alias"])
            assert resource.open(QIODevice.ReadOnly), entry.attrib["alias"]
            try:
                assert bytes(resource.readAll()) == (source.parent / entry.text).read_bytes()
            finally:
                resource.close()


def test_generated_modules_are_reproducible():
    spec = importlib.util.spec_from_file_location("pumpsolver_generate_ui", ROOT / "tools" / "generate_ui.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    for path, expected in generator.generated_files().items():
        assert path.read_bytes().replace(b"\r\n", b"\n") == expected, path


def test_designer_checkbox_preserves_original_connections(qt_app):
    from pumpsolver.gui.generated.ui_pipe_designer import Ui_LineLossesDesigner
    window = QDialog()
    ui = Ui_LineLossesDesigner()
    ui.setupUi(window)
    names = ("tableWidgetPipeSegment", "pushButtonAddSegment", "pushButtonDeleteSegment",
             "pushButtonImportSegment", "pushButtonExportSegment", "pushButtonExportLineRoughness",
             "pushButtonImportLineRoughness", "comboBoxTransitionEquation", "labelBoundaryEquation",
             "pushButtonImportFittings", "pushButtonExportFittings")
    try:
        ui.checkBoxLossesCal.click()
        assert all(getattr(ui, name).isEnabled() for name in names)
        ui.checkBoxLossesCal.click()
        assert not any(getattr(ui, name).isEnabled() for name in names)
    finally:
        window.close()
        window.deleteLater()


def test_windows_application_icon_loads_at_packaging_sizes(qt_app):
    icon = QIcon(str(GUI / "assets" / "pumpsolver.ico"))
    assert not icon.isNull()
    assert {size.width() for size in icon.availableSizes()} == {16, 32, 48, 64, 128, 256}
    assert not icon.pixmap(256, 256).isNull()


@pytest.mark.parametrize("populated", [False, True])
def test_designer_headings_and_units_remain_visible_after_open_and_reopen(qt_app, project_state, populated):
    from pumpsolver.gui.pipe_designer import LossesCal

    for _ in range(2):
        window = LossesCal("Inlet Pipe Fittings Losses Designer", side="inlet")
        try:
            if populated:
                design = copy.deepcopy(project_state["inlet"])
                window.previously_stored_data(design["segments"], design["fittings"], design["roughness"])
            window.show()
            qt_app.processEvents()
            segments = window.ui.tableWidgetPipeSegment
            fittings = window.ui.tableWidgetFittings
            if populated:
                segments.selectRow(0)
                qt_app.processEvents()
            for table, headings, size in (
                (segments, ["Segment Length (m)", "Segment Diameter (cm)"], (391, 321)),
                (fittings, ["Fitting Type", "Loss Factor"], (321, 241)),
            ):
                assert [table.horizontalHeaderItem(i).text() for i in range(2)] == headings
                assert table.horizontalHeader().isVisible()
                assert table.horizontalHeader().height() > 0
                assert not table.verticalHeader().isHidden()
                assert (table.width(), table.height()) == size
                if populated:
                    assert table.rowCount() > 0
                    assert table.verticalHeader().isVisible()
                    assert table.verticalHeader().width() > 0
            window.hide()
            window.show()
            qt_app.processEvents()
            assert segments.horizontalHeader().isVisible()
            assert fittings.horizontalHeader().isVisible()
        finally:
            window.close()
            window.deleteLater()
