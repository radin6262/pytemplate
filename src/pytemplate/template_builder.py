"""Full TUI template builder using Urwid with integrated file navigator."""

import click
from pathlib import Path
from typing import List, Dict, Optional, Set

import urwid
from urwid import (
    Widget, Text, ListBox, SimpleListWalker, Button,
    Edit, Pile, Divider, AttrMap,
    Columns, LineBox, GridFlow
)

# Import the file navigator (loop‑less version)
from .filenav import FileNavigatorTUI


class TemplateBuilderTUI:
    """Full TUI template builder using Urwid."""

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
    ]

    def __init__(self, template_name: str, templates_dir: Path, force: bool = False):
        self.template_name = template_name
        self.templates_dir = templates_dir
        self.force = force
        self.template_file = templates_dir / f"{template_name}.setup"
        self._builder_input_handler = self._handle_input

        # Template parts
        self.directories: List[str] = []
        self.files: Dict[str, Optional[str]] = {}
        self.commands: List[str] = []
        self.references: Set[str] = set()

        # UI state
        self.selected_index = 0
        self.message = ""
        self.message_style = "info"
        self.main_loop = None
        self.dialog_active = False

        # Build the UI
        self.top_widget = self._build_main_view()
        self.loop = urwid.MainLoop(
            self.top_widget,
            palette=self.palette,
            unhandled_input=self._handle_input
        )



    def _build_main_view(self) -> Widget:
        """Build the main view."""
        self.header_text = Text(
            f" PyTemplate Builder - {self.template_name} ",
            align='center'
        )
        self.header = AttrMap(self.header_text, 'header')

        # Task list
        self.task_list = self._build_task_list()
        self.task_list_walker = SimpleListWalker(self.task_list)

        self.body = ListBox(self.task_list_walker)

        # Status bar
        self.status_text = Text("", align='center')
        self.status_bar = AttrMap(self.status_text, 'footer')

        # Build the layout
        content = Pile([
            ('pack', self.header),
            ('pack', Divider('─')),
            self.body,
            ('pack', Divider('─')),
            ('pack', self.status_bar),
        ])

        return content

    def _build_task_list(self) -> List[Widget]:
        """Build the task list."""
        tasks = self._get_tasks()
        widgets = []

        for i, (task_id, description, check_func) in enumerate(tasks):
            done = check_func()
            check = "✓" if done else " "

            prefix = "▶ " if i == self.selected_index else "  "
            status_attr = "done" if done else "pending"

            if i == self.selected_index:
                text = AttrMap(
                    Text(f"{prefix}[{check}] {task_id}. {description}"),
                    'selected'
                )
            else:
                text = AttrMap(
                    Text(f"{prefix}[{check}] {task_id}. {description}"),
                    status_attr
                )
            widgets.append(text)

        widgets.append(Text("", align='center'))
        widgets.append(Text(" [f] File Manager  [s] Save  [q] Quit  [↑/↓] Navigate  [Enter] Select", align='center'))
        widgets.append(Text("", align='center'))

        return widgets

    def _get_tasks(self) -> List[tuple]:
        return [
            ("1", "Add directories", self._has_directories),
            ("2", "Add files", self._has_files),
            ("3", "Add setup commands", self._has_commands),
            ("4", "Preview and save template", self._can_save),
            ("5", "Add reference files", self._has_references),
        ]

    def _has_directories(self) -> bool:
        return len(self.directories) > 0

    def _has_files(self) -> bool:
        return len(self.files) > 0

    def _has_commands(self) -> bool:
        return len(self.commands) > 0

    def _has_references(self) -> bool:
        return len(self.references) > 0

    def _can_save(self) -> bool:
        return self._has_directories() or self._has_files() or self._has_commands()

    def _handle_input(self, key: str) -> bool:
        if self.dialog_active:
            return False

        if key == 'q':
            self._quit()
            return True
        elif key == 's':
            self._save()
            return True
        elif key == 'f':
            self._file_manager()
            return True
        elif key == 'up':
            self.selected_index = max(0, self.selected_index - 1)
            self._refresh()
            return True
        elif key == 'down':
            tasks = self._get_tasks()
            self.selected_index = min(len(tasks) - 1, self.selected_index + 1)
            self._refresh()
            return True
        elif key == 'enter':
            tasks = self._get_tasks()
            if 0 <= self.selected_index < len(tasks):
                task_id = tasks[self.selected_index][0]
                self._execute_task(task_id)
            return True
        elif key in ['1', '2', '3', '4', '5']:
            self._execute_task(key)
            return True
        return False

    def _refresh(self):
        if self.main_loop:
            self.task_list_walker[:] = self._build_task_list()
            self._update_status()

    def _update_status(self):
        status = f"Template: {self.template_name} | "
        status += f"Dirs: {len(self.directories)} | "
        status += f"Files: {len(self.files)} | "
        status += f"Commands: {len(self.commands)} | "
        status += f"Refs: {len(self.references)}"
        if self.message:
            status += f" | {self.message}"
            self.message = ""
        self.status_text.set_text(status)

    def _execute_task(self, task_id: str):
        if task_id == '1':
            self._add_directories()
        elif task_id == '2':
            self._add_files()
        elif task_id == '3':
            self._add_commands()
        elif task_id == '4':
            self._preview_template()
        elif task_id == '5':
            self._add_reference_files()
        self._refresh()

    def _show_dialog(self, dialog: Widget):
        """Show a dialog overlay."""
        self.dialog_active = True

        overlay = urwid.Overlay(
            dialog,
            self.top_widget,
            align='center',
            width=('relative', 70),
            valign='middle',
            height='pack',
        )

        if self.main_loop:
            self.main_loop.widget = overlay

    def _close_dialog(self):
        """Close the current dialog."""
        self.dialog_active = False

        if self.main_loop:
            self.main_loop.widget = self.top_widget
            self._refresh()

    def _file_manager(self):
        """Open the file manager using the same Urwid MainLoop."""
        if not self.main_loop:
            return

        # Make sure we're displaying the builder before switching
        self.main_loop.widget = self.top_widget

        self.file_navigator = FileNavigatorTUI(
            self.template_name,
            main_loop=self.main_loop,
            on_done=self._file_manager_done
        )

        # Give the navigator the main loop
        self.file_navigator.main_loop = self.main_loop

        # IMPORTANT:
        # While the navigator is active, its input handler must be used.
        self.main_loop.unhandled_input = self.file_navigator._handle_input

        # Switch the displayed widget
        self.main_loop.widget = self.file_navigator.top_widget

    def _file_manager_done(self, selected_files: List[str]):
        """Return from the file navigator to the template builder."""

        # Restore the builder's input handler FIRST
        self.main_loop.unhandled_input = self._handle_input

        # Restore builder widget
        self.main_loop.widget = self.top_widget

        # Process selected files
        if selected_files:
            self.message = (
                f"✅ Added {len(selected_files)} files from file manager"
            )
            self.message_style = "success"

            temp_dir = Path(selected_files[0]).parent.parent
            directories = set()

            for file_path in selected_files:
                try:
                    rel_path = Path(file_path).relative_to(temp_dir)

                    path = f"{{name}}/{str(rel_path).replace(chr(92), '/')}"

                    # Add parent directories
                    parent = rel_path.parent

                    while str(parent) != '.':
                        dir_path = (
                            f"{{name}}/"
                            f"{str(parent).replace(chr(92), '/')}"
                        )

                        if not dir_path.endswith('/'):
                            dir_path += '/'

                        directories.add(dir_path)
                        parent = parent.parent

                    # Read file content
                    full_path = Path(file_path)

                    if full_path.exists() and full_path.is_file():
                        content = None

                        try:
                            if full_path.stat().st_size < 1024 * 10:
                                content = full_path.read_text(
                                    encoding="utf-8"
                                )

                                if content.startswith('@'):
                                    self.references.add(
                                        content[1:].strip()
                                    )
                        except Exception:
                            pass

                        if path not in self.files:
                            self.files[path] = content

                except Exception as e:
                    self.message = f"❌ Error adding {file_path}: {e}"
                    self.message_style = "error"

            # Add directories
            for dir_path in sorted(directories):
                if dir_path not in self.directories:
                    self.directories.append(dir_path)

        else:
            self.message = "No files selected"
            self.message_style = "info"

        self._refresh()
    def _add_directories(self):
        """Add directories using a simple dialog."""
        if self.dialog_active:
            return

        edit = Edit("Directory path: ")
        msg = Text("", align='center')

        def on_add(btn):
            name = edit.edit_text.strip()
            if name:
                if not name.endswith('/'):
                    name += '/'
                if not name.startswith('{name}/'):
                    name = f"{{name}}/{name}"
                if name in self.directories:
                    msg.set_text(("error", f"❌ '{name}' already exists!"))
                else:
                    self.directories.append(name)
                    msg.set_text(("success", f"✅ Added: {name}"))
                    self._refresh()
                    edit.set_edit_text("")

        def on_done(btn):
            self._close_dialog()

        dirs_text = Text("Current: " + ", ".join(self.directories) if self.directories else "(empty)", align='center')

        content = Pile([
            Text("ADD DIRECTORIES", align="center"),
            Divider("─"),
            dirs_text,
            Divider("─"),
            edit,
            msg,
            Columns([
                Button("Add", on_press=on_add),
                Button("Done", on_press=on_done),
            ]),
        ])

        dialog = LineBox(content, title=" Directories ")
        self._show_dialog(dialog)

    def _add_files(self):
        """Add files using a simple dialog."""
        if self.dialog_active:
            return

        path_edit = Edit("File path: ")
        content_edit = Edit("Content (@ref): ")
        msg = Text("", align='center')

        def on_add(btn):
            path = path_edit.edit_text.strip()
            content = content_edit.edit_text.strip()
            if path:
                if not path.startswith('{name}/'):
                    path = f"{{name}}/{path}"
                if path in self.files:
                    msg.set_text(("error", f"❌ '{path}' already exists!"))
                else:
                    self.files[path] = content if content else None
                    if content and content.startswith('@'):
                        self.references.add(content[1:].strip())
                    msg.set_text(("success", f"✅ Added: {path}"))
                    self._refresh()
                    path_edit.set_edit_text("")
                    content_edit.set_edit_text("")

        def on_done(btn):
            self._close_dialog()

        files_text = Text("Current: " + ", ".join(self.files.keys()) if self.files else "(empty)", align='center')

        content = Pile([
            Text("ADD FILES", align="center"),
            Divider("─"),
            files_text,
            Divider("─"),
            path_edit,
            content_edit,
            msg,
            Columns([
                Button("Add", on_press=on_add),
                Button("Done", on_press=on_done),
            ])
        ])
        dialog = LineBox(content, title=" Files ")
        self._show_dialog(dialog)

    def _add_commands(self):
        """Add setup commands using a dialog with available commands."""
        if self.dialog_active:
            return

        available_commands = {
            "ask": "Ask for user input",
            "makevenv": "Create virtual environment. args: py version eg 3.14",
            "pkginstall": "Install packages. args: <pkg1> <pkg2>",
            "pkginstalldev": "Install dev packages. args: <pkg1> <pkg2>",
            "installreq": "Install from requirements.txt. args: none",
            "installreqdev": "Install dev requirements. args: none",
            "makefolder": "Create a folder. Recommended to use the file manager.",
            "makefile": "Create a file. Recommended to use the file manager.",
            "editfile": "Edit a file. Recommended to supply contents via makefile reference.",
            "initgit": "Initialize git",
            "echo": 'Print a message. args: "msg"',
        }

        edit = Edit("Command: ")
        msg = Text("", align="center")
        cmds_text = Text("", align="left")

        def update_commands_display():
            if self.commands:
                text = (
                        "Current commands:\n"
                        + "\n".join(
                    f"  {i + 1}. {cmd}"
                    for i, cmd in enumerate(self.commands)
                )
                )
            else:
                text = "Current commands:\n  (empty)"

            cmds_text.set_text(text)

        def select_command(command):
            edit.set_edit_text(command)
            edit.set_edit_pos(len(command))
            msg.set_text(
                (
                    "info",
                    f"Selected command: {command}",
                )
            )

        def on_add(btn):
            cmd = edit.edit_text.strip()

            if not cmd:
                msg.set_text(
                    ("error", "❌ Command cannot be empty.")
                )
                return

            command_name = cmd.split(maxsplit=1)[0]

            if command_name not in available_commands:
                msg.set_text(
                    (
                        "error",
                        f"❌ Unknown command: {command_name}",
                    )
                )
                return

            self.commands.append(cmd)

            msg.set_text(
                (
                    "success",
                    f"✅ Added: {cmd}",
                )
            )

            edit.set_edit_text("")
            edit.set_edit_pos(0)

            update_commands_display()
            self._refresh()

        def on_done(btn):
            self._close_dialog()

        # --------------------------------------------------------------
        # Available commands
        # --------------------------------------------------------------

        command_widgets = [
            Text(
                "Select a command:",
                align="center",
            ),
            Divider("─"),
        ]

        for command, description in available_commands.items():
            command_widgets.append(
                Button(
                    f"{command:<15} - {description}",
                    on_press=lambda btn, cmd=command: select_command(cmd),
                )
            )

        available_list = ListBox(
            SimpleListWalker(command_widgets)
        )

        available_box = LineBox(
            urwid.BoxAdapter(
                available_list,
                12,
            ),
            title=" Available Commands ",
        )

        # --------------------------------------------------------------
        # Command editor
        # --------------------------------------------------------------

        update_commands_display()

        editor_content = Pile([
            Text(
                "ADD SETUP COMMAND",
                align="center",
            ),

            Divider("─"),

            cmds_text,

            Divider("─"),

            edit,

            msg,

            Divider("─"),

            Columns(
                [
                    Button(
                        "Add",
                        on_press=on_add,
                    ),
                    Button(
                        "Done",
                        on_press=on_done,
                    ),
                ],
                dividechars=2,
            ),
        ])

        editor_box = LineBox(
            editor_content,
            title=" Command ",
        )

        # --------------------------------------------------------------
        # Use a vertical layout instead of Columns.
        # This avoids Urwid's BOX/FLOW conflict.
        # --------------------------------------------------------------

        content = Pile([
            Text(
                "ADD COMMANDS",
                align="center",
            ),

            Divider("─"),

            available_box,

            Divider("─"),

            editor_box,
        ])

        dialog = LineBox(
            content,
            title=" Setup Commands ",
        )

        self._show_dialog(dialog)
    def _preview_template(self):
        """Preview the template."""
        if not self._can_save():
            self.message = "⚠️ Template is empty!"
            self.message_style = "warning"
            self._refresh()
            return

        lines = ["[setup]"]
        for dir_path in sorted(self.directories):
            clean_path = dir_path.replace('{name}/', '')
            lines.append(f"makefolder {clean_path}")
        for file_path, content in sorted(self.files.items()):
            clean_path = file_path.replace('{name}/', '')

            if content:
                lines.append(f"makefile {clean_path}: {content}")
            else:
                lines.append(f"makefile {clean_path}:")
        for cmd in self.commands:
            lines.append(cmd)

        close_btn = Button("Close", on_press=lambda btn: self._close_dialog())

        content = Pile([
            Text("TEMPLATE PREVIEW", align="center"),
            Divider("─"),
            Text("\n".join(lines)),
            Divider("─"),
            close_btn,
        ])

        dialog = LineBox(content, title=" Preview ")
        self._show_dialog(dialog)

    def _add_reference_files(self):
        """Add reference files."""
        if not self.references:
            self.message = "⚠️ No references found. Add files with @ prefix first."
            self.message_style = "warning"
            self._refresh()
            return

        for ref in sorted(self.references):
            ref_file = self.templates_dir / f"@{ref}"

            edit = Edit("Content: ")
            msg = Text("", align='center')

            if ref_file.exists():
                try:
                    edit.set_text(ref_file.read_text())
                except:
                    pass

            def on_save(btn, ref_name=ref, ref_path=ref_file, edit=edit, msg=msg):
                content = edit.edit_text
                ref_path.write_text(content)
                msg.set_text(("success", f"✅ Saved: @{ref_name}"))
                self._refresh()

            def on_done(btn):
                self._close_dialog()

            content = Pile([
                Text(f"@{ref}", align="center"),
                Divider("─"),
                edit,
                msg,
                Columns([
                    Button("Save", on_press=on_save),
                    Button("Done", on_press=on_done),
                ]),
            ])

            dialog = LineBox(content, title=" Reference ")
            self._show_dialog(dialog)

    def _save(self):
        """Save the template."""
        if not self._can_save():
            self.message = "⚠️ Template is empty. Add some content first!"
            self.message_style = "warning"
            self._refresh()
            return

        lines = ["[setup]"]
        for dir_path in sorted(self.directories):
            clean_path = dir_path.replace('{name}/', '')
            lines.append(f"makefolder {clean_path}")
        for file_path, content in sorted(self.files.items()):
            clean_path = file_path.replace('{name}/', '')

            if content:
                lines.append(f"makefile {clean_path}: {content}")
            else:
                lines.append(f"makefile {clean_path}:")
        for cmd in self.commands:
            lines.append(cmd)

        try:
            self.template_file.write_text("\n".join(lines))
            self.message = f"✅ Template saved: {self.template_file}"
            self.message_style = "success"
            self._refresh()

            close_btn = Button("Great!", on_press=lambda btn: self._close_dialog())
            content = Pile([
                Text(f"✅ Saved to:\n{self.template_file}", align="center"),
                close_btn,
            ])
            dialog = LineBox(content, title=" Success ")
            self._show_dialog(dialog)

        except Exception as e:
            self.message = f"❌ Error: {e}"
            self.message_style = "error"
            self._refresh()

    def _quit(self):
        """Quit the application."""
        if self._can_save():
            def on_save(btn):
                self._save()
                raise urwid.ExitMainLoop()

            def on_quit(btn):
                raise urwid.ExitMainLoop()

            def on_cancel(btn):
                self._close_dialog()

            content = Pile([
                Text("Save before quitting?", align="center"),
                Divider("─"),
                Columns([
                    Button("Save", on_press=on_save),
                    Button("Quit", on_press=on_quit),
                    Button("Cancel", on_press=on_cancel),
                ]),
            ])

            dialog = LineBox(content, title=" Quit ")
            self._show_dialog(dialog)

        else:
            raise urwid.ExitMainLoop()

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


def build_template_interactive(template_name: str, templates_dir: Path, force: bool = False):
    """Interactive template builder using Urwid TUI."""
    builder = TemplateBuilderTUI(template_name, templates_dir, force)
    builder.run()


def list_available_commands() -> None:
    """List all available setup commands with descriptions."""
    commands = {
        'ask': 'Ask for user input',
        'makevenv': 'Create virtual environment. args: py version eg 3.14',
        'pkginstall': 'Install packages args: <pkg1> <pkg2>',
        'pkginstalldev': 'Install dev packages args: <pkg1> <pkg2>',
        'installreq': 'Install from requirements.txt args: none',
        'installreqdev': 'Install dev requirements args: none',
        'makefolder': 'Create a folder / its recommended to use the file manager or dedicated task',
        'makefile': 'Create a file / its recommended to use the file manager or dedicated task',
        'editfile': 'Edit a file /  its recommended to supply the file contents via the makefile refrence',
        'initgit': 'Initialize git',
        'echo': 'Print a message args: "msg"',
    }

    click.echo("\n" + click.style("Available setup commands:", fg="yellow", bold=True))
    click.echo(click.style("-" * 40, fg="blue"))
    for cmd, description in commands.items():
        click.echo(f"  {click.style(cmd, fg='cyan', bold=True):<12} - {click.style(description, fg='white')}")
    click.echo(click.style("-" * 40, fg="blue"))