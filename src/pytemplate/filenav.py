"""Urwid file navigator (loop‑less, to be embedded in another main loop)."""

import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Callable

import urwid
from urwid import (
    Widget, Text, ListBox, SimpleListWalker, Button,
    Edit, Pile, Divider, AttrMap, WidgetWrap,
    GridFlow, LineBox
)


class FileEntry(WidgetWrap):
    """A selectable file/directory entry."""

    def __init__(self, text: str, path: Optional[Path] = None, is_dir: bool = False):
        self.path = path
        self.is_dir = is_dir
        self.text_widget = Text(text)
        super().__init__(
            AttrMap(
                self.text_widget,
                "file",
                "selected"
            )
        )

    def selectable(self):
        return True

    def keypress(self, size, key):
        return key

    def get_text(self) -> str:
        return self.text_widget.text


class FileNavigatorTUI:
    """Urwid file navigator (no own MainLoop)."""

    palette = [
        ('header', 'light cyan', 'dark blue'),
        ('body', 'white', 'dark gray'),
        ('footer', 'light gray', 'dark blue'),
        ('selected', 'black', 'light cyan'),
        ('dir', 'light blue', 'dark gray'),
        ('file', 'light gray', 'dark gray'),
        ('selected_file', 'light green', 'dark gray'),
        ('error', 'light red', 'dark gray'),
        ('success', 'light green', 'dark gray'),
        ('info', 'light cyan', 'dark gray'),
        ('button', 'white', 'dark blue'),
        ('button_focus', 'black', 'light cyan'),
    ]

    def __init__(self, template_name: str, main_loop=None, on_done: Optional[Callable[[List[str]], None]] = None):
        self.template_name = template_name
        self.main_loop = main_loop
        self.on_done = on_done

        self.temp_dir = Path(tempfile.mkdtemp()) / template_name
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.current_dir = self.temp_dir
        self.selected_files: List[str] = []
        self.result_files: List[str] = []
        self.done = False
        self.dialog_active = False
        self.overlay = None

        # Build the UI
        self.top_widget = self._build_main_view()

    def _build_main_view(self) -> Widget:
        """Build the main view."""
        self.header_text = Text(
            f" File Navigator - {self.template_name} ",
            align='center'
        )
        self.header = AttrMap(self.header_text, 'header')

        self.path_text = Text(f"📂 {self.current_dir}", align='center')
        self.path_bar = AttrMap(self.path_text, 'info')

        # File list
        self.file_list = self._build_file_list()
        self.file_list_walker = SimpleListWalker(self.file_list)
        self.body = ListBox(self.file_list_walker)

        # Status bar
        self.status_text = Text("", align='center')
        self.status_bar = AttrMap(self.status_text, 'footer')

        # Action buttons
        self.actions = self._build_actions()

        # Layout
        content = Pile([
            ('pack', self.header),
            ('pack', Divider('─')),
            ('pack', self.path_bar),
            ('pack', Divider('─')),
            self.body,
            ('pack', Divider('─')),
            ('pack', self.actions),
            ('pack', Divider('─')),
            ('pack', self.status_bar),
        ])

        return content

    def _build_file_list(self) -> List[Widget]:
        """Build the file list widgets."""
        widgets = []

        # Add parent directory if not at root
        if self.current_dir != self.temp_dir:
            widgets.append(
                FileEntry("  [..] 📁 .. (parent)", path=self.current_dir.parent, is_dir=True)
            )

        try:
            items = sorted(self.current_dir.iterdir())
            for item in items:
                if item.name.startswith('.'):
                    continue
                is_dir = item.is_dir()
                icon = "📁" if is_dir else "📄"
                file_path = str(item)

                if is_dir:
                    widgets.append(
                        FileEntry(f"  {icon} {item.name}/", path=item, is_dir=True)
                    )
                else:
                    prefix = "★ " if file_path in self.selected_files else "  "
                    entry = FileEntry(f"  {prefix}{icon} {item.name}", path=item, is_dir=False)
                    widgets.append(entry)
        except PermissionError:
            widgets.append(
                AttrMap(
                    Text("  Permission denied", align='center'),
                    'error'
                )
            )

        if not widgets:
            widgets.append(
                AttrMap(
                    Text("  (empty directory)", align='center'),
                    'info'
                )
            )

        # Info and key hints
        widgets.append(Text("", align='center'))
        widgets.append(Text(
            f" Selected: {len(self.selected_files)} files",
            align='center'
        ))
        widgets.append(Text("", align='center'))
        widgets.append(Text(
            " [↑/↓] Navigate  [Enter] Select/Open  [s] Toggle selection  [a] Select all  [c] Clear",
            align='center'
        ))
        widgets.append(Text(
            " [d] New dir  [f] New file  [q] Quit  [Space] Toggle",
            align='center'
        ))

        return widgets

    def _build_actions(self) -> Widget:
        """Build action buttons using GridFlow."""

        def on_new_dir(btn):
            self._create_directory_dialog()

        def on_new_file(btn):
            self._create_file_dialog()

        def on_select_all(btn):
            self._select_all()

        def on_clear(btn):
            self._clear_selection()

        def on_done(btn):
            self._finish()

        def on_quit(btn):
            self._quit()

        buttons = [
            Button("New Dir", on_press=on_new_dir),
            Button("New File", on_press=on_new_file),
            Button("Select All", on_press=on_select_all),
            Button("Clear", on_press=on_clear),
            Button("Done", on_press=on_done),
            Button("Quit", on_press=on_quit),
        ]

        return GridFlow(
            buttons,
            cell_width=14,
            h_sep=1,
            v_sep=0,
            align='center'
        )

    def _handle_input(self, key: str) -> bool:
        """Handle global input for navigator."""
        if self.dialog_active:
            return False

        if key == 'q':
            self._quit()
            return True
        elif key == 'enter':
            self._select_current()
            return True
        elif key in ('s', ' '):
            self._toggle_selection()
            return True
        elif key == 'a':
            self._select_all()
            return True
        elif key == 'c':
            self._clear_selection()
            return True
        elif key == 'd':
            self._create_directory_dialog()
            return True
        elif key == 'f':
            self._create_file_dialog()
            return True
        return False

    def _navigate(self, direction: int):
        """Navigate the list."""
        list_walker = self.file_list_walker
        current_pos = self.body.get_focus()[1]
        if current_pos is None:
            return
        new_pos = current_pos + direction
        if 0 <= new_pos < len(list_walker):
            self.body.set_focus(new_pos)

    def _select_current(self):
        """Select or open the current item."""
        focus = self.body.get_focus()[0]
        if not focus:
            return

        text = self._get_widget_text(focus)
        if not text:
            return

        # Check if it's a directory
        if "📁" in text:
            if "📁 .." in text:
                parent = self.current_dir.parent
                if parent != self.current_dir:
                    self.current_dir = parent
                    self._refresh()
                    self._update_status("📂 Navigated up")
            else:
                name = text.split("📁")[1].strip().rstrip('/')
                new_dir = self.current_dir / name
                if new_dir.exists() and new_dir.is_dir():
                    self.current_dir = new_dir
                    self._refresh()
                    self._update_status(f"📂 Navigated to: {name}")
        elif "📄" in text:
            self._toggle_selection()

    def _toggle_selection(self):
        """Toggle selection of the current file."""
        focus = self.body.get_focus()[0]
        if not focus:
            return

        text = self._get_widget_text(focus)
        if not text or "📁" in text:
            return

        name = text.split("📄")[1].strip()
        if "★" in name:
            name = name.replace("★", "").strip()
        file_path = str(self.current_dir / name)

        if file_path in self.selected_files:
            self.selected_files.remove(file_path)
            self._update_status(f"Deselected: {name}")
        else:
            self.selected_files.append(file_path)
            self._update_status(f"Selected: {name}")

        self._refresh()

    def _select_all(self):
        """Select all files in current directory."""
        for item in self.current_dir.iterdir():
            if item.is_file() and not item.name.startswith('.'):
                file_path = str(item)
                if file_path not in self.selected_files:
                    self.selected_files.append(file_path)
        self._refresh()
        self._update_status(f"Selected all files ({len(self.selected_files)})")

    def _clear_selection(self):
        """Clear selection."""
        self.selected_files.clear()
        self._refresh()
        self._update_status("Selection cleared")

    def _get_widget_text(self, widget) -> Optional[str]:
        """Extract text from a widget."""
        if isinstance(widget, FileEntry):
            return widget.get_text()
        if isinstance(widget, AttrMap):
            return self._get_widget_text(widget.original_widget)
        if isinstance(widget, Text):
            return widget.text
        return None

    def _refresh(self):
        """Refresh the file list."""
        if not self.main_loop:
            return

        try:
            old_focus = self.body.get_focus()[1]
        except Exception:
            old_focus = 0

        new_widgets = self._build_file_list()
        self.file_list_walker.clear()
        self.file_list_walker.extend(new_widgets)
        self.path_text.set_text(f"📂 {self.current_dir}")

        if new_widgets:
            new_focus = min(old_focus, len(new_widgets) - 1)
            try:
                self.body.set_focus(new_focus)
            except Exception:
                pass

    def _update_status(self, message: str):
        """Update the status bar."""
        self.status_text.set_text(message)

    def _show_dialog(self, dialog: Widget, focus_position: int = 0):
        """Show a dialog overlay."""
        self.dialog_active = True
        self.overlay = urwid.Overlay(
            dialog,
            self.top_widget,
            align='center',
            width=('relative', 60),
            valign='middle',
            height='pack',
        )
        if self.main_loop:
            self.main_loop.widget = self.overlay

        # Focus the desired widget
        if focus_position is not None:
            try:
                pile = dialog.original_widget
                if isinstance(pile, urwid.Pile):
                    pile.set_focus(focus_position)
            except Exception:
                pass

    def _close_dialog(self):
        """Close the current dialog."""
        self.dialog_active = False
        if self.main_loop:
            self.main_loop.widget = self.top_widget
            self._refresh()
            self.main_loop.draw_screen()

    def _focus_edit(self, dialog: Widget, edit_index: int = 2):
        """Focus the Edit widget inside a dialog."""
        try:
            if hasattr(dialog, 'original_widget') and hasattr(dialog.original_widget, 'set_focus'):
                dialog.original_widget.set_focus(edit_index)
            elif hasattr(dialog, 'set_focus'):
                dialog.set_focus(edit_index)
        except Exception:
            pass

    def _create_directory_dialog(self):
        """Show dialog to create a directory."""
        edit = Edit("Directory name: ")
        msg = Text("", align='center')

        def on_create(btn):
            name = edit.edit_text.strip()
            if name:
                name = name.rstrip('/')
                if '/' in name or '\\' in name:
                    msg.set_text(("error", "❌ Use single directory name only"))
                    return
                new_dir = self.current_dir / name
                try:
                    new_dir.mkdir()
                    msg.set_text(("success", f"✅ Created: {name}"))
                    self._refresh()
                    edit.set_edit_text("")
                    self._update_status(f"Created directory: {name}")
                except FileExistsError:
                    msg.set_text(("error", f"❌ '{name}' already exists"))
                except Exception as e:
                    msg.set_text(("error", f"❌ Error: {e}"))

        def on_done(btn):
            self._close_dialog()

        content = Pile([
            Text("CREATE DIRECTORY", align="center"),
            Divider("─"),
            edit,
            msg,
            GridFlow(
                [
                    Button("Create", on_press=on_create),
                    Button("Close", on_press=on_done),
                ],
                cell_width=12,
                h_sep=1,
                v_sep=0,
                align='center'
            ),
        ])
        dialog = LineBox(content, title=" New Directory ")
        self._show_dialog(dialog, focus_position=2)

    def _create_file_dialog(self):
        """Show dialog to create a file."""
        path_edit = Edit("File name: ")
        content_edit = Edit("Content (@ref): ")
        msg = Text("", align='center')

        def on_create(btn):
            name = path_edit.edit_text.strip()
            content = content_edit.edit_text.strip()
            if name:
                if '/' in name or '\\' in name:
                    msg.set_text(("error", "❌ Use single filename only"))
                    return
                new_file = self.current_dir / name
                try:
                    new_file.write_text(content)
                    file_path = str(new_file)
                    if file_path not in self.selected_files:
                        self.selected_files.append(file_path)
                    msg.set_text(("success", f"✅ Created and selected: {name}"))
                    self._refresh()
                    path_edit.set_edit_text("")
                    content_edit.set_edit_text("")
                    self._update_status(f"Created file: {name}")
                except Exception as e:
                    msg.set_text(("error", f"❌ Error: {e}"))

        def on_done(btn):
            self._close_dialog()

        content = Pile([
            Text("CREATE FILE", align="center"),
            Divider("─"),
            path_edit,
            content_edit,
            msg,
            GridFlow(
                [
                    Button("Create", on_press=on_create),
                    Button("Close", on_press=on_done),
                ],
                cell_width=12,
                h_sep=1,
                v_sep=0,
                align='center'
            ),
        ])
        dialog = LineBox(content, title=" New File ")
        self._show_dialog(dialog, focus_position=2)

    def _finish(self):
        """Finish and return selected files."""
        self.done = True
        self.result_files = self.selected_files.copy()
        if self.on_done:
            self.on_done(self.result_files)

    def _quit(self):
        """Quit without saving."""
        if self.selected_files:
            def on_quit(btn):
                self.result_files = []
                self.done = True
                if self.on_done:
                    self.on_done([])

            def on_cancel(btn):
                self._close_dialog()

            content = Pile([
                Text("Exit without saving selected files?", align="center"),
                GridFlow(
                    [
                        Button("Yes", on_press=on_quit),
                        Button("No", on_press=on_cancel),
                    ],
                    cell_width=10,
                    h_sep=2,
                    v_sep=0,
                    align='center'
                ),
            ])
            dialog = LineBox(content, title=" Confirm ")
            self._show_dialog(dialog)
        else:
            self.result_files = []
            self.done = True
            if self.on_done:
                self.on_done([])

    def run(self) -> List[str]:
        """This method should not be called when embedded; kept for backward compatibility."""
        # If someone calls run, we create a temporary loop (should not happen in normal usage).
        # We'll still implement it to avoid crashes, but it won't be used in the integrated flow.
        loop = urwid.MainLoop(
            self.top_widget,
            palette=self.palette,
            unhandled_input=self._handle_input
        )
        try:
            loop.run()
        except KeyboardInterrupt:
            pass
        finally:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        return self.result_files