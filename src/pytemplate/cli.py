"""PyTemplate - Python Template System - Project scaffolding with .setup templates."""
import os
import sys
import click
from pathlib import Path
from .setup_interpreter import run_setup_commands, ask_input
from .template_builder import build_template_interactive, quick_template, list_available_commands
from .template_manager import register_commands

TEMPLATES_DIR = Path(__file__).parent / "templates"


def parse_setup(filepath):
    """Parse a .setup file into structure and commands."""
    structure = {"dirs": [], "files": {}}
    commands = []
    in_setup = False

    with open(filepath) as f:
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

            if in_setup:
                commands.append(line)
            elif line.endswith("/"):
                structure["dirs"].append(line[:-1])
            elif ":" in line and not line.startswith(" ") and not line.startswith("\t"):
                path, content = line.split(":", 1)
                path = path.strip()
                if "/" in path or "." in path:
                    structure["files"][path] = content.strip()
                else:
                    commands.append(line)
            elif line and ("/" in line or "." in line):
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

        if content and content.startswith("@"):
            ref_file = TEMPLATES_DIR / content[1:]
            if ref_file.exists():
                content = ref_file.read_text()
            else:
                content = ""
                click.echo(f"  Warning: Reference file not found: {content}")

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

    Templates are stored in the 'templates/' directory as <name>.setup files.
    Use the 'list' command to see available templates, and 'show' to preview
    a template's structure.

    If you're not sure what to do, use --help for more information.
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
    click.echo("Please run pytemplate create --help if you don't know what you're doing.")

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
    click.echo("Please run pytemplate list --help if you don't know what you're doing.")

    if not TEMPLATES_DIR.exists():
        click.echo("No templates directory found.")
        return

    templates = [f.stem for f in TEMPLATES_DIR.glob("*.setup")]
    if not templates:
        click.echo("No templates found.")
        return

    click.echo("Available templates:")
    for t in templates:
        click.echo(f"  • {t}")


@main.command()
@click.argument('template_name')
def show(template_name):
    """Show the full content of a specific template."""
    click.echo("Please run pytemplate show --help if you don't know what you're doing.")

    template_file = TEMPLATES_DIR / f"{template_name}.setup"

    if not template_file.exists():
        click.echo(f"Template '{template_name}' not found.")
        return

    click.echo(f"\nTemplate: {template_name}")
    click.echo("-" * 40)
    click.echo(template_file.read_text())


@main.command()
@click.argument('name')
@click.option('--force', '-f', is_flag=True, help='Overwrite existing template')
@click.option('--quick', '-q', is_flag=True, help='Quick mode with presets')
def buildtemplate(name, force, quick):
    """Build a new template interactively.

    Examples:

        pytemplate buildtemplate my-template
            Creates a new template called 'my-template.setup'

        pytemplate buildtemplate my-template --force
            Overwrites existing 'my-template.setup' if it exists

        pytemplate buildtemplate my-template --quick
            Quick template creation with presets
    """
    click.echo("Please run pytemplate buildtemplate --help if you don't know what you're doing. Or use one of our prebuilt templates.")

    try:
        if quick:
            quick_template(name, TEMPLATES_DIR, force)
        else:
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
    click.echo("Remember! Making templates are hard. If you think template making is too hard, use one of our prebuilt templates or get a custom template via our template manager.")
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