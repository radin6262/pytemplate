"""TUI for PyTemplate Template Manager using Urwid."""

import subprocess
import sys
import shutil
from pathlib import Path
from typing import List, Dict, Optional

import urwid
from urwid import (
    Widget, Text, ListBox, SimpleListWalker, Button,
    Edit, Pile, Divider, AttrMap, WidgetWrap,
    GridFlow, LineBox, Columns
)


class TemplateManagerTUI:
    """Urwid TUI for managing PyTemplate templates."""

    palette = [
        ('header', 'light cyan', 'dark blue'),
        ('body', 'white', 'dark gray'),
        ('footer', 'light gray', 'dark blue'),
        ('selected', 'black', 'light cyan'),
        ('done', 'light green', 'dark gray'),
        ('pending', 'light gray', 'dark gray'),
        ('error', 'light red', 'dark gray'),
        ('success', 'light green', 'dark gray'),
        ('warning', 'yellow', 'dark gray'),
        ('info', 'light cyan', 'dark gray'),
        ('button', 'white', 'dark blue'),
        ('button_focus', 'black', 'light cyan'),
    ]

    def __init__(self, manager):
        """Initialize with a TemplateManager instance."""
        self.manager = manager
        self.templates_dir = manager.templates_dir

        # UI state
        self.templates: List[Dict] = []
        self.selected_index = 0
        self.current_view = "list"  # 'list' or 'detail'
        self.selected_template: Optional[Dict] = None
        self.main_loop: Optional[urwid.MainLoop] = None
        self.dialog_active = False
        self.dialog_result = None
        self.downloader_tui = None

        self.pending_command = None

        # Build the main view
        self.top_widget = self._build_main_view()
        self.loop = urwid.MainLoop(
            self.top_widget,
            palette=self.palette,
            unhandled_input=self._handle_global_input
        )

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_main_view(self) -> Widget:
        """Build the root widget."""
        self.header_text = Text(" PyTemplate Template Manager ", align='center')
        self.header = AttrMap(self.header_text, 'header')

        # The main content area (list or detail)
        self.content_area = self._build_list_view()
        self.content_walker = SimpleListWalker(self.content_area)
        self.content_listbox = ListBox(self.content_walker)

        # Status bar
        self.status_text = Text("", align='center')
        self.status_bar = AttrMap(self.status_text, 'footer')

        # Layout
        content = Pile([
            ('pack', self.header),
            ('pack', Divider('─')),
            self.content_listbox,
            ('pack', Divider('─')),
            ('pack', self.status_bar),
        ])

        return content

    def _build_list_view(self) -> List[Widget]:
        """Build the template list view."""
        self.templates = self.manager.list_templates()
        widgets = []

        if not self.templates:
            widgets.append(Text("  No templates found.", align='center'))
        else:
            for i, tpl in enumerate(self.templates):
                name = tpl.get('name', 'unknown')
                desc = tpl.get('description', '')
                prefix = "▶ " if i == self.selected_index else "  "
                text = f"{prefix}{name:<20}  {desc[:40]}" if desc else f"{prefix}{name}"
                widgets.append(
                    AttrMap(
                        Text(text),
                        'selected' if i == self.selected_index else 'body'
                    )
                )

        # Help text
        widgets.append(Text("", align='center'))
        widgets.append(Text(
            " [Enter] Details  [c] Create  [d] Delete  [r] Rename  [i] Import  [e] Export  [w] Download  [q] Quit",
            align='center'
        ))
        widgets.append(Text(" [↑/↓] Navigate", align='center'))

        return widgets

    def _build_detail_view(self, template: Dict) -> List[Widget]:
        """Build the template detail view."""
        widgets = []

        name = template.get('name', 'Unknown')
        widgets.append(Text(f"  Template: {name}", align='left'))

        # Information
        info_lines = []
        if template.get('description'):
            info_lines.append(f"  Description: {template['description']}")
        if template.get('author'):
            info_lines.append(f"  Author:      {template['author']}")
        if template.get('version'):
            info_lines.append(f"  Version:     {template['version']}")
        if template.get('category'):
            info_lines.append(f"  Category:    {template['category']}")
        if template.get('tags'):
            info_lines.append(f"  Tags:        {', '.join(template['tags'])}")
        if template.get('type'):
            info_lines.append(f"  Type:        {template['type']}")
        if template.get('created'):
            info_lines.append(f"  Created:     {template['created'][:10]}")

        # Statistics
        template_path = Path(template['path']) if template.get('path') else None
        if template_path and template_path.exists():
            try:
                content = template_path.read_text()
                lines = content.split('\n')
                dirs = sum(1 for l in lines if l.strip().endswith('/') and not l.strip().startswith('['))
                files = sum(1 for l in lines if ':' in l and not l.strip().startswith('['))
                info_lines.append(f"  Directories: {dirs}")
                info_lines.append(f"  Files:       {files}")
                info_lines.append(f"  Setup:       {'Yes' if '[setup]' in content else 'No'}")
            except:
                pass

        widgets.append(Text("", align='center'))
        widgets.extend([Text(line) for line in info_lines])

        # Preview (first 10 lines)
        if template_path and template_path.exists():
            try:
                content = template_path.read_text()
                preview_lines = content.split('\n')[:10]
                widgets.append(Text("", align='center'))
                widgets.append(Text("  Preview:", align='left'))
                for line in preview_lines:
                    widgets.append(Text(f"    {line[:60]}"))
                if len(content.split('\n')) > 10:
                    widgets.append(Text("    ..."))
            except:
                pass

        widgets.append(Text("", align='center'))

        # Action buttons / key hints
        widgets.append(Text(
            " [u] Use template  [v] View full  [r] Rename  [d] Delete  [b] Back",
            align='center'
        ))

        return widgets

    # ------------------------------------------------------------------
    # View switching
    # ------------------------------------------------------------------

    def _switch_to_list(self):
        """Switch back to the list view."""
        self.current_view = "list"
        self.selected_index = 0
        self.content_walker[:] = self._build_list_view()
        self._update_status()
        self._refresh()

    def _switch_to_detail(self, template: Dict):
        """Show detail view for a template."""
        self.current_view = "detail"
        self.selected_template = template
        self.content_walker[:] = self._build_detail_view(template)
        self._update_status(f"Viewing: {template.get('name', 'Unknown')}")
        self._refresh()

    def _refresh(self):
        """Refresh the UI."""
        if self.main_loop:
            try:
                self.main_loop.draw_screen()
            except:
                pass

    def _update_status(self, message: str = ""):
        """Update the status bar."""
        if not message:
            if self.current_view == "list":
                count = len(self.templates)
                message = f"{count} template(s) available"
            else:
                message = f"Details for {self.selected_template.get('name', '')}"
        self.status_text.set_text(message)

    # ------------------------------------------------------------------
    # Input handling (global shortcuts)
    # ------------------------------------------------------------------

    def _handle_global_input(self, key: str) -> bool:
        """Handle keyboard input for the active view."""

        if self.dialog_active:
            return False

        # Keep a local reference because handle_input() may close
        # the downloader and set self.downloader_tui to None.
        downloader = self.downloader_tui

        if downloader is not None:
            handled = downloader.handle_input(key)

            # The downloader may have closed itself during handle_input().
            # Use the local reference instead of self.downloader_tui.
            if downloader.current_view == "list":
                return handled

            if handled:
                return True

            # If the downloader closed itself, do not continue using it.
            if self.downloader_tui is None:
                return True

        if key == "q":
            self._quit()
            return True

        if self.current_view == "list":
            return self._handle_list_input(key)

        if self.current_view == "detail":
            return self._handle_detail_input(key)

        return False

    def _handle_list_input(self, key: str) -> bool:
        """Handle keys when in list view."""
        if key == 'enter':
            if self.templates and 0 <= self.selected_index < len(self.templates):
                self._switch_to_detail(self.templates[self.selected_index])
            return True

        if key == 'up':
            self.selected_index = max(0, self.selected_index - 1)
            self.content_walker[:] = self._build_list_view()
            self._refresh()
            return True

        if key == 'down':
            max_idx = len(self.templates) - 1
            self.selected_index = min(max_idx, self.selected_index + 1)
            self.content_walker[:] = self._build_list_view()
            self._refresh()
            return True

        if key == 'c':
            self._create_template()
            return True

        if key == 'd':
            self._delete_template()
            return True

        if key == 'r':
            self._rename_template()
            return True

        if key == 'i':
            self._import_template()
            return True

        if key == 'e':
            self._export_template()
            return True

        if key == 'w':
            self._download_template()
            return True

        return False

    def _handle_detail_input(self, key: str) -> bool:
        """Handle keys when in detail view."""
        if key == 'b':
            self._switch_to_list()
            return True

        if key == 'u':
            self._use_template()
            return True

        if key == 'v':
            self._view_full_template()
            return True

        if key == 'r':
            self._rename_template()
            return True

        if key == 'd':
            self._delete_template()
            return True

        return False

    # ------------------------------------------------------------------
    # Actions (call the manager and refresh)
    # ------------------------------------------------------------------

    def _create_template(self):
        """Launch the template builder."""
        self._close_dialog()

        cmd = [
            sys.executable,
            "-m",
            "pytemplate.cli",
            "buildtemplate",
        ]

        self._run_subprocess(cmd)
        self._refresh_list()

    def _use_template(self):
        """Ask for a project name, then exit the manager TUI."""
        if not self.selected_template:
            return

        template_name = self.selected_template["name"]

        edit = Edit("Project name: ")
        msg = Text("", align="center")

        def on_create(btn):
            project_name = edit.edit_text.strip()

            if not project_name:
                msg.set_text(
                    ("error", "Project name cannot be empty.")
                )
                return

            self.pending_command = [
                sys.executable,
                "-m",
                "pytemplate.cli",
                "create",
                project_name,
                "--template",
                template_name,
            ]

            # The manager must completely leave Urwid.
            raise urwid.ExitMainLoop()

        def on_cancel(btn):
            self._close_dialog()

        content = Pile([
            Text(
                f"Create project from '{template_name}'",
                align="center",
            ),
            Divider("─"),
            edit,
            msg,
            GridFlow(
                [
                    Button("Create", on_press=on_create),
                    Button("Cancel", on_press=on_cancel),
                ],
                cell_width=12,
                h_sep=1,
                v_sep=0,
                align="center",
            ),
        ])

        dialog = LineBox(
            content,
            title=" Create Project ",
        )

        self._show_dialog(
            dialog,
            focus_position=2,
        )
    def _delete_template(self):
        """Delete the selected template (with confirmation)."""
        name = self.selected_template['name'] if self.selected_template else None
        if not name:
            if self.templates and 0 <= self.selected_index < len(self.templates):
                name = self.templates[self.selected_index]['name']
            else:
                return

        def confirm_delete(btn, confirmed):
            self._close_dialog()
            if confirmed:
                self.manager.remove_template(name)
                self._refresh_list()
                if self.current_view == "detail":
                    self._switch_to_list()
                else:
                    self.content_walker[:] = self._build_list_view()
                    self._update_status()
                    self._refresh()

        content = Pile([
            Text(f"Delete template '{name}'?", align='center'),
            Divider("─"),
            GridFlow(
                [
                    Button("Yes", on_press=lambda b: confirm_delete(b, True)),
                    Button("No",  on_press=lambda b: confirm_delete(b, False)),
                ],
                cell_width=10,
                h_sep=2,
                v_sep=0,
                align='center'
            ),
        ])
        dialog = LineBox(content, title=" Confirm Delete ")
        self._show_dialog(dialog)

    def _rename_template(self):
        """Rename the selected template."""
        old_name = self.selected_template['name'] if self.selected_template else None
        if not old_name:
            if self.templates and 0 <= self.selected_index < len(self.templates):
                old_name = self.templates[self.selected_index]['name']
            else:
                return

        edit = Edit("New name: ")
        msg = Text("", align='center')

        def on_rename(btn):
            new_name = edit.edit_text.strip()
            if new_name:
                if self.manager.rename_template(old_name, new_name):
                    self._refresh_list()
                    if self.current_view == "detail":
                        self.selected_template['name'] = new_name
                        self.content_walker[:] = self._build_detail_view(self.selected_template)
                    else:
                        self.content_walker[:] = self._build_list_view()
                    self._update_status()
                    self._refresh()
                    self._close_dialog()
                else:
                    msg.set_text(("error", "Rename failed."))

        def on_cancel(btn):
            self._close_dialog()

        content = Pile([
            Text(f"Rename '{old_name}'", align='center'),
            Divider("─"),
            edit,
            msg,
            GridFlow(
                [
                    Button("Rename", on_press=on_rename),
                    Button("Cancel", on_press=on_cancel),
                ],
                cell_width=12,
                h_sep=1,
                v_sep=0,
                align='center'
            ),
        ])
        dialog = LineBox(content, title=" Rename Template ")
        self._show_dialog(dialog, focus_position=2)

    def _import_template(self):
        """Import a template from a file."""
        path_edit = Edit("File path: ")
        msg = Text("", align='center')

        def on_import(btn):
            path = path_edit.edit_text.strip()
            if path:
                src = Path(path)
                if src.exists():
                    if self.manager.import_template(src):
                        self._refresh_list()
                        self.content_walker[:] = self._build_list_view()
                        self._update_status()
                        self._refresh()
                        self._close_dialog()
                    else:
                        msg.set_text(("error", "Import failed."))
                else:
                    msg.set_text(("error", "File not found."))

        def on_cancel(btn):
            self._close_dialog()

        content = Pile([
            Text("Import template from .setup file", align='center'),
            Divider("─"),
            path_edit,
            msg,
            GridFlow(
                [
                    Button("Import", on_press=on_import),
                    Button("Cancel", on_press=on_cancel),
                ],
                cell_width=12,
                h_sep=1,
                v_sep=0,
                align='center'
            ),
        ])
        dialog = LineBox(content, title=" Import Template ")
        self._show_dialog(dialog, focus_position=2)

    def _export_template(self):
        """Export the selected template to a file."""
        name = self.selected_template['name'] if self.selected_template else None
        if not name:
            if self.templates and 0 <= self.selected_index < len(self.templates):
                name = self.templates[self.selected_index]['name']
            else:
                return

        path_edit = Edit("Export path: ", edit_text=f"{name}.setup")
        msg = Text("", align='center')

        def on_export(btn):
            path = path_edit.edit_text.strip()
            if path:
                out = Path(path)
                if self.manager.export_template(name, out):
                    self._update_status(f"Exported to {out}")
                    self._refresh()
                    self._close_dialog()
                else:
                    msg.set_text(("error", "Export failed."))

        def on_cancel(btn):
            self._close_dialog()

        content = Pile([
            Text(f"Export '{name}'", align='center'),
            Divider("─"),
            path_edit,
            msg,
            GridFlow(
                [
                    Button("Export", on_press=on_export),
                    Button("Cancel", on_press=on_cancel),
                ],
                cell_width=12,
                h_sep=1,
                v_sep=0,
                align='center'
            ),
        ])
        dialog = LineBox(content, title=" Export Template ")
        self._show_dialog(dialog, focus_position=2)

    def _download_template(self):
        """Open the template downloader inside the current Urwid loop."""

        try:
            from .template_downloader_tui import (
                run_template_downloader_tui,
            )
        except ImportError as e:
            self._update_status(
                f"Downloader TUI unavailable: {e}"
            )
            self._refresh()
            return

        def return_to_manager():
            self.downloader_tui = None
            self.main_loop.widget = self.top_widget
            self._refresh_list()

        self.downloader_tui = run_template_downloader_tui(
            manager=self.manager,
            main_loop=self.main_loop,
            on_close=return_to_manager,
        )

    def _view_full_template(self):
        """Show the full template content in a dialog."""
        if not self.selected_template:
            return
        path = Path(self.selected_template['path'])
        if not path.exists():
            return
        content_text = path.read_text()

        close_btn = Button("Close", on_press=lambda b: self._close_dialog())
        content = Pile([
            Text("Full Template Content", align='center'),
            Divider("─"),
            Text(content_text),
            Divider("─"),
            close_btn,
        ])
        dialog = LineBox(content, title=" Template Preview ")
        self._show_dialog(dialog)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ask_string(self, prompt: str) -> Optional[str]:
        """Show a simple input dialog and return the string."""
        result = None
        edit = Edit(prompt)
        msg = Text("", align='center')

        def on_ok(btn):
            nonlocal result
            result = edit.edit_text.strip()
            self._close_dialog()

        def on_cancel(btn):
            self._close_dialog()

        content = Pile([
            Text("", align='center'),
            edit,
            msg,
            GridFlow(
                [
                    Button("OK", on_press=on_ok),
                    Button("Cancel", on_press=on_cancel),
                ],
                cell_width=10,
                h_sep=2,
                v_sep=0,
                align='center'
            ),
        ])
        dialog = LineBox(content, title=" Input ")
        self._show_dialog(dialog, focus_position=1)

        # Wait for dialog to close
        while self.dialog_active:
            self.loop.run_once()
        return result

    def _run_subprocess(self, cmd: List[str]):
        """Run a subprocess and wait."""
        try:
            self._update_status(f"Running: {' '.join(cmd)}")
            self._refresh()
            subprocess.run(cmd, check=True)
        except Exception as e:
            self._update_status(f"Error: {e}")
            self._refresh()

    def _refresh_list(self):
        """Refresh the template list data and UI."""
        self.templates = self.manager.list_templates()
        if self.current_view == "list":
            self.content_walker[:] = self._build_list_view()
        else:
            # If in detail view, keep showing the same template
            if self.selected_template:
                # Re-fetch the template data
                updated = self.manager.get_template(self.selected_template['name'])
                if updated:
                    self.selected_template = updated
                    self.content_walker[:] = self._build_detail_view(updated)
                else:
                    self._switch_to_list()
        self._update_status()
        self._refresh()

    # ------------------------------------------------------------------
    # Dialog management
    # ------------------------------------------------------------------

    def _show_dialog(self, dialog: Widget, focus_position: int = 0):
        """Show a dialog overlay."""
        self.dialog_active = True
        overlay = urwid.Overlay(
            dialog,
            self.top_widget,
            align='center',
            width=('relative', 60),
            valign='middle',
            height='pack',
        )
        self.main_loop.widget = overlay

        # Focus the desired widget (e.g., the first Edit)
        if focus_position is not None:
            try:
                # The dialog is a LineBox, its original_widget is a Pile.
                # We need to set focus on the Pile's child at focus_position.
                if hasattr(dialog, 'original_widget'):
                    pile = dialog.original_widget
                    if isinstance(pile, urwid.Pile):
                        pile.set_focus(focus_position)
            except Exception:
                pass

    def _close_dialog(self):
        """Close the current dialog."""
        self.dialog_active = False
        self.main_loop.widget = self.top_widget
        self._refresh()

    # ------------------------------------------------------------------
    # Quit
    # ------------------------------------------------------------------

    def _quit(self):
        """Exit the application."""
        raise urwid.ExitMainLoop()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self):
        """Run the TUI."""
        self.main_loop = self.loop
        self._refresh()

        try:
            self.loop.run()
        except urwid.ExitMainLoop:
            pass
        except KeyboardInterrupt:
            pass

        return self.pending_command


def run_template_manager_tui(manager):
    """Entry point for the TUI."""
    tui = TemplateManagerTUI(manager)
    pending_command = tui.run()

    if pending_command:
        try:
            subprocess.run(pending_command, check=True)
        except subprocess.CalledProcessError as e:
            click.echo(f"Command failed with exit code {e.returncode}")
        except Exception as e:
            click.echo(f"Error running command: {e}")