"""PyTemplate - Python Template System - Project scaffolding with .setup templates."""
import os
import sys
import click
from pathlib import Path


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
    click.echo("Warning: You are running a pre-release version. expect bugs and issues")

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
    click.echo("Warning: You are running a pre-release version. expect bugs and issues")

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
        click.echo("Warning: You are running a pre-release version. expect bugs and issues")
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


# Register template manager commands
register_commands(main)


if __name__ == "__main__":
    main()