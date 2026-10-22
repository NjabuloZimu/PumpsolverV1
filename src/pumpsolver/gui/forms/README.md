# Designer source recovery

`main_window.ui` retains the supplied Designer layout, with resource references
made relative to this repository. The other nine `.ui` files were recovered
from the existing generated `Ui_*` classes because their original Designer
files were absent. They are editable replacements, not byte-for-byte copies of
those lost source files.

Recovery used Qt Designer's `QFormBuilder` serialization, removed Qt's internal
runtime widgets and state, and restored the original explicit properties,
fonts, image references, table headers, combo-box items, tab order and signal
connections from the generated code. `legacy_layout_snapshot.json` records the
authored control names, geometry, explicit font settings, image sizes, table
configuration and widget properties for all ten forms. Platform-inherited font
defaults are deliberately excluded. The About form's preview title is generic;
the handwritten About controller adds the current application version.

Edit these `.ui` files and `../assets/assets.qrc`, then run from the project root:

```powershell
.\.venv\Scripts\python.exe tools\generate_ui.py
.\.venv\Scripts\python.exe tools\generate_ui.py --check
```

The script regenerates every `../generated/ui_*.py` module and the consolidated
`../generated/resources_rc.py`. Generated modules contain no handwritten
behavior. `tests/test_ui_sources.py` checks source/resource completeness,
regeneration and preservation of the recovered interface.
