"""PyTemplate - Python Template System - Project scaffolding with .setup templates."""
import os
import sys
import click
from pathlib import Path

# Textual imports
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, ListView, ListItem, Label, Button, Static, Input, TextArea

from .setup_interpreter import run_setup_commands, ask_input
from .template_builder import build_template_interactive, list_available_commands
from .template_manager import register_commands

TEMPLATES_DIR = Path(__file__).parent / "templates"


def parse_setup(filepath):
    """Parse a .setup file into structure and commands."""
    structure = {"dirs": [], "files": {}}
    commands = []
    in_setup = False

    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if line == "[setup]":
                in_setup = True
                continue

            elif line.startswith("["):
                in_setup = False
                continue

            # Everything inside [setup] is a setup command
            if in_setup:
                commands.append(line)
                continue

            # Directory
            if line.endswith("/"):
                structure["dirs"].append(line[:-1])
                continue

            # File with content or reference
            # Examples:
            # hey.py: hello world
            # hey.py: @general-readme
            if ":" in line and not line.startswith((" ", "\t")):
                path, content = line.split(":", 1)
                path = path.strip()
                content = content.strip()

                if "/" in path or "." in path:
                    structure["files"][path] = content
                    continue

                commands.append(line)
                continue

            # Regular empty file
            if line and ("/" in line or "." in line):
                structure["files"][line] = None

    return structure, commands


def collect_variables(commands, context):
    """Collect user input for ask commands before running setup."""
    for cmd in commands:
        cmd = cmd.strip()
        if not cmd or cmd.startswith("#"):
            continue

        parts = cmd.split(maxsplit=1)
        action = parts[0].lower()

        if action == "ask" and len(parts) > 1:
            rest = parts[1]
            prompt_text = rest
            default_val = None
            var = None

            if rest.startswith('"'):
                end_quote = rest.find('"', 1)
                if end_quote != -1:
                    prompt_text = rest[1:end_quote]
                    rest = rest[end_quote+1:].strip()
                else:
                    prompt_text = rest
                    rest = ""
            elif rest.startswith("'"):
                end_quote = rest.find("'", 1)
                if end_quote != -1:
                    prompt_text = rest[1:end_quote]
                    rest = rest[end_quote+1:].strip()
                else:
                    prompt_text = rest
                    rest = ""

            args = rest.split()
            for arg in args:
                if arg.startswith("default="):
                    default_val = arg.split("=", 1)[1].strip('"\'')
                elif arg.startswith("var="):
                    var = arg.split("=", 1)[1].strip('"\'')

            var_name, value = ask_input(prompt_text, default_val, var)
            if var_name:
                context[var_name] = value

    return context


def create_from_template(name, template_name, base_path=".", run_setup=True):
    """Create project from a .setup template."""
    template_file = TEMPLATES_DIR / f"{template_name}.setup"

    if not template_file.exists():
        raise click.ClickException(f"Template '{template_name}' not found")

    project_dir = Path(base_path) / name
    if project_dir.exists():
        raise click.ClickException(f"Directory {project_dir} already exists!")

    structure, commands = parse_setup(template_file)

    click.echo(f"Debug: Found {len(structure['dirs'])} dirs, {len(structure['files'])} files, {len(commands)} commands")

    context = {
        "name": name,
        "project_dir": str(project_dir),
    }

    if run_setup and commands:
        click.echo("\nProject configuration:")
        context = collect_variables(commands, context)

    for dir_path in structure["dirs"]:
        formatted_path = dir_path
        for var_name, var_value in context.items():
            formatted_path = formatted_path.replace(f"${{{var_name}}}", str(var_value))
        formatted_path = formatted_path.format(name=name)
        full_path = project_dir / formatted_path
        full_path.mkdir(parents=True, exist_ok=True)
        click.echo(f"  Created dir: {formatted_path}")

    for file_path, content in structure["files"].items():
        formatted_path = file_path
        for var_name, var_value in context.items():
            formatted_path = formatted_path.replace(f"${{{var_name}}}", str(var_value))
        formatted_path = formatted_path.format(name=name)

        full_path = project_dir / formatted_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        if content and content.strip().startswith("@"):
            reference_name = content.strip()

            # ALWAYS resolve references from:
            # templates/@<reference>
            ref_file = TEMPLATES_DIR / reference_name

            if ref_file.exists() and ref_file.is_file():
                content = ref_file.read_text(encoding="utf-8")

                click.echo(
                    f"  [REF] Loaded reference: {reference_name}"
                )
            else:
                click.echo(
                    f"  [ERROR] Reference file not found: {ref_file}"
                )
                content = ""

        if content:
            for var_name, var_value in context.items():
                content = content.replace(f"${{{var_name}}}", str(var_value))
            content = content.format(name=name)
            full_path.write_text(content)
            click.echo(f"  Created file: {formatted_path}")
        else:
            full_path.touch()
            click.echo(f"  Created file: {formatted_path}")

    if run_setup and commands:
        click.echo("\nRunning setup commands...")
        click.echo(f"Commands to run: {commands}")
        run_setup_commands(project_dir, commands, context)

    return project_dir


# TUI Commands
class TemplateListScreen(Screen):
    """TUI for listing templates."""

    CSS = """
    TemplateListScreen {
        align: center middle;
    }
    
    #container {
        width: 80%;
        height: 80%;
        border: solid $primary;
        padding: 1;
    }
    
    #list {
        height: 70%;
        border: solid $surface;
        padding: 1;
    }
    
    #actions {
        height: 8;
        margin-top: 1;
    }
    
    Button {
        margin: 0 1;
        width: 20;
    }
    """

    def __init__(self, templates_dir: Path):
        super().__init__()
        self.templates_dir = templates_dir

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Label("📦 Available Templates", id="title"),
            ScrollableContainer(
                ListView(id="template-list"),
                id="list",
            ),
            Container(
                Horizontal(
                    Button("Use Template", variant="primary", id="btn-use"),
                    Button("Refresh", variant="info", id="btn-refresh"),
                    Button("Back", variant="error", id="btn-back"),
                ),
                id="actions",
            ),
            id="container",
        )
        yield Footer()

    def on_mount(self):
        self.refresh_list()

    def refresh_list(self):
        list_view = self.query_one("#template-list", ListView)
        list_view.clear()

        templates = [f.stem for f in self.templates_dir.glob("*.setup")]
        if not templates:
            list_view.append(ListItem(Label("No templates found", classes="empty")))
        else:
            for t in sorted(templates):
                list_view.append(ListItem(Label(f"📄 {t}")))

    @on(ListView.Selected, "#template-list")
    def on_template_selected(self, event: ListView.Selected):
        if event.item:
            label = event.item.render()
            if label and not label.startswith("No"):
                template_name = label.split(" ", 1)[1] if " " in label else label
                self.notify(f"Selected: {template_name}")

    @on(Button.Pressed, "#btn-use")
    def use_template(self):
        list_view = self.query_one("#template-list", ListView)
        if list_view.children:
            selected = list_view.children[0] if list_view.children else None
            if selected and hasattr(selected, 'render'):
                label = selected.render()
                if label and not label.startswith("No"):
                    template_name = label.split(" ", 1)[1] if " " in label else label
                    self.dismiss(("use", template_name))

    @on(Button.Pressed, "#btn-refresh")
    def refresh(self):
        self.refresh_list()
        self.notify("Refreshed")

    @on(Button.Pressed, "#btn-back")
    def go_back(self):
        self.dismiss(("back", None))


class TemplateViewScreen(Screen):
    """TUI for viewing template content."""

    CSS = """
    TemplateViewScreen {
        align: center middle;
    }
    
    #container {
        width: 80%;
        height: 80%;
        border: solid $primary;
        padding: 1;
    }
    
    #content {
        height: 70%;
        border: solid $surface;
        padding: 1;
        overflow: auto;
    }
    
    #actions {
        height: 8;
        margin-top: 1;
    }
    
    Button {
        margin: 0 1;
        width: 20;
    }
    """

    def __init__(self, template_name: str, template_path: Path):
        super().__init__()
        self.template_name = template_name
        self.template_path = template_path

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Label(f"📄 Template: {self.template_name}", id="title"),
            ScrollableContainer(
                Static("", id="content"),
            ),
            Container(
                Horizontal(
                    Button("Back", variant="primary", id="btn-back"),
                ),
                id="actions",
            ),
            id="container",
        )
        yield Footer()

    def on_mount(self):
        try:
            content = self.template_path.read_text()
            self.query_one("#content", Static).update(content)
        except Exception:
            self.query_one("#content", Static).update("Error reading template")

    @on(Button.Pressed, "#btn-back")
    def go_back(self):
        self.dismiss(None)


class MainMenuScreen(Screen):
    """Main menu TUI."""

    CSS = """
    MainMenuScreen {
        align: center middle;
    }
    
    #container {
        width: 70%;
        height: 70%;
        border: solid $primary;
        padding: 2;
        background: $surface;
    }
    
    #title {
        text-style: bold;
        color: $primary;
        text-align: center;
        margin: 1 0;
    }
    
    #menu-list {
        height: 60%;
        margin: 1 0;
    }
    
    #menu-list ListView {
        height: 100%;
    }
    
    #footer {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    
    Button {
        margin: 0 1;
        width: 25;
    }
    """

    def __init__(self):
        super().__init__()
        self.menu_items = [
            ("📁 Create Project", "create"),
            ("📦 List Templates", "list"),
            ("🔨 Build Template", "build"),
            ("📄 Show Template", "show"),
            ("📋 Template Manager", "templates"),
            ("❓ Help", "help"),
            ("🚪 Quit", "quit"),
        ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Label("PyTemplate - Python Template System", id="title"),
            Container(
                ListView(id="menu-list"),
                id="menu-list-container",
            ),
            Label("Use arrow keys to navigate, Enter to select", id="footer"),
            id="container",
        )
        yield Footer()

    def on_mount(self):
        list_view = self.query_one("#menu-list", ListView)
        for label, action in self.menu_items:
            list_view.append(ListItem(Label(label)))
        list_view.index = 0

    @on(ListView.Selected, "#menu-list")
    def on_menu_selected(self, event: ListView.Selected):
        if event.item:
            label = event.item.render()
            action = None
            for item_label, item_action in self.menu_items:
                if item_label in label:
                    action = item_action
                    break

            if action:
                self.dismiss(action)
            else:
                self.dismiss(None)


# Dialog/Input screens (using Screen instead of ModalScreen)
class TemplateInput(Screen):
    """Input dialog for template name."""

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Enter template name:"),
            Input(placeholder="purepython", id="template-input"),
            Horizontal(
                Button("View", variant="primary", id="btn-view"),
                Button("Cancel", variant="error", id="btn-cancel"),
            ),
            id="dialog",
        )

    @on(Button.Pressed, "#btn-view")
    def do_view(self):
        name = self.query_one("#template-input", Input).value.strip()
        if name:
            self.dismiss(name)

    @on(Button.Pressed, "#btn-cancel")
    def do_cancel(self):
        self.dismiss(None)


class CreateInput(Screen):
    """Input dialog for creating a project."""

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Create New Project"),
            Label("Project name:"),
            Input(placeholder="my-project", id="project-input"),
            Label("Template name:"),
            Input(placeholder="python-basic", id="template-input"),
            Horizontal(
                Button("Create", variant="success", id="btn-create"),
                Button("Cancel", variant="error", id="btn-cancel"),
            ),
            id="dialog",
        )

    @on(Button.Pressed, "#btn-create")
    def do_create(self):
        project = self.query_one("#project-input", Input).value.strip()
        template = self.query_one("#template-input", Input).value.strip()
        if project and template:
            self.dismiss((project, template))

    @on(Button.Pressed, "#btn-cancel")
    def do_cancel(self):
        self.dismiss(None)


class BuildInput(Screen):
    """Input dialog for building a template."""

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Build New Template"),
            Label("Template name:"),
            Input(placeholder="my-template", id="template-input"),
            Label("Options:"),
            Horizontal(
                Button("Interactive", variant="primary", id="btn-interactive"),
                Button("Cancel", variant="error", id="btn-cancel"),
            ),
            id="dialog",
        )

    @on(Button.Pressed, "#btn-interactive")
    def do_interactive(self):
        name = self.query_one("#template-input", Input).value.strip()
        if name:
            self.dismiss(("interactive", name))

    @on(Button.Pressed, "#btn-cancel")
    def do_cancel(self):
        self.dismiss(None)


class HelpScreen(Screen):
    """Help screen."""

    def compose(self) -> ComposeResult:
        yield Container(
            Label("📖 PyTemplate Help", id="help-title"),
            ScrollableContainer(
                Static("""
PyTemplate Commands:

  create <name>        Create a new project
  list                 List available templates
  show <name>          Show template content
  buildtemplate <name> Build a new template
  templates            Open template navigator
  templatehelp         Show template commands help
  version              Show version info
  tui                  Open this TUI interface

Examples:
  pytemplate create my-project
  pytemplate buildtemplate my-template
  pytemplate show python-basic
                        """, id="help-content"),
            ),
            Button("Close", variant="primary", id="btn-close"),
            id="dialog",
        )

    @on(Button.Pressed, "#btn-close")
    def close(self):
        self.dismiss(None)


class PyTemplateApp(App):
    """Main PyTemplate TUI App."""

    CSS = """
    .empty {
        color: $text-muted;
        text-style: italic;
    }
    
    #dialog {
        width: 80%;
        height: 60%;
        border: solid $primary;
        background: $surface;
        padding: 1;
    }
    
    #dialog Label {
        margin: 1 0;
    }
    
    #dialog Horizontal {
        margin: 1 0;
    }
    
    #help-title {
        text-style: bold;
        color: $primary;
        text-align: center;
    }
    """

    def __init__(self, templates_dir: Path):
        super().__init__()
        self.templates_dir = templates_dir
        self.selected_template = None

    def compose(self) -> ComposeResult:
        yield MainMenuScreen()

    def on_main_menu_screen_dismissed(self, event: MainMenuScreen.Dismissed):
        action = event.result
        if action == "quit":
            self.exit()
        elif action == "list":
            self.push_screen(TemplateListScreen(self.templates_dir), self.handle_list_result)
        elif action == "show":
            self.push_screen(TemplateInput(), self.handle_template_prompt)
        elif action == "create":
            self.push_screen(CreateInput(), self.handle_create_prompt)
        elif action == "build":
            self.push_screen(BuildInput(), self.handle_build_prompt)
        elif action == "templates":
            self.notify("Opening template manager...", severity="information")
        elif action == "help":
            self.push_screen(HelpScreen())

    def handle_list_result(self, result):
        if result and result[0] == "use":
            template_name = result[1]
            self.selected_template = template_name
            template_path = self.templates_dir / f"{template_name}.setup"
            if template_path.exists():
                self.push_screen(TemplateViewScreen(template_name, template_path))

    def handle_template_prompt(self, name):
        if name:
            template_path = self.templates_dir / f"{name}.setup"
            if template_path.exists():
                self.push_screen(TemplateViewScreen(name, template_path))
            else:
                self.notify(f"Template '{name}' not found", severity="error")

    def handle_create_prompt(self, result):
        if result:
            project, template = result
            self.notify(f"Creating {project} from {template}...", severity="information")
            self.notify(f"Run: pytemplate create {project} --template {template}", severity="information")

    def handle_build_prompt(self, result):
        if result:
            mode, name = result
            if mode == "interactive":
                self.notify(f"Launching interactive builder for: {name}", severity="information")
                # from .template_builder_tui import build_template_interactive
                # build_template_interactive(name, self.templates_dir)
                self.notify(f"Template '{name}' built successfully!", severity="information")


@click.group()
def main():
    """PyTemplate - Python Template System.

    Create projects from .setup templates. Build, manage, and share templates.
    """
    pass


@main.command()
@click.argument('name', required=False)
@click.option('--template', '-t', default='python-basic',
              help='Template name (without .setup extension). Default: python-basic')
@click.option('--path', '-p', default='.',
              help='Destination directory for the new project. Default: current directory')
@click.option('--no-setup', is_flag=True,
              help='Skip running the [setup] commands (e.g., venv creation, package install)')
def create(name, template, path, no_setup):
    """Create a new project from a template.

    If NAME is not provided, you will be prompted for it.

    Examples:

        pytemplate create my-project
            Creates 'my-project' using the default 'python-basic' template.

        pytemplate create --template flet my-web-app
            Creates 'my-web-app' using the 'flet.setup' template.
    """
    if not name:
        name = click.prompt("Project name", type=str)

    try:
        project_dir = create_from_template(name, template, path, run_setup=not no_setup)
        click.echo(f"\n✓ Created: {project_dir}")
    except click.ClickException as e:
        click.echo(f"Error: {e}", err=True)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@main.command()
def list():
    """List all available templates."""
    if not TEMPLATES_DIR.exists():
        click.echo("No templates directory found.")
        return

    templates = [f.stem for f in TEMPLATES_DIR.glob("*.setup")]
    if not templates:
        click.echo("No templates found.")
        return

    click.echo("\n📦 Available Templates:")
    for t in templates:
        click.echo(f"  • {t}")


@main.command()
@click.argument('template_name')
def show(template_name):
    """Show the full content of a specific template."""
    template_file = TEMPLATES_DIR / f"{template_name}.setup"

    if not template_file.exists():
        click.echo(f"Template '{template_name}' not found.")
        return

    click.echo(f"\n📄 Template: {template_name}")
    click.echo("-" * 40)
    click.echo(template_file.read_text())


@main.command()
@click.argument('name')
@click.option('--force', '-f', is_flag=True, help='Overwrite existing template')
def buildtemplate(name, force):
    """Build a new template interactively using the TUI builder.

    Examples:

        pytemplate buildtemplate my-template
            Creates a new template called 'my-template.setup'

        pytemplate buildtemplate my-template --force
            Overwrites existing 'my-template.setup' if it exists
    """
    try:
        build_template_interactive(name, TEMPLATES_DIR, force)
        click.echo(f"\n✓ Template '{name}' created successfully!")
        click.echo(f"  Location: {TEMPLATES_DIR / f'{name}.setup'}")
        click.echo(f"\n  You can now use it with:")
        click.echo(f"  pytemplate create my-project --template {name}")

    except click.ClickException as e:
        click.echo(f"Error: {e}", err=True)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@main.command()
def templatehelp():
    """Show available commands for template building."""
    list_available_commands()


@main.command()
def version():
    """Show version information."""
    from . import __version__
    click.echo(f"PyTemplate version {__version__}")


@main.command()
def tui():
    """Open the PyTemplate TUI interface."""
    try:
        from textual import __version__ as textual_version
        app = PyTemplateApp(TEMPLATES_DIR)
        app.run()
    except ImportError:
        click.echo("Textual not installed. Install with: pip install textual")
        click.echo("Use the CLI commands instead.")
        sys.exit(1)


# Register template manager commands
register_commands(main)


if __name__ == "__main__":
    main()