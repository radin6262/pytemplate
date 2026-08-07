"""Template builder module for creating .setup templates interactively."""

import click
import shutil
import tempfile
import os
from pathlib import Path
from typing import List, Dict, Optional
from filenav import CLIFileManager


def color(text: str, fg: str = None, bold: bool = False, dim: bool = False) -> str:
    """Apply color to text using Click."""
    return click.style(text, fg=fg, bold=bold, dim=dim)


class TemplateBuilder:
    """Interactive template builder with task-based workflow."""

    def __init__(self, template_name: str, templates_dir: Path, force: bool = False):
        self.template_name = template_name
        self.templates_dir = templates_dir
        self.force = force
        self.template_file = templates_dir / f"{template_name}.setup"

        # Template parts
        self.directories = []
        self.files = {}
        self.commands = []
        self.references = []

    def run(self):
        """Run the interactive template builder."""
        # Check if template already exists
        if self.template_file.exists() and not self.force:
            click.confirm(color(f"Template '{self.template_name}' already exists. Overwrite?", fg="yellow"), abort=True)

        click.echo(color(f"\nBuilding template: {self.template_name}", fg="cyan", bold=True))
        click.echo(color("=" * 50, fg="blue", bold=True))
        click.echo(color("You'll be guided through creating your template step by step.", fg="white"))
        click.echo(color("=" * 50, fg="blue", bold=True))

        self._main_menu()

    def _main_menu(self):
        """Display the main menu with available tasks."""
        while True:
            click.echo("\n" + color("=" * 50, fg="blue", bold=True))
            click.echo(color("TASKS:", fg="yellow", bold=True))
            click.echo(color("=" * 50, fg="blue", bold=True))

            # Show all tasks with status
            tasks = [
                ("1", "Add directories", self._has_directories),
                ("2", "Add files", self._has_files),
                ("3", "Add setup commands", self._has_commands),
                ("4", "Preview and save template", self._can_save),
                ("5", "Add reference files", self._has_references),
            ]

            for task_id, description, check_func in tasks:
                status = color("✓", fg="green") if check_func() else " "
                click.echo(f"  [{status}] {color(task_id, fg='cyan')}. {description}")

            click.echo(color("=" * 50, fg="blue", bold=True))
            click.echo("  " + color("[f]", fg="green", bold=True) + " File Manager (create files/folders visually)")
            click.echo("  " + color("[q]", fg="red", bold=True) + " Quit without saving")
            click.echo("  " + color("[s]", fg="green", bold=True) + " Finish and save")
            click.echo(color("=" * 50, fg="blue", bold=True))

            choice = click.prompt("Choose a task", default="", show_default=False)

            if choice.lower() == 'q':
                if click.confirm(color("Quit without saving?", fg="yellow")):
                    click.echo(color("Template not saved.", fg="yellow"))
                    return
                continue

            if choice.lower() == 's':
                if self._can_save():
                    self._save_template()
                    return
                else:
                    click.echo(color("You need to add at least one directory, file, or command before saving.", fg="yellow"))
                    continue

            if choice.lower() == 'f':
                self._file_manager()
                continue

            # Execute task
            if choice == '1':
                self._add_directories()
            elif choice == '2':
                self._add_files()
            elif choice == '3':
                self._add_commands()
            elif choice == '4':
                self._preview_template()
            elif choice == '5':
                self._add_reference_files()
            else:
                click.echo(color(f"Unknown option: {choice}", fg="red"))

    def _file_manager(self):
        """Open the file manager to create/navigate and select files."""
        click.echo("\n" + color("[FILE MANAGER]", fg="cyan", bold=True))
        click.echo(color("Use the file manager to create directories and files,", fg="white"))
        click.echo(color("and select files to add to your template.", fg="white"))

        # Run file manager with template name
        manager = CLIFileManager(self.template_name)
        selected_files = manager.run()

        # Process selected files and add to template
        if selected_files:
            click.echo(color(f"\nAdding {len(selected_files)} selected files to template...", fg="yellow"))

            # Get the temp directory where files were created
            temp_dir = manager.temp_dir

            # First, collect all directories from the temp structure
            directories = set()
            for file_path in selected_files:
                try:
                    rel_path = Path(file_path).relative_to(temp_dir)
                    # Add {name}/ prefix for the file
                    path = f"{{name}}/{str(rel_path).replace('\\', '/')}"

                    # Also add parent directories
                    parent = rel_path.parent
                    while str(parent) != '.':
                        dir_path = f"{{name}}/{str(parent).replace('\\', '/')}"
                        if not dir_path.endswith('/'):
                            dir_path += '/'
                        directories.add(dir_path)
                        parent = parent.parent

                    # Get the actual file content
                    full_path = Path(file_path)
                    if full_path.exists() and full_path.is_file():
                        content = None
                        try:
                            file_size = full_path.stat().st_size
                            if file_size < 1024 * 10:  # Less than 10KB
                                content = full_path.read_text()
                                if content and content.startswith('@'):
                                    ref_name = content[1:].strip()
                                    if ref_name not in self.references:
                                        self.references.append(ref_name)
                        except:
                            pass

                        # Add file to template using makefile command in setup section
                        if path not in self.files:
                            self.files[path] = content
                            click.echo(color(f"  ✓ Added file: {path}", fg="green"))
                        else:
                            click.echo(color(f"  ⚠ File '{path}' already exists in template", fg="yellow"))
                except Exception as e:
                    click.echo(color(f"  Error adding {file_path}: {e}", fg="red"))

            # Add directories using makefolder commands
            for dir_path in sorted(directories):
                if dir_path not in self.directories:
                    self.directories.append(dir_path)
                    click.echo(color(f"  ✓ Added directory: {dir_path}", fg="green"))

        # Clean up temp directory
        manager.cleanup()

    def _add_directories_from_structure(self, temp_dir: Path):
        """Add directories from the temp structure to the template."""
        directories = set()
        for root, dirs, files in os.walk(temp_dir):
            rel_path = Path(root).relative_to(temp_dir)
            if str(rel_path) != '.':
                dir_path = f"{{name}}/{str(rel_path).replace('\\', '/')}"
                if not dir_path.endswith('/'):
                    dir_path += '/'
                directories.add(dir_path)

        for dir_path in sorted(directories):
            if dir_path not in self.directories:
                self.directories.append(dir_path)
                click.echo(color(f"  ✓ Added directory: {dir_path}", fg="green"))

    def _has_directories(self) -> bool:
        """Check if directories have been added."""
        return len(self.directories) > 0

    def _has_files(self) -> bool:
        """Check if files have been added."""
        return len(self.files) > 0

    def _has_commands(self) -> bool:
        """Check if commands have been added."""
        return len(self.commands) > 0

    def _has_references(self) -> bool:
        """Check if reference files exist."""
        return len(self.references) > 0

    def _can_save(self) -> bool:
        """Check if template can be saved (has at least some content)."""
        return self._has_directories() or self._has_files() or self._has_commands()

    def _add_directories(self):
        """Add directories to the template."""
        click.echo("\n" + color("[ADD DIRECTORIES]", fg="cyan", bold=True))
        click.echo(color("Enter directory paths relative to project root.", fg="white"))
        click.echo(color("Examples: src/, tests/, docs/, data/", dim=True))
        click.echo(color(f"Current: {len(self.directories)} directories added", fg="yellow"))

        if self.directories:
            click.echo(color("Added directories:", fg="yellow"))
            for d in self.directories:
                click.echo(color(f"  - {d}", fg="white"))

        while True:
            click.echo("\n" + color("Options:", fg="yellow", bold=True))
            click.echo("  " + color("[a]", fg="green", bold=True) + " Add a directory")
            click.echo("  " + color("[r]", fg="red", bold=True) + " Remove a directory")
            click.echo("  " + color("[d]", fg="blue", bold=True) + " Done")

            choice = click.prompt("Choose option", default="a", show_default=False)

            if choice.lower() == 'd':
                break
            elif choice.lower() == 'a':
                dir_path = click.prompt(color("Directory path (e.g., src/)", fg="cyan"), default="", show_default=False)
                if dir_path:
                    if not dir_path.endswith('/'):
                        dir_path += '/'
                    if dir_path in self.directories:
                        click.echo(color(f"  Directory '{dir_path}' already exists!", fg="yellow"))
                    else:
                        self.directories.append(dir_path)
                        click.echo(color(f"  Added: {dir_path}", fg="green"))
            elif choice.lower() == 'r':
                if not self.directories:
                    click.echo(color("  No directories to remove.", fg="yellow"))
                    continue

                click.echo(color("Select directory to remove:", fg="yellow"))
                for i, d in enumerate(self.directories, 1):
                    click.echo(f"  {color(f'[{i}]', fg='cyan')} {d}")

                try:
                    idx = int(click.prompt("Number", default="", show_default=False))
                    if 1 <= idx <= len(self.directories):
                        removed = self.directories.pop(idx - 1)
                        click.echo(color(f"  Removed: {removed}", fg="red"))
                    else:
                        click.echo(color("  Invalid number.", fg="red"))
                except ValueError:
                    click.echo(color("  Please enter a number.", fg="red"))
            else:
                click.echo(color(f"Unknown option: {choice}", fg="red"))

        click.echo(color(f"\n✓ Added {len(self.directories)} directories", fg="green"))

    def _add_files(self):
        """Add files to the template."""
        click.echo("\n" + color("[ADD FILES]", fg="cyan", bold=True))
        click.echo(color("Enter file paths relative to project root.", fg="white"))
        click.echo(color("Examples:", dim=True))
        click.echo(color("  README.md", dim=True))
        click.echo(color("  src/main.py: print('Hello')", dim=True))
        click.echo(color("  src/config.py: @config-template", dim=True))
        click.echo(color(f"Current: {len(self.files)} files added", fg="yellow"))

        if self.files:
            click.echo(color("Added files:", fg="yellow"))
            for f in self.files:
                content = self.files[f]
                if content:
                    click.echo(color(f"  - {f} -> {content[:50]}...", fg="white"))
                else:
                    click.echo(color(f"  - {f}", fg="white"))

        while True:
            click.echo("\n" + color("Options:", fg="yellow", bold=True))
            click.echo("  " + color("[a]", fg="green", bold=True) + " Add a file")
            click.echo("  " + color("[r]", fg="red", bold=True) + " Remove a file")
            click.echo("  " + color("[e]", fg="magenta", bold=True) + " Edit file content")
            click.echo("  " + color("[d]", fg="blue", bold=True) + " Done")

            choice = click.prompt("Choose option", default="a", show_default=False)

            if choice.lower() == 'd':
                break
            elif choice.lower() == 'a':
                file_input = click.prompt(color("File path (or path: content)", fg="cyan"), default="", show_default=False)
                if file_input:
                    if ':' in file_input:
                        path, content = file_input.split(':', 1)
                        path = path.strip()
                        content = content.strip()
                        if path in self.files:
                            click.echo(color(f"  File '{path}' already exists!", fg="yellow"))
                        else:
                            self.files[path] = content
                            if content.startswith('@'):
                                self.references.append(content[1:])
                            click.echo(color(f"  Added: {path}", fg="green"))
                    else:
                        path = file_input.strip()
                        if path in self.files:
                            click.echo(color(f"  File '{path}' already exists!", fg="yellow"))
                        else:
                            self.files[path] = None
                            click.echo(color(f"  Added: {path}", fg="green"))
            elif choice.lower() == 'r':
                if not self.files:
                    click.echo(color("  No files to remove.", fg="yellow"))
                    continue

                click.echo(color("Select file to remove:", fg="yellow"))
                file_list = list(self.files.keys())
                for i, f in enumerate(file_list, 1):
                    click.echo(f"  {color(f'[{i}]', fg='cyan')} {f}")

                try:
                    idx = int(click.prompt("Number", default="", show_default=False))
                    if 1 <= idx <= len(file_list):
                        removed = file_list[idx - 1]
                        del self.files[removed]
                        click.echo(color(f"  Removed: {removed}", fg="red"))
                    else:
                        click.echo(color("  Invalid number.", fg="red"))
                except ValueError:
                    click.echo(color("  Please enter a number.", fg="red"))
            elif choice.lower() == 'e':
                if not self.files:
                    click.echo(color("  No files to edit.", fg="yellow"))
                    continue

                click.echo(color("Select file to edit:", fg="yellow"))
                file_list = list(self.files.keys())
                for i, f in enumerate(file_list, 1):
                    click.echo(f"  {color(f'[{i}]', fg='cyan')} {f}")

                try:
                    idx = int(click.prompt("Number", default="", show_default=False))
                    if 1 <= idx <= len(file_list):
                        path = file_list[idx - 1]
                        current_content = self.files[path] or ""
                        click.echo(color(f"\nCurrent content: ", fg="yellow") + color(current_content[:100], fg="white"))
                        if len(current_content) > 100:
                            click.echo(color("  ...", dim=True))
                        new_content = click.prompt(color("New content", fg="cyan"), default=current_content, show_default=False)
                        self.files[path] = new_content
                        click.echo(color(f"  Updated: {path}", fg="green"))
                    else:
                        click.echo(color("  Invalid number.", fg="red"))
                except ValueError:
                    click.echo(color("  Please enter a number.", fg="red"))
            else:
                click.echo(color(f"Unknown option: {choice}", fg="red"))

        click.echo(color(f"\n✓ Added {len(self.files)} files", fg="green"))

    def _add_commands(self):
        """Add setup commands to the template."""
        click.echo("\n" + color("[ADD SETUP COMMANDS]", fg="cyan", bold=True))
        click.echo(color("Available commands:", fg="yellow"))
        click.echo(color("  ask \"Question\" default=\"value\" var=\"varname\"", fg="white"))
        click.echo(color("  makevenv [python_version]", fg="white"))
        click.echo(color("  pkginstall package1 package2", fg="white"))
        click.echo(color("  pkginstalldev package1 package2", fg="white"))
        click.echo(color("  installreq", fg="white"))
        click.echo(color("  installreqdev", fg="white"))
        click.echo(color("  makefolder folder/path", fg="white"))
        click.echo(color("  makefile file/path \"content\"", fg="white"))
        click.echo(color("  editfile file/path operation [args]", fg="white"))
        click.echo(color("  initgit", fg="white"))
        click.echo(color("  echo \"message\"", fg="white"))
        click.echo(color(f"Current: {len(self.commands)} commands added", fg="yellow"))

        if self.commands:
            click.echo(color("\nAdded commands:", fg="yellow"))
            for i, cmd in enumerate(self.commands, 1):
                click.echo(f"  {color(f'{i}', fg='cyan')}. {color(cmd, fg='white')}")

        while True:
            click.echo("\n" + color("Options:", fg="yellow", bold=True))
            click.echo("  " + color("[a]", fg="green", bold=True) + " Add a command")
            click.echo("  " + color("[r]", fg="red", bold=True) + " Remove a command")
            click.echo("  " + color("[e]", fg="magenta", bold=True) + " Edit a command")
            click.echo("  " + color("[d]", fg="blue", bold=True) + " Done")

            choice = click.prompt("Choose option", default="a", show_default=False)

            if choice.lower() == 'd':
                break
            elif choice.lower() == 'a':
                cmd = click.prompt(color("Command", fg="cyan"), default="", show_default=False)
                if cmd:
                    self.commands.append(cmd)
                    click.echo(color(f"  Added: {cmd}", fg="green"))
            elif choice.lower() == 'r':
                if not self.commands:
                    click.echo(color("  No commands to remove.", fg="yellow"))
                    continue

                click.echo(color("Select command to remove:", fg="yellow"))
                for i, cmd in enumerate(self.commands, 1):
                    click.echo(f"  {color(f'[{i}]', fg='cyan')} {cmd}")

                try:
                    idx = int(click.prompt("Number", default="", show_default=False))
                    if 1 <= idx <= len(self.commands):
                        removed = self.commands.pop(idx - 1)
                        click.echo(color(f"  Removed: {removed}", fg="red"))
                    else:
                        click.echo(color("  Invalid number.", fg="red"))
                except ValueError:
                    click.echo(color("  Please enter a number.", fg="red"))
            elif choice.lower() == 'e':
                if not self.commands:
                    click.echo(color("  No commands to edit.", fg="yellow"))
                    continue

                click.echo(color("Select command to edit:", fg="yellow"))
                for i, cmd in enumerate(self.commands, 1):
                    click.echo(f"  {color(f'[{i}]', fg='cyan')} {cmd}")

                try:
                    idx = int(click.prompt("Number", default="", show_default=False))
                    if 1 <= idx <= len(self.commands):
                        current_cmd = self.commands[idx - 1]
                        new_cmd = click.prompt(color("New command", fg="cyan"), default=current_cmd, show_default=False)
                        self.commands[idx - 1] = new_cmd
                        click.echo(color(f"  Updated: {new_cmd}", fg="green"))
                    else:
                        click.echo(color("  Invalid number.", fg="red"))
                except ValueError:
                    click.echo(color("  Please enter a number.", fg="red"))
            else:
                click.echo(color(f"Unknown option: {choice}", fg="red"))

        click.echo(color(f"\n✓ Added {len(self.commands)} commands", fg="green"))

    def _preview_template(self):
        """Preview the current template."""
        click.echo("\n" + color("[TEMPLATE PREVIEW]", fg="cyan", bold=True))
        click.echo(color("=" * 50, fg="blue", bold=True))

        if not self._can_save():
            click.echo(color("Template is empty. Add some directories, files, or commands first.", fg="yellow"))
            return

        # Build template content
        lines = []
        lines.append("[setup]")

        # Add makefolder commands for directories
        for dir_path in sorted(self.directories):
            clean_path = dir_path.replace('{name}/', '')
            lines.append(f"makefolder {clean_path}")

        # Add makefile commands for files
        for file_path, content in sorted(self.files.items()):
            clean_path = file_path.replace('{name}/', '')
            if content:
                lines.append(f'makefile {clean_path} "{content}"')
            else:
                lines.append(f'makefile {clean_path} ""')

        # Add other setup commands
        for cmd in self.commands:
            lines.append(cmd)

        template_content = "\n".join(lines)

        click.echo(color(template_content, fg="white"))
        click.echo(color("=" * 50, fg="blue", bold=True))

        if self.references:
            click.echo(color("\nReference files needed:", fg="yellow"))
            for ref in self.references:
                click.echo(color(f"  - @{ref}", fg="white"))

    def _add_reference_files(self):
        """Add content for reference files."""
        if not self.references:
            click.echo(color("\nNo reference files found in template.", fg="yellow"))
            click.echo(color("Reference files are added when you create files with @ prefix.", dim=True))
            return

        click.echo("\n" + color("[ADD REFERENCE FILES]", fg="cyan", bold=True))
        click.echo(color("Reference files are template files that can be included with @", fg="white"))

        for ref in self.references:
            ref_file = self.templates_dir / f"@{ref}"

            if ref_file.exists() and not self.force:
                if not click.confirm(color(f"  @{ref} already exists. Overwrite?", fg="yellow")):
                    continue

            click.echo(color(f"\nEnter content for @{ref}:", fg="cyan"))
            click.echo(color("(Type content, then press Enter twice on a new line to finish)", dim=True))

            lines = []
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)

            # Remove trailing empty lines
            while lines and lines[-1] == "":
                lines.pop()

            if lines:
                content = "\n".join(lines)
                ref_file.write_text(content)
                click.echo(color(f"  ✓ Saved: @{ref}", fg="green"))
            else:
                # Create empty reference file
                ref_file.write_text("")
                click.echo(color(f"  ✓ Created empty: @{ref}", fg="green"))

        click.echo(color("\n✓ All reference files processed", fg="green"))

    def _save_template(self):
        """Save the template."""
        if not self._can_save():
            click.echo(color("Template is empty. Add some content first.", fg="yellow"))
            return

        # Show preview first
        self._preview_template()

        if not click.confirm(color("\nSave this template?", fg="yellow")):
            click.echo(color("Template not saved.", fg="yellow"))
            return

        # Build template content - directories as makefolder commands in setup
        lines = []

        # Add setup section with all commands
        lines.append("[setup]")

        # Add makefolder commands for directories
        for dir_path in sorted(self.directories):
            # Remove {name}/ prefix for the makefolder command
            clean_path = dir_path.replace('{name}/', '')
            lines.append(f"makefolder {clean_path}")

        # Add makefile commands for files
        for file_path, content in sorted(self.files.items()):
            # Remove {name}/ prefix for the makefile command
            clean_path = file_path.replace('{name}/', '')
            if content:
                # If content has newlines, keep it as is
                if '\n' in content:
                    lines.append(f'makefile {clean_path} "{content}"')
                else:
                    lines.append(f'makefile {clean_path} "{content}"')
            else:
                lines.append(f'makefile {clean_path} ""')

        # Add other setup commands
        for cmd in self.commands:
            lines.append(cmd)

        template_content = "\n".join(lines)

        # Save template
        self.template_file.write_text(template_content)
        click.echo(color(f"\n✓ Template saved to: {self.template_file}", fg="green"))
        click.echo(color(f"\nYou can now use it with:", fg="yellow"))
        click.echo(color(f"  pytemplate create my-project --template {self.template_name}", fg="cyan"))

        # Ask about reference files
        if self.references:
            if click.confirm(color("\nDo you want to add content for reference files?", fg="yellow")):
                self._add_reference_files()


def build_template_interactive(template_name: str, templates_dir: Path, force: bool = False):
    """Interactive template builder with task-based workflow."""
    builder = TemplateBuilder(template_name, templates_dir, force)
    builder.run()


def quick_template(name: str, templates_dir: Path, force: bool = False):
    """Quick template builder with presets."""
    presets = {
        'python': {
            'directories': ['src/', 'tests/', 'docs/'],
            'files': {
                'README.md': None,
                'pyproject.toml': None,
                '.gitignore': '@python-gitignore',
                'requirements.txt': None,
            },
            'commands': [
                'ask "Package name" default="${name}" var="package_name"',
                'ask "Author name" default="Developer" var="author"',
                'ask "Python version" default="3.11" var="py_version"',
                'makevenv ${py_version}',
                'installreq',
                'installreqdev',
                'initgit',
                'echo "Project ${package_name} is ready!"',
            ]
        },
        'web': {
            'directories': ['src/', 'src/templates/', 'src/static/', 'tests/', 'docs/'],
            'files': {
                'README.md': None,
                'pyproject.toml': None,
                '.gitignore': '@python-gitignore',
                'requirements.txt': None,
                'src/app.py': '@web-app',
                'src/config.py': '@web-config',
            },
            'commands': [
                'ask "App name" default="${name}" var="app_name"',
                'ask "Author name" default="Developer" var="author"',
                'ask "Python version" default="3.11" var="py_version"',
                'makevenv ${py_version}',
                'pkginstall flask python-dotenv',
                'pkginstalldev pytest black flake8',
                'initgit',
                'echo "Web app ${app_name} is ready!"',
            ]
        },
        'cli': {
            'directories': ['src/', 'src/cli/', 'tests/', 'docs/'],
            'files': {
                'README.md': None,
                'pyproject.toml': None,
                '.gitignore': '@python-gitignore',
                'requirements.txt': None,
                'src/main.py': '@cli-main',
                'src/cli/commands.py': '@cli-commands',
            },
            'commands': [
                'ask "CLI name" default="${name}" var="cli_name"',
                'ask "Author name" default="Developer" var="author"',
                'ask "Python version" default="3.11" var="py_version"',
                'makevenv ${py_version}',
                'pkginstall click',
                'pkginstalldev pytest black flake8',
                'initgit',
                'echo "CLI tool ${cli_name} is ready!"',
            ]
        }
    }

    click.echo("\n" + color("Quick template presets:", fg="yellow", bold=True))
    click.echo(color("  python  - Basic Python project", fg="white"))
    click.echo(color("  web     - Web application (Flask-based)", fg="white"))
    click.echo(color("  cli     - Command-line tool (Click-based)", fg="white"))

    preset = click.prompt(color("Choose preset (or 'custom' for full builder)", fg="cyan"), default="custom")

    if preset == 'custom':
        return build_template_interactive(name, templates_dir, force)

    if preset not in presets:
        click.echo(color(f"Unknown preset: {preset}", fg="red"))
        return False

    template_data = presets[preset]

    # Build template content
    lines = []
    for dir_path in template_data['directories']:
        lines.append(dir_path)

    for file_path, content in template_data['files'].items():
        if content:
            lines.append(f"{file_path}: {content}")
        else:
            lines.append(file_path)

    if template_data['commands']:
        lines.append("")
        lines.append("[setup]")
        lines.extend(template_data['commands'])

    template_content = "\n".join(lines)

    # Show preview
    click.echo("\n" + color("=" * 50, fg="blue", bold=True))
    click.echo(color("Template Preview:", fg="yellow", bold=True))
    click.echo(color("=" * 50, fg="blue", bold=True))
    click.echo(color(template_content, fg="white"))
    click.echo(color("=" * 50, fg="blue", bold=True))

    if click.confirm(color("\nSave this template?", fg="yellow")):
        template_file = templates_dir / f"{name}.setup"
        template_file.write_text(template_content)
        click.echo(color(f"\n✓ Template saved to: {template_file}", fg="green"))
        return True

    return False


def list_available_commands() -> None:
    """List all available setup commands with descriptions."""
    commands = {
        'ask': 'Ask for user input during template execution',
        'makevenv': 'Create a virtual environment',
        'pkginstall': 'Install packages in the virtual environment',
        'pkginstalldev': 'Install development packages',
        'installreq': 'Install packages from requirements.txt',
        'installreqdev': 'Install development packages from requirements-dev.txt',
        'makefolder': 'Create a folder in the project directory',
        'makefile': 'Create a file with content',
        'editfile': 'Edit a file (append, prepend, replace, etc.)',
        'initgit': 'Initialize a git repository',
        'echo': 'Print a message to the console',
    }

    click.echo("\n" + color("Available setup commands:", fg="yellow", bold=True))
    click.echo(color("-" * 40, fg="blue"))
    for cmd, description in commands.items():
        click.echo(f"  {color(cmd, fg='cyan', bold=True):<12} - {color(description, fg='white')}")
    click.echo(color("-" * 40, fg="blue"))